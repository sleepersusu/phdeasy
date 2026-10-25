"""教授研究檔案：雙擊打開的看資料應用程式（做法同雅思練習室）。

  uv run python scripts/app.py [runs] [--port 8790] [--no-browser]

1. 打開時：從 Google 雲端硬碟拉下別台電腦的更新，重建首頁與教授頁。
2. 用瀏覽器打開首頁（本人 CV → 教授比對 → 教授詳細頁）。
3. 開著的時候每 3 分鐘同步一次（也讓別台知道這台還在用）。
4. 關掉視窗或按 Ctrl+C：最後同步一次並釋放「使用中」，別台電腦就能接著用。

建新教授、停 1／停 2 的確認仍在 Claude Code 裡做；這裡只負責看資料與同步。
"""
import argparse
import atexit
import functools
import http.server
import signal
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import release

SYNC_EVERY = 180


def free_port(preferred, host="127.0.0.1"):
    """preferred 沒被佔用就用它，否則找一個空的。"""
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind((host, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("找不到可用的連接埠")


def rebuild(runs):
    from build_home import main as build_home_main
    argv = sys.argv
    try:
        sys.argv = ["build_home.py", str(runs)]
        build_home_main()  # 重建首頁與每位教授頁，結尾會同步雲端
    finally:
        sys.argv = argv


class Closer:
    """關掉時只做一次：最後同步並釋放使用中。"""

    def __init__(self, runs, sync=drive_sync, rel=release, tgt=target):
        self.runs, self.sync, self.rel, self.tgt, self.done = runs, sync, rel, tgt, False
        self.lock = threading.Lock()

    def __call__(self, *_):
        with self.lock:
            if self.done:
                return
            self.done = True
        print("\n正在關閉：最後同步一次並釋放使用中…")
        try:
            self.sync(self.runs)
            dst = self.tgt(self.runs)
            if dst and dst.exists():
                self.rel(dst)
        except Exception as e:  # 關閉時同步失敗不要卡住
            print(f"同步失敗：{e}")
        print("已關閉，可以關掉這個視窗。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default=str(Path(__file__).resolve().parent.parent / "runs"))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # 雙擊開的視窗要即時看到進度
    runs = Path(a.runs)
    runs.mkdir(exist_ok=True)

    print("從 Google 雲端硬碟同步…")
    if drive_sync(runs) == 2:
        print("另一台電腦還在用：這台先只看資料、不同步。那台關掉後重開這個程式。")
        closer = None
    else:
        closer = Closer(runs)
    print("重建首頁與教授頁…")
    rebuild(runs)

    port = free_port(a.port)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(runs))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"\n✅ 已打開：{url}\n   看資料時保持這個視窗開著；關掉視窗或按 Ctrl+C 就會同步並結束。\n")

    stop = threading.Event()
    if closer:
        atexit.register(closer)
        sigs = [signal.SIGINT, signal.SIGTERM] + [getattr(signal, n) for n in ("SIGHUP", "SIGBREAK") if hasattr(signal, n)]  # SIGBREAK：Windows 關視窗

        def on_signal(*_):
            if closer.done:  # 關閉中又收到訊號（例：uv 轉送一次）：不要打斷正在做的同步
                return
            for sg in sigs:
                signal.signal(sg, signal.SIG_IGN)
            closer()
            sys.exit(0)  # 訊號在主執行緒處理：結束 serve_forever
        for sg in sigs:
            signal.signal(sg, on_signal)

        def periodic():
            while not stop.wait(SYNC_EVERY):
                try:
                    drive_sync(runs)
                except Exception as e:
                    print(f"同步失敗：{e}")
        threading.Thread(target=periodic, daemon=True).start()

    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    finally:
        stop.set()
        srv.server_close()


if __name__ == "__main__":
    main()
