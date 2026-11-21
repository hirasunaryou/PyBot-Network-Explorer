#!/usr/bin/env python3
"""Mac/Windows one-click entrypoint; no venv and no pip install."""
import json
import os
import sys
import threading
import traceback
import urllib.request
import webbrowser

if sys.version_info < (3, 8):
    raise SystemExit("Python 3.8以上が必要です。https://www.python.org/downloads/")

from network.bootstrap import BootstrapError, ensure_upstream
from network.server import serve


def main():
    try:
        source=ensure_upstream()
        url,server=serve(source)
        if "--self-check" in sys.argv or os.getenv("PYBOT_NETWORK_SELF_CHECK")=="1":
            runner=threading.Thread(target=server.serve_forever,daemon=True)
            runner.start()
            try:
                for path in ("api/status","api/system","api/source?path=bot/runtime.py&line=1"):
                    with urllib.request.urlopen(url+path,timeout=90) as response:
                        result=json.load(response)
                    assert isinstance(result,dict) and "error" not in result
                print("PASS: Original PyBot, API, static graph and source browser")
            finally:
                server.shutdown()
                server.server_close()
            return 0
        print("PyBot Network Explorer: "+url)
        print("Mac / Windows · no GPU · no pip packages · no Python venv")
        print("閉じる場合はターミナルでCtrl+Cを押してください。")
        webbrowser.open(url)
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        print("\n終了しました。")
        return 0
    except BootstrapError as exc:
        print("PyBotの初回取得を完了できませんでした:\n"+str(exc),file=sys.stderr)
        return 1
    except Exception:
        print("起動できませんでした。以下のメッセージを確認してください。",file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__=="__main__":
    sys.exit(main())
