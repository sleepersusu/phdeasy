"""應用程式自己的視窗（做法同雅思練習室）：Windows 用 Edge（沒有就 Chrome）的 App 模式開成獨立視窗，
沒有網址列與分頁；關掉視窗＝結束程式。找不到 Edge／Chrome 就退回一般瀏覽器。"""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def find_app_browser(env=None):
    env = env if env is not None else os.environ
    rels = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    for base in (env.get("ProgramFiles(x86)"), env.get("ProgramFiles"), env.get("LOCALAPPDATA")):
        for rel in rels:
            exe = Path(base, *rel.split("\\")) if base else None
            if exe and exe.exists():
                return str(exe)
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return next((p for p in mac if Path(p).exists()), None)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppWindow:
    def __init__(self, exe, url, profile_root, title="教授研究檔案"):
        self.exe, self.url, self.title = exe, url, title
        self.port = _free_port()
        root = Path(profile_root)
        self.profile = root / str(int(time.time()))  # 每次新的設定資料夾：拿到自己的 Edge 行程，關得掉也看得到
        try:
            root.mkdir(parents=True, exist_ok=True)
            for d in root.iterdir():
                if d != self.profile:
                    shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
        self.proc = None

    def open(self):
        self.proc = subprocess.Popen([self.exe, f"--app={self.url}", f"--user-data-dir={self.profile}", "--no-first-run",
                                      "--no-default-browser-check", "--window-size=1360,900", "--disable-sync",
                                      "--disable-background-mode", f"--remote-debugging-port={self.port}"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def pages(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=2) as r:
                return [t for t in json.loads(r.read() or b"[]") if t.get("type") == "page"]
        except (OSError, ValueError):
            return None

    def wait_closed(self, alive=lambda: True, poll=1.0):
        """視窗關掉（連續 3 秒沒有頁面，或行程結束）就回來；alive() 變 False（例：伺服器停了）也回來。"""
        seen, gone = False, 0
        while alive():
            time.sleep(poll)
            ps = self.pages()
            if ps:
                seen, gone = True, 0
            elif seen or (self.proc and self.proc.poll() is not None):
                gone += 1
                if gone >= 3:
                    return
        self.close()

    def close(self):
        for t in self.pages() or []:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/close/{t.get('id')}", timeout=2).read()
            except OSError:
                pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
