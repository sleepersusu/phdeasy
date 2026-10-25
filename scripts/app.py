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
import time
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import busy_elsewhere, device_id, find_drives, release
from pipeline.window import AppWindow, find_app_browser
from pipeline.jobs import (FULLTEXT_KINDS, REJUDGE_KINDS, UNATTENDED, Jobs, exception_actions, find_claude, prompt_continue,
                           prompt_exception, prompt_match, prompt_new)

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
    if ask is None:  # 視窗版：沒有主控台可以問，改在畫面上選（/api/account）
        return None
    print("這台電腦登入了多個 Google 雲端硬碟帳號，要用哪一個放教授檔案？")
    for i, (label, path) in enumerate(drives, 1):
        print(f"  {i}. {label}")
    while True:
        ans = ask("輸入編號後按 Enter：").strip()
        if ans.isdigit() and 1 <= int(ans) <= len(drives):
            return save_account(runs, drives[int(ans) - 1][0])


def save_account(runs, acct):
    p = runs / "_me" / "drive.json"
    conf = json.loads(p.read_text()) if p.exists() else {}
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
        self.closer = None
        self.syncing = True
        self.need_account, self.account_chosen = threading.Event(), threading.Event()
        self.drive_choices = []

    def after_job(self, job):
        try:
            rebuild(self.workspace)
        except Exception as e:
            print(f"重建失敗：{e}")

    def status(self):
        dst = target(self.runs)
        job = self.jobs.latest()
        other = busy_elsewhere(dst, device_id()) if dst and dst.exists() else None
        return {"syncing": self.syncing, "need_account": self.need_account.is_set() and not self.account_chosen.is_set(),
                "drive_choices": self.drive_choices,
                "claude": find_claude(), "uv": find_uv(), "drive": str(dst) if dst and dst.parent.exists() else None,
                "blocked": self.blocked or (other or {}).get("device"), "running": self.jobs.running(), "job": job,
                "log": self.jobs.log_tail(job["id"]) if job else [], "professors": professors(self.runs),
                "exception_actions": {k: exception_actions(k) for k in sorted(FULLTEXT_KINDS | REJUDGE_KINDS | {"grant_unresolved", "possible_author_split"})}}

    def upload(self, slug, wid, data, limit=200 * 1024 * 1024):
        """本人從畫面上放進來的全文 PDF：存進 runs/<slug>/inbox/（只新增、不覆蓋），之後「再找一次」會用上。"""
        import re as _re
        if not _re.fullmatch(r"[a-z0-9-]+", slug) or not _re.fullmatch(r"W\d+", wid):
            raise ValueError("教授或文章 id 不對")
        if not (self.runs / slug / "state.json").exists():
            raise ValueError(f"沒有這位教授：{slug}")
        if len(data) > limit or b"%PDF-" not in data[:1024]:
            raise ValueError("這不是 PDF 檔（或超過 200 MB）")
        inbox = self.runs / slug / "inbox"
        inbox.mkdir(exist_ok=True)
        dst, i = inbox / f"{wid}.pdf", 1
        while dst.exists():
            i += 1
            dst = inbox / f"{wid}-{i}.pdf"
        dst.write_bytes(data)
        return {"ok": True, "saved": dst.relative_to(self.runs).as_posix()}

    def post(self, path, body):
        if path == "account":
            acct = body.get("account")
            if acct not in self.drive_choices:
                raise ValueError("沒有這個帳號")
            save_account(self.runs, acct)
            self.account_chosen.set()
            return {"ok": True}
        if path in ("new", "continue", "reply", "match", "exception") and self.blocked:
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
        if path == "exception":
            slug = (body.get("slug") or "").strip()
            stp = self.runs / slug / "state.json"
            if not stp.exists():
                raise ValueError(f"沒有這位教授：{slug}")
            exc = next((e for e in json.loads(stp.read_text()).get("exceptions", [])
                        if e["id"] == body.get("id") and e["kind"] == body.get("kind") and not e.get("resolved")), None)
            if not exc:
                raise ValueError("找不到這筆未解決的例外（可能已經處理過，重新整理看看）")
            return self.jobs.start("exception", prompt_exception(slug, exc, body.get("action"), body.get("note") or ""),
                                   f"例外：{slug} {exc['id']}", slug=slug)
        if path == "match":
            slug = (body.get("slug") or "").strip()
            if not (self.runs / slug / "state.json").exists():
                raise ValueError(f"沒有這位教授：{slug}")
            return self.jobs.start("match", prompt_match(slug), f"重新比對：{slug}", slug=slug)
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

        def end_headers(self):
            if "/api/" not in self.path:
                self.send_header("Cache-Control", "no-cache")  # 更新版本或重建資料後，畫面不要用舊的快取
            super().end_headers()

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
            if self.path.startswith("/api/upload/"):
                try:
                    _, slug, wid = urlparse(self.path).path.rsplit("/", 2)
                    n = int(self.headers.get("Content-Length") or 0)
                    return self._json(200, app.upload(unquote(slug), unquote(wid), self.rfile.read(n)))
                except (ValueError, RuntimeError) as e:
                    return self._json(400, {"error": str(e)})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                return self._json(200, app.post(self.path[len("/api/"):], body))
            except KeyError:
                return self._json(404, {"error": "沒有這個功能"})
            except (ValueError, RuntimeError) as e:
                return self._json(400, {"error": str(e)})
    return Handler


