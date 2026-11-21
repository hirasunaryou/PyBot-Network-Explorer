"""Grounded PyBot network analysis, without modifying the upstream project.

Dynamic connections are observed via sys.setprofile during a separate replay.
Static import arrows and literal matches are separate evidence classes.
"""
import ast
from collections import Counter, defaultdict
import os
from pathlib import Path
import random
import re
import sys
import threading
import time

ROOT_GROUPS = ("runtime", "understanding", "memory", "knowledge", "compose", "modules", "arbiter")
MAX_NODES = 125
MAX_EDGES = 260
MAX_TIMELINE = 360
_LOCK = threading.RLock()


def group_for(path):
    bits = str(path).replace("\\", "/").split("/")
    if bits[-1] == "arbiter.py":
        return "arbiter"
    if len(bits) == 2 and bits[0] == "bot":
        return "runtime"
    if len(bits) >= 2 and bits[1] in ROOT_GROUPS:
        return bits[1]
    return "runtime"


def _candidate_sources(root, reply, max_results=4):
    """Locate identical text literals. Never describe a static match as executed."""
    wanted = " ".join(str(reply or "").split())
    if len(wanted) < 32:
        return []
    needle = wanted[:min(46, len(wanted))]
    results = []
    for path in sorted((Path(root) / "bot").rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if needle not in source:
            continue
        rel = path.relative_to(root).as_posix()
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, MemoryError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = getattr(node, "value", None)
            # Adjacent string literals inside parentheses become one Constant.
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            if " ".join(value.value.split()) != wanted:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if not names:
                continue
            name = names[0]
            refs = [i + 1 for i, line in enumerate(lines)
                    if re.search(r"\breturn\s+" + re.escape(name) + r"\b", line)][:12]
            results.append({
                "path": rel, "line": node.lineno, "symbol": name,
                "exact": True, "references": refs,
                "evidence": "static_exact_literal",
                "note": "回答文と完全一致する定数。実行中の経路を証明するものではありません。",
            })
            if len(results) >= max_results:
                return results
    return results


def _path_id(path, line, fn):
    return path + "#" + str(line) + ":" + fn


def trace_turn(runtime, source, inputs, expected_reply, selected_module, seed=42):
    """Replay the given sequence, instrumenting only its final turn.

    Returns bounded renderer-ready dynamic network and a sampled chronology.
    Does NOT mutate the live conversation or claim any branch was causal.
    """
    source = Path(source).resolve()
    prefix = str(source / "bot") + os.sep
    arbiter_file = "bot/modules/arbiter.py"
    module_file = "bot/modules/" + str(selected_module) + ".py"
    source_matches = _candidate_sources(source, expected_reply)
    important_files = {x["path"] for x in source_matches}
    nodes, edges = {}, Counter()
    counts = Counter()
    stages = Counter()
    samples, milestones = [], []
    stride = 1
    sequence = 0
    phase = "runtime"
    tick = 0
    hook_first = set()
    return_match = False
    start = 0
    max_samples = 650

    def rel(frame):
        return Path(frame.f_code.co_filename).relative_to(source).as_posix()

    def mark(frame, kind, description=""):
        return {
            "seq": sequence, "kind": kind, "phase": phase,
            "node": _path_id(rel(frame), frame.f_code.co_firstlineno, frame.f_code.co_name),
            "file": rel(frame), "line": frame.f_code.co_firstlineno,
            "fn": frame.f_code.co_name,
            "ms": round((time.perf_counter() - start) * 1000, 2),
            "description": description,
        }

    def profile(frame, event, arg):
        nonlocal sequence, stride, phase, tick, return_match
        pathname = frame.f_code.co_filename
        if not pathname.startswith(prefix):
            return
        if event == "call":
            tick += 1
            sequence += 1
            path = rel(frame)
            fn = frame.f_code.co_name
            node_id = _path_id(path, frame.f_code.co_firstlineno, fn)
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id, "file": path, "line": frame.f_code.co_firstlineno,
                    "name": fn, "group": group_for(path), "kind": "function",
                }
            counts[node_id] += 1
            parent = frame.f_back
            depth = 0
            while parent and depth < 40 and not parent.f_code.co_filename.startswith(prefix):
                parent = parent.f_back
                depth += 1
            if parent and parent.f_code.co_filename.startswith(prefix):
                parent_path = rel(parent)
                parent_id = _path_id(parent_path, parent.f_code.co_firstlineno, parent.f_code.co_name)
                if parent_id not in nodes:
                    nodes[parent_id] = {
                        "id": parent_id, "file": parent_path,
                        "line": parent.f_code.co_firstlineno,
                        "name": parent.f_code.co_name,
                        "group": group_for(parent_path), "kind": "function",
                    }
                edges[(parent_id, node_id)] += 1

            new_stage = None
            if path.startswith("bot/modules/") and fn in ("observe", "respond", "after"):
                new_stage = fn
            elif path == arbiter_file and fn == "choose":
                new_stage = "choose"
            elif path == "bot/runtime.py" and fn == "_choose":
                new_stage = "choose"
            if new_stage:
                phase = new_stage
                stages[phase] += 1
                if phase not in hook_first:
                    hook_first.add(phase)
                    milestones.append(mark(frame, "phase", "公式hookの処理段階"))
            if path == module_file and fn == "respond":
                milestones.append(mark(frame, "selected", "最終的に採択された候補モジュール"))
            if path == arbiter_file and fn == "choose":
                milestones.append(mark(frame, "arbiter", "回答選択器の呼び出し"))
            if path == "bot/runtime.py" and fn == "turn":
                phase = "runtime"
                milestones.append(mark(frame, "start", "PyBot公式runtime.turnの開始"))
            frame_data = mark(frame, "call")
            if tick % stride == 0:
                samples.append(frame_data)
            if len(samples) > max_samples:
                samples[:] = samples[::2]
                stride *= 2
        elif event == "return" and pathname.startswith(prefix):
            path = rel(frame)
            fn = frame.f_code.co_name
            if path == module_file and fn == "respond" and isinstance(arg, str):
                if " ".join(arg.split()) == " ".join(str(expected_reply).split()):
                    sequence += 1
                    return_match = True
                    milestones.append(mark(frame, "answer_candidate", "最終回答と同じ候補文を返した"))
            elif path == arbiter_file and fn == "choose":
                sequence += 1
                milestones.append(mark(frame, "choice", "候補の選択処理が返った"))
            elif path == "bot/runtime.py" and fn == "turn" and isinstance(arg, dict):
                sequence += 1
                phase = "after"
                milestones.append(mark(frame, "final", "PyBotが最終回答を返した"))

    with _LOCK:
        prior_rng = random.getstate()
        prior_profile = sys.getprofile()
        actual = None
        try:
            random.seed(seed)
            replay_memory = {}
            for index, sentence in enumerate(inputs):
                if index == len(inputs) - 1:
                    start = time.perf_counter()
                    sys.setprofile(profile)
                try:
                    actual = runtime.turn(sentence, replay_memory)
                finally:
                    sys.setprofile(prior_profile)
        finally:
            random.setstate(prior_rng)
            sys.setprofile(prior_profile)

    actual_reply = " ".join(str((actual or {}).get("reply", "")).split())
    match = actual_reply == " ".join(str(expected_reply).split()) and (
        (actual or {}).get("module") == selected_module)
    milestones = [item for item in milestones if item["kind"] != "start"][:220] + [
        item for item in milestones if item["kind"] == "start"]
    # Give important stages, selected answer and actual last return preference.
    records = {item["seq"]: item for item in samples}
    records.update({item["seq"]: item for item in milestones})
    ordered = sorted(records.values(), key=lambda e: e["seq"])
    protected = [item for item in ordered if item["kind"] != "call"]
    ordinary = [item for item in ordered if item["kind"] == "call"]
    room = max(0, MAX_TIMELINE - len(protected))
    if len(ordinary) > room:
        stride = max(1, (len(ordinary) + max(1, room) - 1) // max(1, room))
        ordinary = ordinary[::stride][:room]
    frames = sorted(protected + ordinary, key=lambda e: e["seq"])

    # The important nodes include actual timeline events, selected module,
    # official runtime and any code co-located with an exact answer literal.
    required = {e["node"] for e in frames if e["kind"] != "call"}
    required.update(node_id for node_id, node in nodes.items()
                    if node["file"] in important_files or
                    (node["file"] == module_file and node["name"] == "respond") or
                    (node["file"] == "bot/runtime.py" and node["name"] == "turn"))
    high_degree = Counter()
    for (left,right),count in edges.items():
        high_degree[left] += count
        high_degree[right] += count
    ranked = sorted(nodes, key=lambda n: (
        n not in required, -high_degree[n], -counts[n], n))
    selected_ids = set(ranked[:MAX_NODES])
    clipped_nodes = [dict(nodes[n], calls=counts[n]) for n in ranked if n in selected_ids]
    chosen_edges = sorted(
        ((left,right,c) for (left,right),c in edges.items()
         if left in selected_ids and right in selected_ids and left != right),
        key=lambda x: -x[2])[:MAX_EDGES]
    graph_edges = [{"source":a,"target":b,"calls":c,"type":"observed"}
                   for a,b,c in chosen_edges]
    # Preserve chronology even when a particular node was omitted from graph.
    return {
        "graph": {"nodes":clipped_nodes,"edges":graph_edges,
                  "observed_node_count":len(nodes),"observed_edge_count":len(edges),
                  "omitted_nodes":max(0,len(nodes)-len(clipped_nodes)),
                  "omitted_edges":max(0,len(edges)-len(graph_edges))},
        "frames":frames,
        "source_matches":source_matches,
        "call_count":tick,"phase_counts":dict(stages),
        "selected_module":selected_module,
        "replay_module":(actual or {}).get("module"),
        "replay_reply":actual_reply,"replay_equal":match,
        "candidate_return_matched":return_match,
        "elapsed_ms":round((time.perf_counter()-start)*1000),
        "method":"sys.setprofileによる別メモリ再実行の関数呼出し観測。静的回答ソース照合とは別です。",
        "warning":"" if match else "再実行と元回答が異なるため、元の実行経路と断定できません。"
    }


def static_system(source):
    """Read code with AST, never execute it. Static arrows are dependencies."""
    source = Path(source).resolve()
    bot = source / "bot"
    groups = {name:{"files":0,"lines":0,"functions":0} for name in ROOT_GROUPS}
    per_file = []
    connections = Counter()
    degree = Counter()
    for path in sorted(bot.rglob("*.py")):
        relative = path.relative_to(source).as_posix()
        cat = group_for(relative)
        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        lines = len(contents.splitlines())
        try:
            syntax = ast.parse(contents, filename=relative)
        except (SyntaxError, MemoryError, RecursionError):
            syntax = None
        functions = 0
        if syntax is not None:
            for node in ast.walk(syntax):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions += 1
                if isinstance(node, ast.ImportFrom):
                    if node.level and node.module:
                        pieces = node.module.split(".")
                        # from ..memory import / from bot.memory import
                        target = pieces[0] if pieces[0] in ROOT_GROUPS else (
                            pieces[1] if len(pieces)>1 and pieces[0]=="bot" else "")
                    else:
                        raw = (node.module or "").split(".")
                        target = raw[1] if len(raw)>1 and raw[0]=="bot" else ""
                    if target in ROOT_GROUPS and target != cat:
                        connections[(cat,target)] += 1
                        degree[relative] += 1
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        target = parts[1] if len(parts)>1 and parts[0]=="bot" else ""
                        if target in ROOT_GROUPS and target != cat:
                            connections[(cat,target)] += 1
                            degree[relative] += 1
        groups[cat]["files"] += 1
        groups[cat]["lines"] += lines
        groups[cat]["functions"] += functions
        per_file.append({"id":"file:"+relative,"file":relative,
                         "group":cat,"lines":lines,"functions":functions,
                         "dependence_count":degree[relative]})
    cluster_nodes = [{"id":"group:"+name,"name":name,"group":name,**data,"kind":"group"}
                     for name,data in groups.items()]
    group_edges = [{"source":"group:"+a,"target":"group:"+b,
                    "calls":v,"type":"static_import"}
                   for (a,b),v in connections.most_common()]
    # File map: representative high-degree/large files, always include known hubs.
    ranked = sorted(per_file, key=lambda x:(
        -x["dependence_count"],-x["lines"],x["file"]))
    forced = ["bot/runtime.py","bot/modules/arbiter.py",
              "bot/modules/answers.py","bot/knowledge/maths.py"]
    prioritized = [f for f in per_file if f["file"] in forced]
    seen = {f["id"] for f in prioritized}
    file_nodes = (prioritized + [f for f in ranked if f["id"] not in seen])[:85]
    # Real file-to-file Python import edges: unlike mere group membership,
    # these are AST-supported dependencies. They do NOT claim a runtime call.
    chosen_paths={f["file"] for f in file_nodes}
    file_imports=Counter()

    def existing_module(parts):
        if not parts or parts[0]!="bot":
            return None
        path="/".join(parts)
        for candidate in (path+".py",path+"/__init__.py"):
            if candidate in chosen_paths:
                return candidate
        return None

    for record in file_nodes:
        source_path=record["file"]
        try:
            syntax=ast.parse((source/source_path).read_text(encoding="utf-8"))
        except (SyntaxError,OSError,UnicodeError,RecursionError):
            continue
        for item in ast.walk(syntax):
            targets=set()
            if isinstance(item,ast.Import):
                for entry in item.names:
                    found=existing_module(entry.name.split("."))
                    if found:
                        targets.add(found)
            elif isinstance(item,ast.ImportFrom):
                package=source_path[:-3].split("/")[:-1]
                if item.level:
                    for _ in range(item.level-1):
                        if len(package)>1:
                            package.pop()
                    module_path=package+((item.module or "").split(".") if item.module else [])
                else:
                    module_path=(item.module or "").split(".")
                resolved=existing_module(module_path)
                if resolved:
                    targets.add(resolved)
                for entry in item.names:
                    if entry.name=="*":
                        continue
                    child=existing_module(module_path+entry.name.split("."))
                    if child:
                        targets.add(child)
            for target in targets:
                if target!=source_path:
                    file_imports[(source_path,target)]+=1
    import_edges=[{"source":"file:"+source_path,"target":"file:"+target,
                   "calls":count,"type":"static_import"}
                  for (source_path,target),count in file_imports.most_common()]

    # Group membership is represented separately, never as an import.
    membership = [{"source":"group:"+f["group"],"target":f["id"],
                   "calls":f["lines"],"type":"member"} for f in file_nodes]
    return {
        "groups":{"nodes":cluster_nodes,"edges":group_edges},
        "files":{"nodes":cluster_nodes+file_nodes,
                 "edges":group_edges+membership+import_edges},
        "total":{"files":sum(x["files"] for x in groups.values()),
                 "lines":sum(x["lines"] for x in groups.values()),
                 "functions":sum(x["functions"] for x in groups.values())},
        "method":"Python ASTから静的構造を抽出。import線は呼び出しの証拠ではありません。",
        "pinned_source":"7d63c7fbebb44c7e466e5c8b5c1f341ab767929e"
    }
