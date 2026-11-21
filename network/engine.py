"""One PyBot runtime, many isolated browser sessions. No extra Python packages."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import random
import re
import sys
import threading
import time

from .graph import trace_turn, static_system

_SESSION = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_LOCK = threading.RLock()


class RequestError(ValueError):
    pass


@dataclass
class Conversation:
    seed: int = 42
    memory: dict = field(default_factory=dict)
    rng: object = None
    turns: list = field(default_factory=list)
    traces: dict = field(default_factory=dict)


class Explorer:
    def __init__(self, source):
        self.source = Path(source).resolve()
        assert (self.source/"bot"/"runtime.py").is_file()
        if str(self.source) not in sys.path:
            sys.path.insert(0,str(self.source))
        from bot import runtime
        self.runtime = runtime
        self.sessions = {}
        self.lock = threading.Lock()
        self.system_cache = None

    def session(self, key, create=True):
        if not isinstance(key,str) or not _SESSION.fullmatch(key):
            raise RequestError("セッションIDが不正です")
        with self.lock:
            if key not in self.sessions:
                if not create:
                    raise RequestError("会話がありません。質問してから解析してください。")
                if len(self.sessions) >= 24:
                    self.sessions.pop(next(iter(self.sessions)))
                self.sessions[key] = Conversation()
            return self.sessions[key]

    def ask(self, session, text):
        if not isinstance(text,str) or not 0 < len(text.strip()) <= 1000:
            raise RequestError("質問は1〜1000文字で入力してください")
        current=self.session(session)
        if len(current.turns)>=60:
            raise RequestError("会話が60ターンに達しました。リセットして続けてください。")
        with _LOCK:
            before=random.getstate()
            try:
                if current.rng is None:
                    random.seed(current.seed)
                else:
                    random.setstate(current.rng)
                start=time.perf_counter()
                result=self.runtime.turn(text,current.memory)
                elapsed=round((time.perf_counter()-start)*1000,2)
                current.rng=random.getstate()
            finally:
                random.setstate(before)
            candidates=[{
                "module":c["module"],"priority":c["priority"],"reply":str(c["reply"])[:2200],
            } for c in (result.get("candidates") or [])[:160]]
            reply=str(result.get("reply") or "")
            chosen=result.get("module")
            index=next((i for i,c in enumerate(candidates)
                        if c["module"]==chosen and c["reply"]==reply),-1)
            item={
                "index":len(current.turns),"user":text,
                "reply":reply,"selected_module":chosen,
                "chosen_index":index,"candidates":candidates,
                "elapsed_ms":elapsed,
                "memory_keys":list(current.memory.keys())[:35]
            }
            current.turns.append(item)
            return item

    def trace(self, session, turn_index):
        if not isinstance(turn_index,int) or isinstance(turn_index,bool):
            raise RequestError("ターン番号が不正です")
        current=self.session(session,create=False)
        with _LOCK:
            if turn_index < 0 or turn_index>=len(current.turns):
                raise RequestError("選択した会話がありません")
            if turn_index in current.traces:
                return current.traces[turn_index]
            turn=current.turns[turn_index]
            inputs=[t["user"] for t in current.turns[:turn_index+1]]
            data=trace_turn(
                self.runtime,self.source,inputs,turn["reply"],turn["selected_module"],current.seed
            )
            # The chosen candidate and other candidates are OBSERVED from the
            # original turn; the replay graph itself has separate provenance.
            data["observed_answer"]={
                "input":turn["user"],"reply":turn["reply"],
                "module":turn["selected_module"],
                "candidates":turn["candidates"],
                "chosen_index":turn["chosen_index"],
                "elapsed_ms":turn["elapsed_ms"]
            }
            current.traces[turn_index]=data
            return data

    def reset(self, session):
        current=self.session(session,create=False)
        with _LOCK:
            current.memory={}
            current.rng=None
            current.turns.clear()
            current.traces.clear()
        return {"ok":True}

    def system(self):
        with _LOCK:
            if self.system_cache is None:
                self.system_cache=static_system(self.source)
            return self.system_cache

    def source_code(self, path, focus=1, context=24):
        if not isinstance(path,str) or not re.fullmatch(r"bot/[a-zA-Z_0-9/]+\.py",path):
            raise RequestError("ソースの指定が不正です")
        target=(self.source/path).resolve()
        if self.source not in target.parents or not target.is_file():
            raise RequestError("PyBot本体以外のソースは表示できません")
        try:
            focus=int(focus)
            context=int(context)
        except (TypeError,ValueError):
            raise RequestError("行番号が不正です")
        content=target.read_text(encoding="utf-8").splitlines()
        focus=max(1,min(focus,max(1,len(content))))
        context=max(8,min(context,70))
        first=max(1,focus-context//2)
        end=min(len(content),first+context-1)
        return {
            "path":path,"focus":focus,"start":first,"total":len(content),
            "lines":[{"line":i,"code":content[i-1]} for i in range(first,end+1)]
        }