def startup(app, choose=True):
    """背景做：選帳號（必要時等畫面上選）→ 同步雲端 → 重建資料。視窗先開，畫面顯示進度。"""
    try:
        if choose and app.need_account.is_set():
            app.account_chosen.wait()
        print("從 Google 雲端硬碟同步…")
        if drive_sync(app.runs, hold=True) == 2:
            app.blocked = (busy_elsewhere(target(app.runs), device_id()) or {}).get("device") or "另一台電腦"
            print("另一台電腦還在用：這台先只看資料（已拉下雲端的檔），不推上去，也先不要建新教授。")
        else:
            app.closer = Closer(app.runs)
        print("更新教授資料…")
        if not rebuild(app.workspace):
            print("（沒有 uv：先用雲端同步下來的資料；要在這台建新教授，首頁會引導你安裝）")
    except Exception as e:
        print(f"啟動同步失敗：{e}")
    finally:
        app.syncing = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(default_workspace()))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--browser", action="store_true", help="用一般瀏覽器開，不開成獨立視窗")
    ap.add_argument("--window", action="store_true", help="Mac 也開成獨立視窗（用 Chrome）")
    a = ap.parse_args()
    ws = Path(a.workspace)
    ws.mkdir(parents=True, exist_ok=True)
    if FROZEN and sys.stdout is None:  # 視窗版沒有主控台：訊息寫進 使用者\phdeasy\app.log
        sys.stdout = sys.stderr = open(ws / "app.log", "a", encoding="utf-8", buffering=1)
    else:
        sys.stdout.reconfigure(line_buffering=True)
    if FROZEN:
        bundle = Path(getattr(sys, "_MEIPASS", ".")) / "pipeline_src"
        version = (bundle / "VERSION").read_text().strip() if (bundle / "VERSION").exists() else "dev"
        if install_bundle(bundle, ws, version):
            print(f"已把流水線（{version}）放到 {ws}")
    app = App(ws)
    app.runs.mkdir(parents=True, exist_ok=True)
    os.environ["PHDEASY_HOLD"] = "1"  # 子程序（重建、Claude Code）同步時不要放開這台的使用中
    if not choose_account(app.runs, ask=None):
        drives = find_drives()
        if len(drives) > 1:
            app.drive_choices = [d[0] for d in drives]
            app.need_account.set()
    threading.Thread(target=startup, args=(app,), daemon=True).start()

    port = free_port(a.port)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/web/index.html"
    print(f"已打開：{url}")

    def close_all(*_):
        app.jobs.stop()
        if app.closer:
            app.closer()
    atexit.register(close_all)
    stop = threading.Event()

    def periodic():
        while not stop.wait(SYNC_EVERY):
            if app.syncing:
                continue
            try:
                drive_sync(app.runs, hold=not app.blocked)
            except Exception as e:
                print(f"同步失敗：{e}")
    threading.Thread(target=periodic, daemon=True).start()

    exe = None if (a.browser or a.no_browser) else find_app_browser()
    if exe and (FROZEN or os.name == "nt" or a.window):
        win = AppWindow(exe, url, ws / ".window")
        win.open()
        win.wait_closed()  # 關掉視窗＝結束：最後同步、釋放使用中、停掉正在跑的流水線
        stop.set()
        close_all()
        srv.shutdown()
        return
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print("保持這個視窗開著；關掉視窗或按 Ctrl+C 就會同步並結束（正在跑的流水線也會停，之後可按「繼續跑」）。")
    sigs = [signal.SIGINT, signal.SIGTERM] + [getattr(signal, n) for n in ("SIGHUP", "SIGBREAK") if hasattr(signal, n)]
    done = threading.Event()

    def on_signal(*_):
        if done.is_set():  # 關閉中又收到訊號（例：uv 轉送一次）：不要打斷正在做的同步
            return
        done.set()
        for sg in sigs:
            signal.signal(sg, signal.SIG_IGN)
        stop.set()
        close_all()
        sys.exit(0)
    for sg in sigs:
        signal.signal(sg, on_signal)
    if os.name == "nt":  # 主控台版按 X 關視窗：用主控台事件接（約 5 秒內要做完）
        import ctypes
        HANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        def on_console(event):
            if event in (2, 5, 6):
                close_all()
                return True
            return False
        main._console_handler = HANDLER(on_console)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(main._console_handler, True)
    try:
        while True:
            time.sleep(3600)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
