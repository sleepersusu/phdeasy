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
import json
import functools
import os
import http.server
import signal
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import find_drives, release

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


FROZEN = getattr(sys, "frozen", False)  # Windows 安裝版（PyInstaller）：沒有 repo，資料只從雲端硬碟來


def default_runs():
    if FROZEN:
        return Path.home() / "phdeasy" / "runs"
    return Path(__file__).resolve().parent.parent / "runs"


def choose_account(runs, drives=None, ask=input):
    """第一次打開且這台登入多個 Google 帳號：讓本人選一個，記在 runs/_me/drive.json（只在這台）。"""
    p = runs / "_me" / "drive.json"
    conf = json.loads(p.read_text()) if p.exists() else {}
    if conf.get("account") or conf.get("dir"):
        return conf.get("account")
    drives = find_drives() if drives is None else drives
    if len(drives) <= 1:
        return drives[0][0] if drives else None
    print("這台電腦登入了多個 Google 雲端硬碟帳號，要用哪一個放教授檔案？")
    for i, (label, path) in enumerate(drives, 1):
        print(f"  {i}. {label}")
    while True:
        ans = ask("輸入編號後按 Enter：").strip()
        if ans.isdigit() and 1 <= int(ans) <= len(drives):
            acct = drives[int(ans) - 1][0]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({**conf, "account": acct}, ensure_ascii=False, indent=1))
            return acct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default=str(default_runs()))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-rebuild", action="store_true", help="只用雲端同步下來的網頁，不重建（安裝版預設）")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # 雙擊開的視窗要即時看到進度
    runs = Path(a.runs)
    runs.mkdir(parents=True, exist_ok=True)
    choose_account(runs)

    print("從 Google 雲端硬碟同步…")
    if drive_sync(runs) == 2:
        print("另一台電腦還在用：這台先只看資料、不同步。那台關掉後重開這個程式。")
        closer = None
    else:
        closer = Closer(runs)
    if a.no_rebuild or FROZEN:  # 網頁由跑流水線的那台（Claude Code）建好、經雲端同步過來
        if not (runs / "index.html").exists():
            print("雲端還沒有教授檔案：先在裝了 Claude Code 的電腦建一位教授，再打開這裡。")
    else:
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
        if os.name == "nt":  # Windows 按右上角 X 關視窗不會送 Python 訊號：用主控台事件接（約 5 秒內要做完）
            import ctypes
            HANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def on_console(event):
                if event in (2, 5, 6):  # CTRL_CLOSE / LOGOFF / SHUTDOWN
                    closer()
                    return True
                return False
            main._console_handler = HANDLER(on_console)  # 留住參照，不然會被回收
            ctypes.windll.kernel32.SetConsoleCtrlHandler(main._console_handler, True)

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
