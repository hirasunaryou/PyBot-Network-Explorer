"""Loopback HTTP API for graph exploration; only Python's standard library."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
import traceback
from urllib.parse import parse_qs, urlsplit

from .bootstrap import PROJECT_ROOT, UPSTREAM_COMMIT
from .engine import Explorer, RequestError

STATIC=PROJECT_ROOT/"web"
DOCS=PROJECT_ROOT/"docs"
MAX_BODY=20*1024


class App:
    def __init__(self,source):
        self.source=Path(source)
        self.engine=None
        self.guard=threading.Lock()

    def explorer(self):
        if self.engine is None:
            with self.guard:
                if self.engine is None:
                    self.engine=Explorer(self.source)
        return self.engine

    def get(self,path,query):
        if path=="/api/status":
            return {"ready":True,"source":UPSTREAM_COMMIT,
                    "upstream":"https://github.com/huggingface/pybot",
                    "python_stdlib_only":True}
        if path=="/api/system":
            return self.explorer().system()
        if path=="/api/source":
            return self.explorer().source_code(
                query.get("path",[""])[0],
                query.get("line",["1"])[0],
                query.get("context",["34"])[0])
        raise RequestError("存在しないAPIです")

    def post(self,path,data):
        engine=self.explorer()
        session=data.get("session")
        if path=="/api/ask":
            return engine.ask(session,data.get("text"))
        if path=="/api/trace":
            return engine.trace(session,data.get("turn_index"))
        if path=="/api/reset":
            return engine.reset(session)
        raise RequestError("存在しないAPIです")


def handler_factory(app):
    class Handler(BaseHTTPRequestHandler):
        server_version="PyBotNetworkExplorer/1.0"

        def log_message(self,fmt,*args):
            # Avoid logging user-submitted conversations.
            return

        def respond(self,body,status=200,mime="application/json; charset=utf-8",docs=False):
            self.send_response(status)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Referrer-Policy","no-referrer")
            if docs:
                policy=("default-src 'none'; style-src 'unsafe-inline'; "
                        "img-src data: 'self'; object-src 'none'; base-uri 'none'")
            else:
                policy=("default-src 'self'; script-src 'self'; style-src 'self'; "
                        "img-src 'self' data:; connect-src 'self'; "
                        "object-src 'none'; base-uri 'none'")
            self.send_header("Content-Security-Policy",policy)
            self.end_headers()
            self.wfile.write(body)

        def send_json(self,data,status=200):
            self.respond(json.dumps(data,ensure_ascii=False).encode("utf-8"),status)

        def do_GET(self):
            uri=urlsplit(self.path)
            path=uri.path
            try:
                if path.startswith("/api/"):
                    self.send_json(app.get(path,parse_qs(uri.query)))
                    return
                if path=="/":
                    target=STATIC/"index.html"
                elif path.startswith("/web/"):
                    target=STATIC/path[len("/web/"):]
                elif path.startswith("/docs/"):
                    target=DOCS/path[len("/docs/"):]
                else:
                    self.send_json({"error":"ページがありません"},404)
                    return
                target=target.resolve()
                if not (target==STATIC.resolve()/"index.html" or
                        STATIC.resolve() in target.parents or
                        DOCS.resolve() in target.parents):
                    self.send_json({"error":"アクセスできないファイルです"},403)
                    return
                if not target.is_file():
                    self.send_json({"error":"ファイルがありません"},404)
                    return
                mime=mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if mime.startswith("text/") or mime=="application/javascript":
                    mime+="; charset=utf-8"
                is_manual=DOCS.resolve() in target.parents and target.suffix==".html"
                self.respond(target.read_bytes(),mime=mime,docs=is_manual)
            except (RequestError,ValueError,TypeError) as exc:
                self.send_json({"error":str(exc)},400)
            except Exception:
                traceback.print_exc()
                self.send_json({"error":"表示中に問題が起きました。ターミナルを確認してください"},500)

        def do_POST(self):
            try:
                size=int(self.headers.get("Content-Length","0"))
                if size<1 or size>MAX_BODY:
                    raise RequestError("入力サイズが上限を超えました")
                if not self.headers.get("Content-Type","").startswith("application/json"):
                    raise RequestError("JSON形式で送信してください")
                data=json.loads(self.rfile.read(size).decode("utf-8"))
                if not isinstance(data,dict):
                    raise RequestError("JSONオブジェクトが必要です")
                self.send_json(app.post(urlsplit(self.path).path,data))
            except (RequestError,ValueError,TypeError) as exc:
                self.send_json({"error":str(exc)},400)
            except Exception:
                traceback.print_exc()
                self.send_json({"error":"PyBotの処理に失敗しました。ターミナルを確認してください"},500)

    return Handler


def serve(source,port=0):
    app=App(source)
    server=ThreadingHTTPServer(("127.0.0.1",port),handler_factory(app))
    server.daemon_threads=True
    return "http://127.0.0.1:%d/"%server.server_address[1],server
