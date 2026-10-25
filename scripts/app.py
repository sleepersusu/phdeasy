"""教授研究檔案：雙擊打開的應用程式（做法同雅思練習室）。

  uv run python scripts/app.py [--port 8790] [--no-browser] [--workspace <資料夾>]

1. 打開時：從 Google 雲端硬碟拉下別台電腦的更新，有 uv 就重建各教授的資料。
2. 用瀏覽器打開首頁（web/index.html：本人 CV → 教授比對 → 教授詳細頁 web/professor.html）。
   網頁是做好的 HTML／JS，資料從 runs/ 的 JSON 讀，比對在瀏覽器裡算。
3. 首頁的「建新教授」：叫這台的 Claude Code 在背景跑流水線（pipeline/jobs.py），停點在畫面上回覆。
4. 開著的時候每 3 分鐘同步一次；關掉視窗或按 Ctrl+C：最後同步一次並釋放「使用中」。

工作區：開發時是 repo 本身；Windows 安裝版第一次打開會把內建的流水線（scripts、skills、web、CLAUDE.md…）
複製到「使用者\\phdeasy」，教授資料在「使用者\\phdeasy\\runs」。
"""
import argparse
import atexit
import functools
import http.server
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import busy_elsewhere, device_id, find_drives, release
from pipeline.jobs import UNATTENDED, Jobs, find_claude, prompt_continue, prompt_new

SYNC_EVERY = 180
FROZEN = getattr(sys, "frozen", False)  # Windows 安裝版（PyInstaller）
BUNDLE_PARTS = ["scripts", "web", "tests", ".claude", "CLAUDE.md", "CONTEXT.md", "README.md", "pyproject.toml", "uv.lock", ".python-version", "docs"]


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


def default_workspace():
    return Path.home() / "phdeasy" if FROZEN else Path(__file__).resolve().parent.parent


def install_bundle(src, workspace, version):
    """安裝版：內建的流水線複製到工作區（版本變了才覆蓋；runs/ 絕不動）。回傳是否有更新。"""
    src, workspace = Path(src), Path(workspace)
    mark = workspace / ".app_version"
    if mark.exists() and mark.read_text().strip() == version:
        return False
    workspace.mkdir(parents=True, exist_ok=True)
    for part in BUNDLE_PARTS:
        s, d = src / part, workspace / part
        if not s.exists():
            continue
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    mark.write_text(version)
    return True


