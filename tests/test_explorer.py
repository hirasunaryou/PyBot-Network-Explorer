"""Offline, standard-library-only tests. Uses a tiny fixture only in tests."""
import json
import random
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from network.engine import Explorer, RequestError
from network.graph import group_for, static_system
from network.server import serve


RUNTIME = '''from .modules import greeting, arbiter
from .knowledge import maths

def turn(text, memory):
    greeting.observe(text, memory)
    reply = greeting.respond(text, memory)
    alt = maths.solve(text)
    candidates = [
        {"module":"greeting","reply":reply,"priority":50},
        {"module":"maths","reply":alt,"priority":10},
    ]
    winner = arbiter.choose(text, memory, candidates)
    choice = candidates[winner]
    greeting.after(text, choice["reply"], memory)
    memory.setdefault("turns", []).append({"user":text,"bot":choice["reply"],"module":choice["module"]})
    return {"reply":choice["reply"],"module":choice["module"],"candidates":candidates}
'''
GREETING = '''PRIORITY=50
def observe(text, memory):
    memory.setdefault("seen", []).append(text)
def respond(text, memory):
    return "Hello, I can answer that."
def after(text, reply, memory):
    memory["last"] = reply
'''
ARBITER = '''def choose(text, memory, candidates):
    return 1 if "mean" in text.lower() else 0
'''
MATHS = '''_AVERAGE_EXPLAIN = ("The mean is an average formed by adding the numbers "
                    "and dividing by the number of observations in the sample.")
def solve(text):
    return _AVERAGE_EXPLAIN
'''


class ExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        files={
            "bot/__init__.py":"",
            "bot/runtime.py":RUNTIME,
            "bot/modules/__init__.py":"",
            "bot/modules/greeting.py":GREETING,
            "bot/modules/arbiter.py":ARBITER,
            "bot/knowledge/__init__.py":"",
            "bot/knowledge/maths.py":MATHS,
        }
        for name,text in files.items():
            file=self.root/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(text,encoding="utf-8")
        for name in list(sys.modules):
            if name=="bot" or name.startswith("bot."):
                del sys.modules[name]
        self.explorer=Explorer(self.root)

    def test_first_answer_candidates_and_selection(self):
        r=self.explorer.ask("test_session_0001","Do you know mean?")
        self.assertEqual(r["selected_module"],"maths")
        self.assertEqual(r["chosen_index"],1)
        self.assertEqual(len(r["candidates"]),2)
        self.assertIn("The mean",r["reply"])
        self.assertEqual(self.explorer.session("test_session_0001").memory["seen"][0],
                         "Do you know mean?")

    def test_dynamic_replay_is_bounded_and_does_not_mutate(self):
        self.explorer.ask("test_session_0002","Do you know mean?")
        before=json.dumps(self.explorer.session("test_session_0002").memory,sort_keys=True)
        rng=random.getstate()
        trace=self.explorer.trace("test_session_0002",0)
        self.assertTrue(trace["replay_equal"],trace["warning"])
        self.assertEqual(trace["selected_module"],"maths")
        self.assertGreater(trace["call_count"],2)
        self.assertGreater(len(trace["graph"]["nodes"]),0)
        self.assertGreater(len(trace["graph"]["edges"]),0)
        self.assertTrue(any(e["type"]=="observed" for e in trace["graph"]["edges"]))
        self.assertIn("observe",trace["phase_counts"])
        self.assertIn("respond",trace["phase_counts"])
        self.assertIn("choose",trace["phase_counts"])
        self.assertIn("after",trace["phase_counts"])
        self.assertLessEqual(len(trace["frames"]),360)
        self.assertEqual(trace["frames"][0]["kind"],"start")
        self.assertEqual(trace["frames"][-1]["kind"],"final")
        self.assertTrue(trace["candidate_return_matched"] is False)
        self.assertTrue(trace["source_matches"][0]["exact"])
        self.assertEqual(trace["source_matches"][0]["symbol"],"_AVERAGE_EXPLAIN")
        self.assertEqual(json.dumps(self.explorer.session("test_session_0002").memory,sort_keys=True),before)
        self.assertEqual(random.getstate(),rng)
        self.assertIs(self.explorer.trace("test_session_0002",0),trace)

    def test_static_is_separate_from_execution(self):
        r=static_system(self.root)
        self.assertGreaterEqual(r["total"]["files"],7)
        self.assertTrue(all(e["type"]=="static_import" for e in r["groups"]["edges"]))
        self.assertTrue(all(e["type"] in ("static_import","member") for e in r["files"]["edges"]))
        self.assertTrue(any(
            e["source"]=="file:bot/runtime.py" and
            e["target"]=="file:bot/modules/greeting.py" and
            e["type"]=="static_import"
            for e in r["files"]["edges"]
        ), "File import arrows should come from real AST import statements")
        self.assertTrue(any(n["name"]=="modules" for n in r["groups"]["nodes"]))
        self.assertEqual(group_for("bot/modules/arbiter.py"),"arbiter")
        self.assertEqual(group_for("bot/knowledge/maths.py"),"knowledge")

    def test_source_and_bad_path_handling(self):
        result=self.explorer.source_code("bot/knowledge/maths.py",focus=2)
        self.assertEqual(result["path"],"bot/knowledge/maths.py")
        self.assertGreaterEqual(result["total"],3)
        with self.assertRaises(RequestError):
            self.explorer.source_code("bot/../../etc/passwd.py")
        with self.assertRaises(RequestError):
            self.explorer.ask("short","hello")
        with self.assertRaises(RequestError):
            self.explorer.trace("test_session_0003",0)
        self.explorer.ask("test_session_0003","hello")
        with self.assertRaises(RequestError):
            self.explorer.trace("test_session_0003",500)
        self.assertTrue(self.explorer.reset("test_session_0003")["ok"])

    def test_local_http_routes_and_security(self):
        url,server=serve(self.root)
        runner=threading.Thread(target=server.serve_forever,daemon=True)
        runner.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def get(path):
            with urlopen(url+path,timeout=15) as response:
                return response, response.read()
        def post(path,data):
            req=Request(url+"api/"+path,data=json.dumps(data).encode("utf-8"),
                        headers={"Content-Type":"application/json"})
            with urlopen(req,timeout=15) as response:
                return json.load(response)
        status=json.loads(get("api/status")[1])
        self.assertTrue(status["python_stdlib_only"])
        system=json.loads(get("api/system")[1])
        self.assertEqual(system["total"]["files"],7)
        self.assertIn(b"NETWORK",get("")[1])
        self.assertIn(b"graph-node",get("web/style.css")[1])
        answer=post("ask",{"session":"http_session_01","text":"Tell me mean"})
        self.assertEqual(answer["selected_module"],"maths")
        graph=post("trace",{"session":"http_session_01","turn_index":0})
        self.assertTrue(graph["replay_equal"])
        self.assertGreater(len(graph["frames"]),0)
        code=json.loads(get("api/source?path=bot/knowledge/maths.py&line=1")[1])
        self.assertEqual(code["path"],"bot/knowledge/maths.py")
        self.assertTrue(post("reset",{"session":"http_session_01"})["ok"])

    def test_utf8_pages(self):
        root=Path(__file__).resolve().parents[1]
        for name in ("web/index.html","web/style.css","web/app.js","README.md"):
            with self.subTest(name=name):
                value=(root/name).read_text(encoding="utf-8",errors="strict")
                self.assertNotIn("\ufffd",value)
                self.assertNotIn("\x00",value)
        self.assertIn('charset="utf-8"',(root/"web/index.html").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