def find_uv():
    cands = [shutil.which("uv"), str(Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv"))]
    return next((c for c in cands if c and Path(c).exists()), None)


def install_uv():
    """uv 官方安裝方式（astral.sh），裝在使用者資料夾，不用管理員權限。本人在畫面上按確認才會跑。"""
    if os.name == "nt":
        cmd = ["powershell", "-ExecutionPolicy", "ByPass", "-NoProfile", "-c", "irm https://astral.sh/uv/install.ps1 | iex"]
    else:
        cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and bool(find_uv()), (r.stderr or r.stdout)[-500:]


def rebuild(workspace):
    """用工作區的流水線重建各教授的 data.json 與首頁清單（結尾會同步雲端）。沒有 uv 就跳過。"""
    uv = find_uv()
    if not uv:
        return False
    r = subprocess.run([uv, "run", "python", "scripts/build_home.py", "runs"], cwd=str(workspace), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((r.stdout or r.stderr).strip()[-600:])
    return r.returncode == 0


def professors(runs):
    out = []
    for st_p in sorted(Path(runs).glob("*/state.json")):
        if st_p.parent.name.startswith("_"):
            continue
        try:
            st = json.loads(st_p.read_text())
        except ValueError:
            continue
        stage = st.get("stage")
        report = {"stop1": "stop1-report.md", "stop2": "stop2-report.md"}.get(stage)
        out.append({"slug": st_p.parent.name, "name": (st.get("professor") or {}).get("name"), "stage": stage,
                    "report": report if report and (st_p.parent / report).exists() else None})
    return out


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


class App:
    """伺服器狀態：工作區、雲端、背景工作。"""

    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.runs = self.workspace / "runs"
        self.web = self.workspace / "web"
        self.jobs = Jobs(self.workspace, self.runs)
        self.jobs.on_done = self.after_job
        self.blocked = None

    def after_job(self, job):
        try:
            rebuild(self.workspace)
        except Exception as e:
            print(f"重建失敗：{e}")

    def status(self):
        dst = target(self.runs)
        job = self.jobs.latest()
        other = busy_elsewhere(dst, device_id()) if dst and dst.exists() else None
        return {"claude": find_claude(), "uv": find_uv(), "drive": str(dst) if dst and dst.parent.exists() else None,
                "blocked": self.blocked or (other or {}).get("device"), "running": self.jobs.running(), "job": job,
                "log": self.jobs.log_tail(job["id"]) if job else [], "professors": professors(self.runs)}

    def post(self, path, body):
        if path in ("new", "continue", "reply") and self.blocked:
            raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑流水線；那台關掉後重開這個程式")
        if path == "new":
            name, inst = (body.get("name") or "").strip(), (body.get("institution") or "").strip()
            if not name or not inst:
                raise ValueError("姓名和學校都要填")
            return self.jobs.start("new", prompt_new(name, inst, body.get("orcid")), f"建檔：{name}")
        if path == "continue":
            slug = (body.get("slug") or "").strip()
            if not (self.runs / slug / "state.json").exists():
                raise ValueError(f"沒有這位教授：{slug}")
            return self.jobs.start("continue", prompt_continue(slug), f"繼續：{slug}", slug=slug)
        if path == "reply":
            last = self.jobs.latest()
            if not last or not last.get("session"):
                raise ValueError("沒有可以接續的對話，請改按「繼續跑」")
            text = (body.get("text") or "").strip()
            if not text:
                raise ValueError("回覆是空的")
            return self.jobs.start("reply", text + "\n" + UNATTENDED, f"回覆：{last['title'].split('：', 1)[-1]}", session=last["session"], slug=last.get("slug"))
        if path == "stop":
            return {"stopped": self.jobs.stop()}
        if path == "install-uv":
            ok, msg = install_uv()
            return {"ok": ok, "error": None if ok else msg}
        raise KeyError(path)


def make_handler(app):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def translate_path(self, path):
            p = unquote(urlparse(path).path)
            for prefix, root in (("/web/", app.web), ("/runs/", app.runs)):
                if p.startswith(prefix):
                    full = (root / p[len(prefix):]).resolve()
                    if root.resolve() in full.parents or full == root.resolve():
                        return str(full)
            return str(app.web / "__missing__")

        def do_GET(self):
            if urlparse(self.path).path in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", "/web/index.html")
                self.end_headers()
                return
            if self.path.startswith("/api/status"):
                return self._json(200, app.status())
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/api/") or self.headers.get("X-Phdeasy-App") != "1":  # 擋其他網站偷送請求
                return self._json(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                return self._json(200, app.post(self.path[len("/api/"):], body))
            except KeyError:
                return self._json(404, {"error": "沒有這個功能"})
            except (ValueError, RuntimeError) as e:
                return self._json(400, {"error": str(e)})
    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(default_workspace()))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # 雙擊開的視窗要即時看到進度
    ws = Path(a.workspace)
    if FROZEN:
        bundle = Path(getattr(sys, "_MEIPASS", ".")) / "pipeline_src"
        version = (bundle / "VERSION").read_text().strip() if (bundle / "VERSION").exists() else "dev"
        if install_bundle(bundle, ws, version):
            print(f"已把流水線（{version}）放到 {ws}")
    app = App(ws)
    app.runs.mkdir(parents=True, exist_ok=True)
    choose_account(app.runs)

    print("從 Google 雲端硬碟同步…")
    if drive_sync(app.runs) == 2:
        app.blocked = (busy_elsewhere(target(app.runs), device_id()) or {}).get("device") or "另一台電腦"
        print("另一台電腦還在用：這台先只看資料、不同步，也先不要建新教授。那台關掉後重開這個程式。")
        closer = None
    else:
        closer = Closer(app.runs)
    print("更新教授資料…")
    if not rebuild(ws):
        print("（沒有 uv：先用雲端同步下來的資料；要在這台建新教授，首頁會引導你安裝）")

    port = free_port(a.port)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{port}/web/index.html"
    print(f"\n✅ 已打開：{url}\n   保持這個視窗開著；關掉視窗或按 Ctrl+C 就會同步並結束（正在跑的流水線也會停，之後可按「繼續跑」）。\n")

    stop = threading.Event()
    if closer:
        def close_all(*_):
            app.jobs.stop()
            closer()
        atexit.register(close_all)
        sigs = [signal.SIGINT, signal.SIGTERM] + [getattr(signal, n) for n in ("SIGHUP", "SIGBREAK") if hasattr(signal, n)]  # SIGBREAK：Windows 關視窗

        def on_signal(*_):
            if closer.done:  # 關閉中又收到訊號（例：uv 轉送一次）：不要打斷正在做的同步
                return
            for sg in sigs:
                signal.signal(sg, signal.SIG_IGN)
            close_all()
            sys.exit(0)  # 訊號在主執行緒處理：結束 serve_forever
        for sg in sigs:
            signal.signal(sg, on_signal)
        if os.name == "nt":  # Windows 按右上角 X 關視窗不會送 Python 訊號：用主控台事件接（約 5 秒內要做完）
            import ctypes
            HANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def on_console(event):
                if event in (2, 5, 6):  # CTRL_CLOSE / LOGOFF / SHUTDOWN
                    close_all()
                    return True
                return False
            main._console_handler = HANDLER(on_console)  # 留住參照，不然會被回收
            ctypes.windll.kernel32.SetConsoleCtrlHandler(main._console_handler, True)

        def periodic():
            while not stop.wait(SYNC_EVERY):
                try:
                    drive_sync(app.runs)
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
