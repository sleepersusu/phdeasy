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
import html
import http.server
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

# Windows 中文版預設編碼是 cp950：腳本裡沒寫 encoding 的讀寫會讀壞 UTF-8 的 JSON、印不出某些字。
# 應用程式叫的每個子程序（腳本、Claude Code 再叫的腳本）都繼承這個設定，一律用 UTF-8。
os.environ["PYTHONUTF8"] = "1"


def hide_console_windows(sp):
    """照 ieltsgod：Windows 上背景跑的指令（測試 AI、換模型、跑腳本、Claude Code）不要每次都跳出黑色終端機視窗。
    只加 CREATE_NO_WINDOW（只影響終端機程式）；已經指定 creationflags 的（登入要開看得到的新視窗、自動更新）不動。"""
    init = sp.Popen.__init__

    def hidden(self, *a, **k):
        if "creationflags" not in k:
            k["creationflags"] = 0x08000000
        init(self, *a, **k)
    sp.Popen.__init__ = hidden


if os.name == "nt":
    hide_console_windows(subprocess)

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import busy_elsewhere, device_id, find_drives, release
from pipeline.window import AppWindow, find_app_browser
from pipeline.jobs import (FULLTEXT_KINDS, REJUDGE_KINDS, UNATTENDED, Jobs, exception_actions, find_claude, find_codex, prompt_continue, prompt_deep, prompt_faculty, prompt_programs, slug_of,
                           prompt_discover_enrich, prompt_doc_edit, prompt_doc_translate, prompt_exception, prompt_library_draft, prompt_library_process, prompt_match, prompt_propose, prompt_new)

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
        self.jobs.engine = self.engine  # 背景工作用哪個 AI：Claude Code（預設）或 Codex（備用）
        self.codex_test = None
        self.port = 8790
        self._rebuild_lock = threading.Lock()
        self.queue = self._load_queue()  # 同時已有 3 個工作在跑時先排隊，有空位就自動開始；存成檔，重開程式還在
        self._prog_samples = {}  # {工作 id: {步驟: (第一次看到的時間, 當時做完幾項)}}
        self.gcal_pending = None
        from pipeline import ai as AI
        AI.configure(self.runs)  # AI 小幫手（照 ieltsgod）：設定存在 runs/_app/ai.json，只在這台
        self.zh_jobs = {}  # 全文翻中文的背景工作：{(教授, 文章, 討論文獻?): {status, done, total, error}}
        self.jobs.on_done = self.after_job
        self.blocked = None
        self.closer = None
        self.syncing = True
        self.need_account, self.account_chosen = threading.Event(), threading.Event()
        self.drive_choices = []
        self.claude_test = None
        self.version = "dev"
        self.update_info = None
        self.quitting = threading.Event()  # 自動更新時設起來：關掉視窗、結束程式，讓安裝程式接手
        self.boot = {"steps": {k: {"state": "todo", "note": ""} for k, _ in BOOT_STEPS}, "labels": dict(BOOT_STEPS),
                     "order": [k for k, _ in BOOT_STEPS], "step": "drive", "sync": {}, "done": False}
        self.update_state = {"stage": "", "got": 0, "total": 0, "error": ""}

    def _queue_file(self):
        return self.runs / "_app" / "queue.json"

    def _load_queue(self):
        try:
            return json.loads(self._queue_file().read_text())
        except (OSError, ValueError):
            return []

    def _save_queue(self):
        p = self._queue_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.queue, ensure_ascii=False, indent=1))

    def start_or_queue(self, kind, prompt, title, slug=None, key=None):
        """有空位就開始；已有 3 個工作在跑就排隊（同一位教授已在跑則照樣回錯誤）。"""
        try:
            return self.jobs.start(kind, prompt, title, slug=slug, key=key)
        except RuntimeError as e:
            if "個工作在跑" not in str(e):
                raise
            if not any(q["title"] == title for q in self.queue):
                self.queue.append({"kind": kind, "prompt": prompt, "title": title, "slug": slug, "key": key})
                self._save_queue()
            return {"queued": True, "title": title, "position": len(self.queue)}

    def _drain_queue(self):
        while self.queue:
            q = self.queue[0]
            try:
                self.jobs.start(q["kind"], q["prompt"], q["title"], slug=q["slug"], key=q["key"])
            except RuntimeError as e:
                if "個工作在跑" in str(e):
                    return
                print(f"排隊的工作開不了：{q['title']}：{e}")
            self.queue.pop(0)
            self._save_queue()

    def _targets(self):
        p = self.runs / "_me" / "targets.json"
        return json.loads(p.read_text()) if p.exists() else {"schools": []}

    def _save_targets(self, t):
        p = self.runs / "_me" / "targets.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(t, ensure_ascii=False, indent=1))

    def after_job(self, job):
        try:
            self._drain_queue()
        except Exception as e:
            print(f"排隊處理失敗：{e}")
        try:
            with self._rebuild_lock:  # 好幾個工作同時跑完時，一次重建一個
                rebuild(self.workspace)
        except Exception as e:
            print(f"重建失敗：{e}")

    def status(self):
        dst = target(self.runs)
        job = self.jobs.latest()
        other = busy_elsewhere(dst, device_id()) if dst and dst.exists() else None
        return {"syncing": self.syncing, "need_account": self.need_account.is_set() and not self.account_chosen.is_set(),
                "drive_choices": self.drive_choices,
                "claude": find_claude(), "codex": find_codex(), "engine": self.engine(),
                "uv": find_uv(), "drive": str(dst) if dst and dst.parent.exists() else None,
                "blocked": self.blocked or (other or {}).get("device"), "running": self.jobs.running(), "job": job,
                "log": self.jobs.log_tail(job["id"]) if job else [], "professors": professors(self.runs),
                "exception_actions": {k: exception_actions(k) for k in sorted(FULLTEXT_KINDS | REJUDGE_KINDS | {"grant_unresolved", "possible_author_split", "external_candidates", "possible_duplicate", "affiliation_mismatch"})},
                "settings": self.settings(), "update": self.update_info, "version": self.version,
                "boot": self.boot, "update_state": self.update_state, "progress": self.job_progress(job), "jobs": self.job_list(),
                "queue": [q["title"] for q in self.queue]}

    def job_list(self):
        """工作進度頁：正在跑的全部，加上最近的（每位教授／每份文件只留最新一個，最多 15 個）；各自的紀錄與進度條。
        紀錄上寫 running、但不在這次開的程式裡跑的（程式中途關掉），當作中斷。"""
        act = self.jobs.active()
        ids = {j["id"] for j in act}
        seen, out = {j.get("key") for j in act}, list(act)
        for j in self.jobs.recent(40):
            k = j.get("key", j.get("slug") or j["kind"])
            if j["id"] in ids or k in seen or len(out) >= 15:
                continue
            seen.add(k)
            if j["status"] == "running":
                j = {**j, "status": "failed"}
            elif j["status"] == "done" and j.get("slug") and j["kind"] in ("new", "reply", "continue", "exception", "deep"):
                st_p = self.runs / j["slug"] / "state.json"  # 建檔停下（熔斷）不算跑完
                try:
                    if json.loads(st_p.read_text()).get("stage") == "halted":
                        j = {**j, "status": "halted"}
                except (OSError, ValueError):
                    pass
            out.append(j)
        return [{**{k: v for k, v in j.items() if k != "prompt"}, "running": j["id"] in ids,
                 "log": self.jobs.log_tail(j["id"], 80 if j["id"] in ids or j["status"] != "done" else 30),
                 "progress": self.job_progress(j) if j["id"] in ids else None} for j in out]

    def job_progress(self, job):
        """執行中的流水線工作：進度條與預估時間（看批次資料夾裡已產生的檔案；速度用這次輪詢量到的）。"""
        from pipeline.progress import estimate
        if not job or job.get("status") != "running" or job.get("kind") not in ("new", "reply", "continue", "exception", "deep"):
            return None
        slug = job.get("slug")
        if not slug:  # 新建檔時還不知道資料夾：用這個工作開始後最近有動的批次
            cands = [p for p in self.runs.glob("*/state.json") if not p.parent.name.startswith("_") and p.stat().st_mtime >= (job.get("started") or 0) - 60]
            if not cands:
                return None
            slug = max(cands, key=lambda p: p.stat().st_mtime).parent.name
        try:
            e = estimate(self.runs / slug, job["kind"], samples=self._prog_samples.get(job["id"]))
        except Exception:
            return None
        smp = self._prog_samples.setdefault(job["id"], {})
        cur = next((x for x in e["steps"] if x["key"] == e["current"]), None)
        if cur and cur["key"] not in smp:
            smp[cur["key"]] = (time.time(), cur["done"])
        return {"slug": slug, **e}

    def settings(self):
        """設定頁要顯示的：雲端帳號（這台偵測到的全部）、Claude Code 測試結果、金鑰有沒有設（不顯示內容）。"""
        p = self.runs / "_me" / "drive.json"
        conf = json.loads(p.read_text()) if p.exists() else {}
        drives = [d[0] for d in find_drives()]
        dst = target(self.runs)
        sec = self.runs / "_me" / "secrets.env"
        keys = {}
        if sec.exists():
            for line in sec.read_text(encoding="utf-8").splitlines():
                k, eq, v = line.partition("=")
                if eq and not line.lstrip().startswith("#"):
                    keys[k.strip()] = bool(v.strip().strip('"').strip("'"))
        return {"drives": drives, "account": conf.get("account") or (drives[0] if len(drives) == 1 else None),
                "folder": str(dst) if dst else None, "claude_test": self.claude_test, "codex_test": self.codex_test, "notion": self.notion_status(), "applicant": self._applicant(), "gcal": self.gcal_status(),
                "keys": {"S2_API_KEY": keys.get("S2_API_KEY", False) or bool(os.environ.get("S2_API_KEY"))},
                "workspace": str(self.workspace)}

    def _applicant(self):
        mep = self.runs / "_me" / "me.json"
        try:
            return json.loads(mep.read_text()).get("applicant") if mep.exists() else None
        except ValueError:
            return None

    def check_update(self):
        from pipeline.updater import check
        if self.version == "dev":  # 開發版（repo 直接跑）：用 git 更新，不自己下載安裝檔
            return None
        self.update_info = check(self.version)
        return self.update_info

    def do_update(self):
        """下載新版安裝檔（畫面顯示百分比）、安靜安裝；安裝程式等這個程式結束後才開始裝，裝完自動重開。"""
        info = self.update_info or self.check_update()
        if not info or not info.get("available"):
            raise ValueError("目前已經是最新版")
        if os.name != "nt":
            raise ValueError("自動更新只支援 Windows 安裝版；Mac 請用 git pull 更新")
        if self.jobs.running():
            raise ValueError("有工作在跑，等它跑完再更新")
        if self.update_state["stage"] in ("download", "install"):
            return {"ok": True, "already": True}
        self.update_state.update(stage="download", got=0, total=0, error="")
        threading.Thread(target=self._update_worker, args=(info,), daemon=True).start()
        return {"ok": True, "installing": info["latest"]}

    def _update_worker(self, info):
        from pipeline.updater import download
        st = self.update_state
        try:
            exe = download(info["release"], self.workspace / "update", progress=lambda g, t: st.update(got=g, total=t or 0))
            st["stage"] = "install"
            subprocess.Popen([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", f"/WAITPID={os.getpid()}", "/AUTOUPDATE=1"],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), close_fds=True)
            threading.Timer(1.5, self.quitting.set).start()  # 先讓畫面顯示「安裝中」，再結束程式
        except Exception as e:
            st.update(stage="", error=str(e)[:300])
            print(f"更新失敗：{e}")

    def switch_account(self, acct):
        """換雲端帳號：先放開舊雲端的使用中，記下新帳號，在背景重新同步（新雲端當第一次同步：只合併不刪）。"""
        if acct not in [d[0] for d in find_drives()]:
            raise ValueError("這台電腦沒有登入這個 Google 帳號")
        old = target(self.runs)
        if old and old.exists():
            release(old)
        save_account(self.runs, acct)
        self.account_chosen.set()
        self.resync()
        return {"ok": True}

    def resync(self):
        if self.syncing:
            return {"ok": True, "already": True}
        self.syncing, self.blocked = True, None
        threading.Thread(target=startup, args=(self, False), daemon=True).start()
        return {"ok": True}

    def _engine_file(self):
        return self.runs / "_app" / "engine.json"  # 只存在這台（_app 不同步）：每台可以各自選

    def engine(self):
        try:
            return json.loads(self._engine_file().read_text()).get("engine") or "claude"
        except (OSError, ValueError):
            return "claude"

    def set_engine(self, engine):
        if engine not in ("claude", "codex"):
            raise ValueError("AI 引擎只能是 Claude Code 或 Codex")
        self._engine_file().parent.mkdir(parents=True, exist_ok=True)
        self._engine_file().write_text(json.dumps({"engine": engine}))
        return {"ok": True, "engine": engine}

    def test_codex(self):
        """確認 Codex CLI 裝好、也登入了：先看 codex login status，再跑一個極小的工作（唯讀、不碰檔案）。"""
        codex = find_codex()
        if not codex:
            self.codex_test = {"ok": False, "msg": "找不到 Codex CLI（npm install -g @openai/codex）"}
            return self.codex_test
        try:
            st = subprocess.run([codex, "login", "status"], capture_output=True, text=True, timeout=30)
            if st.returncode != 0:
                self.codex_test = {"ok": False, "msg": "還沒登入：按「登入 Codex」"}
                return self.codex_test
            r = subprocess.run([codex, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "只回覆兩個字：可以"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, cwd=str(self.workspace))
            msgs = [json.loads(l).get("item", {}).get("text") for l in r.stdout.splitlines() if '"agent_message"' in l]
            ok = r.returncode == 0 and bool(msgs)
            msg = (msgs[-1] if msgs else (r.stderr or "沒有回應"))[:300]
        except (subprocess.TimeoutExpired, OSError, ValueError) as e:
            ok, msg = False, str(e)[:300]
        self.codex_test = {"ok": ok, "msg": msg, "t": int(time.time())}
        return self.codex_test

    def login_codex(self):
        """開終端機跑 codex login（瀏覽器會跳出 ChatGPT 登入頁）；登入完關掉那個視窗即可。"""
        codex = find_codex()
        if not codex:
            raise ValueError("找不到 Codex CLI：請先安裝（npm install -g @openai/codex）")
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "Codex 登入", "cmd", "/k", codex, "login"], cwd=str(self.workspace))
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{shlex.quote(codex)} login"', "-e", 'tell application "Terminal" to activate'])
        else:
            raise ValueError("這個系統請自己在終端機執行 codex login")
        return {"ok": True}

    def set_secret(self, name, value):
        """寫進本人的金鑰檔（runs/_me/secrets.env，經雲端硬碟同步）；已有就改那一行。程式之後不顯示內容。"""
        p = self.runs / "_me" / "secrets.env"
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        lines = [l for l in lines if not l.strip().startswith(name + "=")] + [f"{name}={value}"]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _secret(self, name):
        p = self.runs / "_me" / "secrets.env"
        for line in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
            k, sep, v = line.partition("=")
            if sep and k.strip() == name:
                return v.strip() or None
        return None

    def _profs_for_notion(self):
        out = []
        for st_p in sorted(self.runs.glob("*/state.json")):
            if st_p.parent.name.startswith("_"):
                continue
            pr = (json.loads(st_p.read_text()) or {}).get("professor") or {}
            out.append({"slug": st_p.parent.name, "name": pr.get("name"), "institution": pr.get("institution"), "orcid": pr.get("orcid")})
        return out

    def notion_import(self):
        """從 Notion 的「博士申請追蹤」匯入（Notion 為主）→ runs/_me/applications.json；對不到已建檔教授的是待建檔。"""
        from pipeline import notion
        cfg_p = self.runs / "_me" / "notion.json"
        token = self._secret("NOTION_TOKEN")
        if not token or not cfg_p.exists():
            raise ValueError("還沒連接 Notion")
        cfg = json.loads(cfg_p.read_text())
        rows = notion.match_professors(notion.fetch_rows(token, cfg["db_id"]), self._profs_for_notion())
        (self.runs / "_me" / "applications.json").write_text(json.dumps({"fetched": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                                         "db_url": cfg.get("db_url"), "rows": rows}, ensure_ascii=False, indent=1))
        return {"ok": True, "rows": len(rows)}

    def notion_connect(self, token, link):
        from pipeline import notion
        token = (token or "").strip()
        if not token:
            raise ValueError("先貼上 Notion 整合的金鑰")
        cfg = notion.setup(token, link, [{**p, "status": "聯絡中"} for p in self._profs_for_notion()])
        self.set_secret("NOTION_TOKEN", token)
        (self.runs / "_me" / "notion.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        return self.notion_import()

    def notion_status(self):
        p = self.runs / "_me" / "notion.json"
        a = self.runs / "_me" / "applications.json"
        if not p.exists():
            return None
        cfg = json.loads(p.read_text())
        fetched = json.loads(a.read_text()).get("fetched") if a.exists() else None
        return {"db_url": cfg.get("db_url"), "fetched": fetched, "token": bool(self._secret("NOTION_TOKEN"))}

    # ---- Google 日曆（OAuth：本人自己的「電腦版應用程式」用戶端；權杖只在本人的雲端硬碟）----
    def _gfile(self, name):
        return self.runs / "_me" / name

    def gcal_client(self, text):
        from pipeline import gcal
        c = gcal.client_from(text)
        self._gfile("").mkdir(parents=True, exist_ok=True)
        self._gfile("google_client.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
        return {"ok": True}

    def gcal_start(self):
        """產生登入網址並用預設瀏覽器打開；Google 回到 http://127.0.0.1:<port>/ 由 gcal_callback 接。"""
        from pipeline import gcal
        cp = self._gfile("google_client.json")
        if not cp.exists():
            raise ValueError("先上傳 Google 的用戶端 JSON")
        v, c = gcal.pkce()
        st = secrets.token_urlsafe(16)
        self.gcal_pending = {"state": st, "verifier": v, "redirect": f"http://127.0.0.1:{self.port}/"}
        url = gcal.auth_url(json.loads(cp.read_text())["client_id"], self.gcal_pending["redirect"], st, c)
        webbrowser.open(url)
        return {"ok": True, "url": url}

    def gcal_callback(self, q):
        from pipeline import gcal
        pend = getattr(self, "gcal_pending", None)
        if not pend or q.get("state") != pend["state"]:
            raise ValueError("登入狀態對不上：回應用程式重按「登入 Google」")
        if q.get("error"):
            raise ValueError(f"Google 沒有給權限（{q['error']}）")
        tok = gcal.exchange(json.loads(self._gfile("google_client.json").read_text()), q.get("code"), pend["verifier"], pend["redirect"])
        self.gcal_pending = None
        self._gfile("google_token.json").write_text(json.dumps(tok, ensure_ascii=False, indent=1))
        return self.gcal_import()

    def _gcal_access(self):
        from pipeline import gcal
        tp, cp = self._gfile("google_token.json"), self._gfile("google_client.json")
        if not tp.exists() or not cp.exists():
            raise ValueError("還沒連接 Google 日曆")
        tok = json.loads(tp.read_text())
        if gcal.expired(tok):
            tok = gcal.refresh(json.loads(cp.read_text()), tok)
            tp.write_text(json.dumps(tok, ensure_ascii=False, indent=1))
        return tok["access_token"]

    def _profs_for_gcal(self):
        out = []
        for p in self._profs_for_notion():
            op = self.runs / p["slug"] / "owner.json"
            out.append({**p, "email": (json.loads(op.read_text()) if op.exists() else {}).get("email")})
        return out

    def gcal_import(self):
        """讀主日曆前 60 天到後 180 天的活動，留下對到教授的 → runs/_me/calendar.json。"""
        from pipeline import gcal
        events = gcal.match_events(gcal.list_events(self._gcal_access()), self._profs_for_gcal())
        self._gfile("calendar.json").write_text(json.dumps({"fetched": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                            "events": events}, ensure_ascii=False, indent=1))
        return {"ok": True, "events": len(events)}

    def gcal_create(self, body):
        from pipeline import gcal
        slug = self._lib_slug(body.get("slug"))
        b = gcal.event_body(body.get("summary"), body.get("start") or "", body.get("minutes") or 60, body.get("tz") or "UTC",
                            body.get("attendees") or [], meet=bool(body.get("meet")), slug=slug, note=body.get("note"))
        e = gcal.create_event(self._gcal_access(), b, notify=bool(body.get("notify")))
        self.gcal_import()
        return {"ok": True, "link": e.get("htmlLink"), "meet": e.get("hangoutLink")}

    def gcal_status(self):
        cal = self._gfile("calendar.json")
        return {"client": self._gfile("google_client.json").exists(), "connected": self._gfile("google_token.json").exists(),
                "fetched": json.loads(cal.read_text()).get("fetched") if cal.exists() else None}

    def test_claude(self):
        """跑一個極小的工作確認 Claude Code 裝好、也登入了（不碰任何檔案）。"""
        claude = find_claude()
        if not claude:
            self.claude_test = {"ok": False, "msg": "找不到 Claude Code"}
            return self.claude_test
        try:
            r = subprocess.run([claude, "-p", "只回覆兩個字：可以", "--output-format", "json", "--permission-mode", "dontAsk"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, cwd=str(self.workspace))
            out = json.loads(r.stdout or "{}") if r.stdout.strip().startswith("{") else {}
            ok = r.returncode == 0 and not out.get("is_error")
            msg = (out.get("result") or r.stderr or r.stdout or "").strip()[:300]
        except (subprocess.TimeoutExpired, OSError, ValueError) as e:
            ok, msg = False, str(e)[:300]
        self.claude_test = {"ok": ok, "msg": msg if ok else (msg or "沒有回應") + "（多半是還沒登入：按「登入 Claude Code」）", "t": int(time.time())}
        return self.claude_test

    def login_claude(self):
        """開一個終端機視窗跑 claude，照畫面登入（瀏覽器會跳出 Anthropic 的登入頁）；登入完關掉那個視窗即可。"""
        claude = find_claude()
        if not claude:
            raise ValueError("找不到 Claude Code：請先安裝（https://claude.com/claude-code）")
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "Claude Code 登入", "cmd", "/k", claude], cwd=str(self.workspace))
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "cd {shlex.quote(str(self.workspace))} && {shlex.quote(claude)}"',
                              "-e", 'tell application "Terminal" to activate'])
        else:
            raise ValueError("這個系統請自己在終端機執行 claude 登入")
        return {"ok": True}

    def open_secrets(self):
        """用系統的文字編輯器打開金鑰檔讓本人自己貼（程式不經手金鑰內容）；沒有就先建空白範本。"""
        p = self.runs / "_me" / "secrets.env"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("# phdeasy 金鑰（只在你的 Google 雲端硬碟同步，不進 GitHub）\n# 在等號後面貼上 key，存檔即可\nS2_API_KEY=\n", encoding="utf-8")
        if os.name == "nt":
            subprocess.Popen(["notepad", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-e", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"ok": True, "path": str(p)}

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

    def lib_script(self, *args):
        """跑討論文獻的腳本（加文獻、讀 Zotero）：用工作區的流水線，跟 Claude Code 跑的是同一支。"""
        uv = find_uv()
        if not uv:
            raise ValueError("這台還沒有 uv，先到「設定」安裝")
        r = subprocess.run([uv, "run", "python", "scripts/library.py", *args], cwd=str(self.workspace), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        if r.returncode:
            out = (r.stdout + r.stderr).strip()
            print(f"library.py {' '.join(args)} 失敗：\n{out}")  # 完整訊息進 app.log
            self.log_error(f"library.py {' '.join(args)}", out)
            last = next((l for l in reversed(out.splitlines()) if l.strip()), "")
            raise ValueError(f"{last}（完整訊息在雲端硬碟 _logs 資料夾）" if last else "加入失敗")
        return r.stdout.strip()

    def log_error(self, what, detail):
        """錯誤也寫進 runs/_logs/<這台電腦>.log：會同步到雲端硬碟，別台電腦（或 Claude）也看得到；app.log 只在這台。"""
        try:
            d = self.runs / "_logs"
            d.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^\w.-]", "_", socket.gethostname() or "this") + ".log"
            with open(d / name, "a", encoding="utf-8") as f:
                f.write(f"===== {datetime.now().isoformat(timespec='seconds')} {what}\n{detail.strip()[-6000:]}\n")
        except OSError:
            pass

    def _lib_slug(self, slug):
        import re as _re
        if not _re.fullmatch(r"[a-z0-9-]+", slug or "") or not (self.runs / slug / "state.json").exists():
            raise ValueError(f"沒有這位教授：{slug}")
        return slug

    @staticmethod
    def _lib_meta(m):
        out = []
        for k, flag in (("given_by", "--given-by"), ("discussion", "--discussion"), ("note", "--note")):
            v = (m.get(k) or "").strip()
            if v:
                out += [flag, v[:200]]
        return out

    # ---------- 全文閱讀：螢光筆、筆記、問 AI、翻譯、收藏素材（學 ieltsgod 的閱讀題） ----------
    def paper_text(self, body):
        from pipeline.reader import paper_paths, text_blocks
        t, a = paper_paths(self.runs, body.get("slug"), body.get("id"), lib=bool(body.get("lib")))
        blocks = text_blocks(t.read_text(encoding="utf-8")) if t.exists() else []
        head = t.read_text(encoding="utf-8").split("\n", 1)[0] if t.exists() else ""
        src = next((k for k in ("pdf", "xml", "abstract") if f"| {k} |" in head), None)
        z = a.with_name(a.stem + ".zh.json")
        job = self.zh_jobs.get((body.get("slug"), body.get("id"), bool(body.get("lib"))))
        return {"blocks": blocks, "source": src, "store": json.loads(a.read_text(encoding="utf-8")) if a.exists() else {},
                "zh": json.loads(z.read_text(encoding="utf-8")) if z.exists() else {}, "zh_job": job}

    def paper_translate(self, body):
        """整篇翻成中文（學 ieltsgod 閱讀題的右邊）：背景一批一批翻，翻好的存 annotations/<id>.zh.json，畫面輪詢進度。"""
        from pipeline.reader import merge_zh, paper_paths, text_blocks, todo_chunks, zh_chunk_prompt
        t, a = paper_paths(self.runs, body.get("slug"), body.get("id"), lib=bool(body.get("lib")))
        if not t.exists():
            raise ValueError("這篇沒有轉好的全文")
        k = (body.get("slug"), body.get("id"), bool(body.get("lib")))
        if (self.zh_jobs.get(k) or {}).get("status") == "running":
            return self.zh_jobs[k]
        z = a.with_name(a.stem + ".zh.json")
        blocks = text_blocks(t.read_text(encoding="utf-8"))
        chunks = todo_chunks(blocks, json.loads(z.read_text(encoding="utf-8")) if z.exists() else {})
        job = self.zh_jobs[k] = {"status": "running", "done": 0, "total": sum(len(c) for c in chunks), "error": ""}

        def run():
            try:
                for c in chunks:
                    job["done"] += merge_zh(z, self.ai_once(zh_chunk_prompt(c, body.get("title")), level="easy"), c)
                job["status"] = "done"
            except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                job.update(status="error", error=str(e)[:300])
        threading.Thread(target=run, daemon=True).start()
        return job

    def annot_save(self, body):
        from pipeline.reader import clean_store, paper_paths
        _, a = paper_paths(self.runs, body.get("slug"), body.get("id"), lib=bool(body.get("lib")))
        store = clean_store(body.get("store") or {})
        a.parent.mkdir(parents=True, exist_ok=True)
        a.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"ok": True}

    def clip_add(self, body):
        from pipeline.reader import add_clip
        return add_clip(self.runs / "_me" / "clips.json", body)

    def ask_ai(self, body, translate=False):
        """選取文字問 AI／翻譯：一次性的小問題，不碰任何檔案。"""
        from pipeline.reader import ask_prompt, translate_prompt
        prompt = translate_prompt(body.get("sel")) if translate else ask_prompt(body.get("sel"), body.get("ctx"), body.get("title"), body.get("q"), body.get("history"))
        return {"a": self.ai_once(prompt, level="easy" if translate else "hard")}

    def ai_once(self, prompt, level="hard"):
        """問一次、拿一個回答（問 AI、翻譯、分類）：用 AI 小幫手選的那位；額度用完或沒登入就自動換下一位測試過的（照 ieltsgod）。"""
        from pipeline import ai as AI
        pv = AI.current_provider()
        if not pv:
            raise ValueError("還沒有可以用的 AI：到「設定 → AI 小幫手」安裝、登入並測試一位")
        try:
            return AI.ai_run(pv, prompt, timeout=300, level=level).strip()
        except subprocess.TimeoutExpired:
            raise ValueError("AI 太久沒有回應，請再試一次") from None
        except RuntimeError as e:
            raise ValueError(AI.friendly_error(pv, str(e))[:400]) from None

    def ai_post(self, path, body):
        """AI 小幫手的按鈕：安裝、登入、登出、終端機、測試、換模型、設定、Antigravity 登入（貼 code）、通知。"""
        from pipeline import ai as AI
        pv = body.get("provider")
        if path == "ai-engine":
            return AI.engine_status(pv)
        if path == "ai-alerts":
            since = int(body.get("since") or 0)
            return {"alerts": [a for a in AI.AI_ALERTS if a["t"] > since], "now": int(time.time() * 1000)}
        if path == "ai-settings":
            c = AI.w_settings()
            if body.get("provider") in AI.PROVIDERS:
                c["provider"] = body["provider"]
            if "autoSwitch" in body:
                c["autoSwitch"] = bool(body["autoSwitch"])
            AI.write_json(AI.WSET, c)
            return AI.engine_status()
        if path == "ai-agy":
            a = body.get("action")
            try:
                if a == "start":
                    AI.agy_login_start()
                elif a == "code":
                    AI.agy_send_code(body.get("code"))
                elif a == "cancel":
                    AI.agy_stop()
                    AI.AGY.update(state="", error="")
            except RuntimeError as e:
                raise ValueError(str(e)) from None
            return AI.agy_status()
        if pv not in AI.PROVIDERS:
            raise ValueError("不認得的 AI")
        try:
            if path == "ai-install":
                if AI.ai_bin(pv) and not (pv == "gemini" and not AI.is_agy(AI.ai_bin(pv))):
                    return {"ok": True, "already": True}
                AI.ai_install(pv)
                return {"ok": True}
            if path == "ai-login":
                AI.ai_login(pv)
                return {"ok": True}
            if path == "ai-logout":
                AI.ai_logout(pv)
                return {"ok": True}
            if path == "ai-terminal":
                return {"ok": AI.ai_terminal(pv)}
            if path == "ai-test":
                return {"tested": AI.ai_test(pv)}
            if path == "ai-model":
                return AI.set_model(pv, str(body.get("model") or ""))
        except RuntimeError as e:
            raise ValueError(str(e)) from None
        raise KeyError(path)

    def library_upload(self, slug, data, meta, limit=200 * 1024 * 1024):
        """討論文獻：本人上傳教授給的 PDF。存進 runs/<slug>/library/inbox/（只新增），再查 DOI／OpenAlex 建檔。"""
        slug = self._lib_slug(slug)
        if len(data) > limit or b"%PDF-" not in data[:1024]:
            raise ValueError("這不是 PDF 檔（或超過 200 MB）")
        inbox = self.runs / slug / "library" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        dst = inbox / f"_upload_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.pdf"
        dst.write_bytes(data)
        out = self.lib_script("add-pdf", f"runs/{slug}", "--pdf", str(dst.relative_to(self.workspace)) if dst.is_relative_to(self.workspace) else str(dst),
                              *self._lib_meta(meta))
        self._rebuild_site(slug)
        self.lib_classify(slug)
        return {"ok": True, "result": out}

    # ---------- Meeting 文獻：資料夾與類型標籤 ----------
    def _lib_works(self, slug):
        p = self.runs / slug / "library" / "work" / "works.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def lib_classify(self, slug, wait=False):
        """還沒有主題或類型的文獻：類型腳本先判；主題（判不出的類型也一起）在背景問 AI（便宜的模型），沿用已經有的主題。照 ieltsgod 閱讀的主題分類。"""
        from pipeline.libmeta import classify_prompt, load_meta, parse_classify, rule_type, set_topic, set_type, topics
        lib = self.runs / slug / "library"
        items = load_meta(lib)["items"]
        todo = [w for w in self._lib_works(slug) if not (items.get(w["id"]) or {}).get("topic") or not (items.get(w["id"]) or {}).get("ptype")]
        for w in todo:
            t = rule_type(w.get("title"), w.get("abstract"), w.get("type"))
            if t and not (items.get(w["id"]) or {}).get("ptype"):
                set_type(lib, w["id"], t, by="rule")

        def run():
            for w in todo:
                if getattr(self, "_classifying", {}).get((slug, w["id"])):
                    continue
                self._classifying = {**getattr(self, "_classifying", {}), (slug, w["id"]): True}
                try:
                    cur = load_meta(lib)
                    if (cur["items"].get(w["id"]) or {}).get("topic") and (cur["items"].get(w["id"]) or {}).get("ptype"):
                        continue
                    topic, ptype = parse_classify(self.ai_once(classify_prompt(w.get("title"), w.get("abstract"), topics(cur)), level="easy"))
                    if topic:
                        set_topic(lib, w["id"], topic, by="ai")
                    if not (load_meta(lib)["items"].get(w["id"]) or {}).get("ptype"):
                        set_type(lib, w["id"], ptype, by="ai")
                except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                    print(f"文獻分類失敗 {slug}/{w['id']}：{e}")
                finally:
                    self._classifying.pop((slug, w["id"]), None)
        if todo:
            run() if wait else threading.Thread(target=run, daemon=True).start()
        return {"todo": len(todo)}

    def lib_meta(self, body):
        from pipeline.libmeta import rename_topic, set_topic, set_type
        slug = self._lib_slug(body.get("slug"))
        lib, act = self.runs / slug / "library", body.get("act")
        if act == "rename-topic":
            return rename_topic(lib, body.get("old") or "", body.get("name"))
        wid = str(body.get("id") or "")
        if wid not in {w["id"] for w in self._lib_works(slug)}:
            raise ValueError(f"沒有這篇：{wid}")
        if act == "topic":
            return set_topic(lib, wid, body.get("topic"), by="me")
        if act == "type":
            return set_type(lib, wid, body.get("ptype"), by="me")
        raise ValueError("不知道要做什麼")

    def _rebuild_site(self, slug):
        """加了文獻：重建這位教授的 data.json，清單馬上看得到（「待處理」）。"""
        uv = find_uv()
        if uv:
            subprocess.run([uv, "run", "python", "scripts/build_site.py", f"runs/{slug}"], cwd=str(self.workspace), capture_output=True, timeout=300)

    def doc_script(self, *args):
        """本人文件的腳本（上傳成新版本）：用工作區的流水線。"""
        uv = find_uv()
        if not uv:
            raise ValueError("這台還沒有 uv，先到「設定」安裝")
        r = subprocess.run([uv, "run", "python", "scripts/mydocs.py", *args], cwd=str(self.workspace), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        if r.returncode:
            raise ValueError((r.stdout + r.stderr).strip()[-400:] or "上傳失敗")
        return r.stdout.strip()

    def doc_upload(self, q, data, limit=50 * 1024 * 1024):
        """本人上傳 Research Proposal／Personal Statement／SOP（Word 或 PDF）：存成新版本、馬上顯示英文，背景翻成中文。"""
        import re as _re
        from pipeline.mydocs import doc_key
        key = doc_key(q.get("kind") or "", q.get("for") or None)
        ext = (q.get("ext") or "").lower()
        if ext not in ("docx", "pdf") or len(data) > limit:
            raise ValueError("只收 Word（.docx）或 PDF，50 MB 以內")
        if (ext == "pdf" and b"%PDF-" not in data[:1024]) or (ext == "docx" and not data.startswith(b"PK")):
            raise ValueError("檔案內容跟副檔名對不上")
        up = self.runs / "_me" / "docs" / "_uploads"
        up.mkdir(parents=True, exist_ok=True)
        f = up / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.{ext}"
        f.write_bytes(data)
        args = ["upload", q["kind"], str(f)] + (["--for", q["for"]] if q.get("for") else [])
        out = self.doc_script(*args)
        m = _re.search(r"第 (\d+) 版", out)
        n = int(m.group(1)) if m else None
        started = False
        if n and not self.blocked:  # 馬上顯示英文；中文在背景翻（同時已有 3 個工作在跑就先不翻，之後可按「翻成中文」）
            try:
                self.jobs.start("doc-translate", prompt_doc_translate(key, n), f"翻成中文：{key} 第 {n} 版", key=f"doc:{key}")
                started = True
            except RuntimeError:
                pass
        return {"ok": True, "key": key, "version": n, "translating": started, "result": out}

    def me_update(self, body):
        """本人在首頁編輯：摘要、標題列、研究興趣、工作經歷、學歷；舊的 me.json 先備份到 runs/_me/history/。"""
        mep = self.runs / "_me" / "me.json"
        me = json.loads(mep.read_text())
        new = {}
        for k in ("summary", "summary_zh", "headline", "headline_zh"):
            if k in body:
                new[k] = str(body[k] or "").strip()[:3000]
        if "interests" in body:
            ints = [{"en": str(i.get("en") or "").strip()[:200], "zh": str(i.get("zh") or "").strip()[:200]} for i in body["interests"] or []]
            if any(not (i["en"] or i["zh"]) for i in ints):
                raise ValueError("研究興趣不能空白")
            new["interests"] = ints
        if "experience" in body:
            xs = []
            for x in body["experience"] or []:
                role, org = str(x.get("role") or "").strip()[:200], str(x.get("org") or "").strip()[:200]
                if not role and not org:
                    raise ValueError("工作經歷要有職稱或單位")
                bullets = [{"en": str(b.get("en") or "").strip()[:1500], "zh": str(b.get("zh") or "").strip()[:1500]}
                           for b in x.get("bullets") or [] if (b.get("en") or b.get("zh"))]
                xs.append({"kind": x.get("kind") if x.get("kind") in ("professional", "research") else "professional", "role": role,
                           "role_zh": str(x.get("role_zh") or "").strip()[:200], "org": org, "place": str(x.get("place") or "").strip()[:200],
                           "dates": str(x.get("dates") or "").strip()[:100], "bullets": bullets,
                           "skills": [str(k).strip()[:80] for k in x.get("skills") or [] if str(k).strip()],
                           "skills_zh": [str(k).strip()[:80] for k in x.get("skills_zh") or [] if str(k).strip()]})
            new["experience"] = xs
        if "education" in body:
            eds = []
            for e in body["education"] or []:
                if not (e.get("degree") or e.get("school")):
                    raise ValueError("學歷要有學位或學校")
                eds.append({k: str(e.get(k) or "").strip()[:300] for k in ("degree", "school", "years", "note")})
            new["education"] = eds
        if "applicant" in body:  # 申請身分：查博士學程時照這個身分寫學費、條件、期限
            ap = body["applicant"] or {}
            if ap.get("status") not in ("international", "domestic"):
                raise ValueError("申請身分只能是國際生或本地生")
            new["applicant"] = {"status": ap["status"], "citizenship": str(ap.get("citizenship") or "").strip()[:80],
                                "intake": str(ap.get("intake") or "").strip()[:20]}
        if not new:
            raise ValueError("沒有要改的內容")
        hist = mep.parent / "history"
        hist.mkdir(exist_ok=True)
        (hist / f"me-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json").write_text(mep.read_text())
        mep.write_text(json.dumps({**me, **new}, ensure_ascii=False, indent=2))
        return {"ok": True, "changed": sorted(new)}

    def _run_discover(self, args):
        """查詢教授：在背景跑 scripts/discover.py（只查 OpenAlex 公開資料，不開始建檔），結果寫 runs/_discover/latest.json。"""
        def go():
            uv = find_uv()
            if uv:
                subprocess.run([uv, "run", "python", "scripts/discover.py", *args], cwd=str(self.workspace), capture_output=True, timeout=900)
        threading.Thread(target=go, daemon=True).start()

    def doc_change(self, body):
        """本人自己改文件的一段：改、刪、在後面加一段。直接存成新版本（不用 AI），更新索引。"""
        import re as _re
        from pipeline.mydocs import change, index
        key, v, b, op = body.get("key") or "", body.get("version"), body.get("block"), body.get("op")
        if not _re.fullmatch(r"(ps|sop|proposal)(--[a-z0-9-]+)?", key) or not isinstance(v, int) or not isinstance(b, int) or b < 0:
            raise ValueError("文件、版本或段落不對")
        root = self.runs / "_me" / "docs"
        meta = change(root, key, v, op, b, en=body.get("en"), zh=body.get("zh"))
        (root / "index.json").write_text(json.dumps(index(root), ensure_ascii=False, indent=1))
        return {"ok": True, "version": meta["n"]}

    def prof_owner(self, slug, **upd):
        """本人對這位教授的註記（owner.json）：備註、顯示用的機構、移除（只是收起來，檔案都留著，可以還原）。"""
        slug = self._lib_slug(slug)
        p = self.runs / slug / "owner.json"
        o = json.loads(p.read_text()) if p.exists() else {}
        o.update(upd)
        p.write_text(json.dumps(o, ensure_ascii=False, indent=1))
        return {"ok": True, **o}

    def post(self, path, body):
        if path == "notion-connect":
            return self.notion_connect(body.get("token"), body.get("link"))
        if path == "notion-import":
            return self.notion_import()
        if path == "gcal-client":
            return self.gcal_client(body.get("json") or "")
        if path == "gcal-login":
            return self.gcal_start()
        if path == "gcal-import":
            return self.gcal_import()
        if path == "gcal-create":
            return self.gcal_create(body)
        if path == "engine":
            return self.set_engine(body.get("engine"))
        if path == "test-codex":
            return self.test_codex()
        if path == "login-codex":
            return self.login_codex()
        if path == "paper-text":
            return self.paper_text(body)
        if path.startswith("ai-"):
            return self.ai_post(path, body)
        if path == "paper-translate":
            return self.paper_translate(body)
        if path == "annot-save":
            return self.annot_save(body)
        if path == "clip-add":
            return self.clip_add(body)
        if path == "clip-del":
            from pipeline.reader import remove_clip
            return {"ok": remove_clip(self.runs / "_me" / "clips.json", str(body.get("id") or ""))}
        if path in ("ask", "translate"):
            return self.ask_ai(body, translate=path == "translate")
        if path == "doc-change":
            return self.doc_change(body)
        if path == "prof-update":
            upd = {k: str(body[k]).strip()[:500] for k in ("note", "institution", "email") if k in body}
            return self.prof_owner(body.get("slug"), **upd)
        if path in ("prof-remove", "prof-restore"):
            return self.prof_owner(body.get("slug"), archived=path == "prof-remove")
        if path == "discover-enrich":
            if self.blocked:
                raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑")
            if not (self.runs / "_discover" / "latest.json").exists():
                raise ValueError("先按「開始查詢」")
            return self.jobs.start("discover-enrich", prompt_discover_enrich(), "查詢教授：補排名、獎學金、實驗室網址")
        if path == "discover":
            q = str(body.get("query") or "").strip()[:200]
            since = body.get("since") or datetime.now().year - 4
            if not isinstance(since, int) or not 2000 <= since <= datetime.now().year:
                raise ValueError("起始年份不對")
            self._run_discover((["--query", q] if q else []) + ["--from", str(since)])
            return {"started": True}
        if path == "me-update":
            return self.me_update(body)
        if path in ("doc-edit", "doc-translate"):
            import re as _re
            if self.blocked:
                raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑；那台關掉後重開這個程式")
            key, v = body.get("key") or "", body.get("version")
            if not _re.fullmatch(r"(ps|sop|proposal)(--[a-z0-9-]+)?", key) or not isinstance(v, int) or v < 1:
                raise ValueError("文件或版本不對")
            if path == "doc-translate":
                return self.jobs.start("doc-translate", prompt_doc_translate(key, v), f"翻成中文：{key} 第 {v} 版", key=f"doc:{key}")
            b = body.get("block")
            if not isinstance(b, int) or b < 0:
                raise ValueError("段落不對")
            return self.jobs.start("doc-edit", prompt_doc_edit(key, v, b, (body.get("instruction") or "")[:300]), f"AI 編修：{key} 第 {v} 版第 {b + 1} 段", key=f"doc:{key}")
        if path == "lib-meta":
            return self.lib_meta(body)
        if path == "lib-classify":
            return self.lib_classify(self._lib_slug(body.get("slug")))
        if path in ("library-add", "zotero"):
            slug = self._lib_slug(body.get("slug"))
            if path == "zotero":
                args = ["zotero", f"runs/{slug}"] + (["--collection", body["collection"]] if body.get("collection") else [])
                return json.loads(self.lib_script(*args))
            import re as _re
            dois = [d.strip() for d in body.get("dois") or [] if d.strip()]
            bad = [d for d in dois if not _re.fullmatch(r"(https?://(dx\.)?doi\.org/)?10\.\d{4,9}/\S+", d, _re.I)]
            if bad or not dois:
                raise ValueError(f"這不是 DOI：{', '.join(bad) or '（空的）'}")
            src = "zotero" if body.get("source") == "zotero" else "doi"
            res = [self.lib_script("add-doi", f"runs/{slug}", "--doi", d, "--source", src, *self._lib_meta(body)) for d in dois]
            self._rebuild_site(slug)
            self.lib_classify(slug)
            return {"ok": True, "result": res}
        if path in ("library-process", "library-draft"):
            if self.blocked:
                raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑流水線；那台關掉後重開這個程式")
            slug = self._lib_slug(body.get("slug"))
            if path == "library-process":
                return self.jobs.start("library", prompt_library_process(slug), f"Meeting 文獻：{slug}", slug=slug)
            import re as _re
            ids = [i for i in body.get("ids") or [] if i]
            if not ids or not all(_re.fullmatch(r"[WL][0-9a-f]+", i) for i in ids):
                raise ValueError("先勾選要用的文獻")
            return self.jobs.start("library-draft", prompt_library_draft(slug, ids), f"用 {len(ids)} 篇擬初稿：{slug}", slug=slug)
        if path == "account":
            acct = body.get("account")
            if self.need_account.is_set() and not self.account_chosen.is_set():  # 第一次選：背景的啟動同步正在等
                if acct not in self.drive_choices:
                    raise ValueError("沒有這個帳號")
                save_account(self.runs, acct)
                self.account_chosen.set()
                return {"ok": True}
            if self.jobs.running():
                raise ValueError("有工作在跑，等它跑完再換帳號")
            return self.switch_account(acct)
        if path == "sync":
            return self.resync()
        if path == "check-update":
            return self.check_update() or {"available": False, "current": self.version}
        if path == "update":
            return self.do_update()
        if path == "test-claude":
            return self.test_claude()
        if path == "login-claude":
            return self.login_claude()
        if path == "open-secrets":
            return self.open_secrets()
        if path in ("new", "continue", "reply", "match", "propose", "exception", "deep") and self.blocked:
            raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑流水線；那台關掉後重開這個程式")
        if path == "new":
            name, inst = (body.get("name") or "").strip(), (body.get("institution") or "").strip()
            if not name or not inst:
                raise ValueError("姓名和學校都要填")
            slug = slug_of(name)
            if not slug:
                raise ValueError("看不懂這個姓名：請用英文姓名")
            if (self.runs / slug / "state.json").exists():
                raise ValueError(f"已經有這位教授的檔案（{slug}）：到「工作進度」按繼續跑")
            if body.get("dept"):  # 從目標系所新增：放進那個系所
                from pipeline.targets import assign
                t = self._targets()
                assign(t, str(body["dept"]), slug)
                self._save_targets(t)
            return self.start_or_queue("new", prompt_new(name, inst, body.get("orcid"), slug), f"建檔：{name}", slug=slug)
        if path == "continue":
            slug = (body.get("slug") or "").strip()
            if not (self.runs / slug / "state.json").exists():
                raise ValueError(f"沒有這位教授：{slug}")
            return self.start_or_queue("continue", prompt_continue(slug), f"繼續：{slug}", slug=slug)
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
        if path == "target-add":  # 目標學校 → 系所：新增後在背景查教員名單
            from pipeline.targets import add_target, find_dept
            t = self._targets()
            dept = add_target(t, str(body.get("school") or "")[:200], str(body.get("department") or "")[:200], str(body.get("url") or "")[:500] or None)
            self._save_targets(t)
            sc, d = find_dept(t, dept)
            job = None if self.blocked or (d.get("faculty") and not body.get("refresh")) else \
                self.start_or_queue("faculty", prompt_faculty(dept, sc["name"], d["name"], d.get("url")), f"教員名單：{d['name']}", key=f"faculty:{dept}")
            return {"ok": True, "dept": dept, "job": job}
        if path == "faculty-lookup":
            from pipeline.targets import find_dept
            sc, d = find_dept(self._targets(), str(body.get("dept") or ""))
            return self.start_or_queue("faculty", prompt_faculty(d["id"], sc["name"], d["name"], d.get("url")), f"教員名單：{d['name']}", key=f"faculty:{d['id']}")
        if path == "target-remove":
            from pipeline.targets import remove_target
            t = self._targets()
            remove_target(t, str(body.get("dept") or ""))
            self._save_targets(t)
            return {"ok": True}
        if path == "prof-assign":
            from pipeline.targets import assign, find_dept
            t, slug = self._targets(), self._lib_slug(body.get("slug"))
            if body.get("dept"):
                assign(t, str(body["dept"]), slug)
            else:  # 拿出系所
                for sc in t.get("schools") or []:
                    for d in sc["departments"]:
                        if slug in d["members"]:
                            d["members"].remove(slug)
            self._save_targets(t)
            return {"ok": True}
        if path == "faculty-build":  # 勾選的教員：放進這個系所並開始建檔（超過同時上限就排隊）
            from pipeline.targets import assign, find_dept
            if self.blocked:
                raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑流水線；那台關掉後重開這個程式")
            t = self._targets()
            sc, d = find_dept(t, str(body.get("dept") or ""))
            names = [str(n).strip()[:200] for n in body.get("names") or [] if str(n).strip()][:30]
            if not names:
                raise ValueError("先勾選教授")
            started, queued, existing = [], [], []
            for n in names:
                slug = slug_of(n)
                if not slug:
                    continue
                assign(t, d["id"], slug)
                if (self.runs / slug / "state.json").exists():
                    existing.append(n)
                    continue
                r = self.start_or_queue("new", prompt_new(n, f"{sc['name']}（{d['name']}）", None, slug), f"建檔：{n}", slug=slug)
                (queued if r.get("queued") else started).append(n)
            self._save_targets(t)
            return {"ok": True, "started": started, "queued": queued, "existing": existing}
        if path == "deep":  # 教授頁勾選「完全解析」：加進必讀，背景只處理這幾篇
            import re as _re
            slug = self._lib_slug(body.get("slug"))
            ids = [i for i in body.get("ids") or [] if isinstance(i, str) and _re.fullmatch(r"W\d+", i)]
            if not ids or len(ids) > 20:
                raise ValueError("勾 1–20 篇")
            works = {w["id"]: w for w in json.loads((self.runs / slug / "work" / "works.json").read_text())}
            ids = [i for i in ids if i in works and works[i].get("kind") == "title"]
            if not ids:
                raise ValueError("勾的文章都已經是完全解析了")
            uv = find_uv()
            if not uv:
                raise ValueError("這台還沒有 uv，先到「設定」安裝")
            r = subprocess.run([uv, "run", "python", "scripts/focus.py", "add", f"runs/{slug}", "--ids", ",".join(ids)], cwd=str(self.workspace),
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if r.returncode:
                raise ValueError((r.stdout + r.stderr).strip()[-300:])
            return self.jobs.start("deep", prompt_deep(slug, ids), f"完全解析 {len(ids)} 篇：{slug}", slug=slug)
        if path == "programs":
            slug = self._lib_slug(body.get("slug"))
            pr = (json.loads((self.runs / slug / "state.json").read_text()) or {}).get("professor") or {}
            dept = next((d["name"] for sc in self._targets().get("schools") or [] for d in sc.get("departments") or [] if slug in (d.get("members") or [])), None)
            return self.jobs.start("programs", prompt_programs(slug, pr.get("name") or slug, pr.get("institution") or "", pr.get("orcid"), dept),
                                   f"博士學程：{pr.get('name') or slug}", slug=slug)
        if path == "match":
            slug = (body.get("slug") or "").strip()
            if not (self.runs / slug / "state.json").exists():
                raise ValueError(f"沒有這位教授：{slug}")
            return self.jobs.start("match", prompt_match(slug), f"重新比對：{slug}", slug=slug)
        if path == "propose":
            slug = (body.get("slug") or "").strip()
            if not slug or not (self.runs / slug / "state.json").exists():
                raise ValueError(f"沒有這位教授：{slug}")
            from pipeline.propose import finalized_with
            mep = self.runs / "_me" / "me.json"
            if finalized_with(json.loads(mep.read_text()) if mep.exists() else {}, slug):
                raise ValueError("跟這位教授的計畫書已定案，不再產生 AI 版本")
            return self.jobs.start("propose", prompt_propose(slug), f"研究構想草稿：{slug}", slug=slug)
        if path == "reply":
            last = self.jobs.load(body["job"]) if body.get("job") else self.jobs.latest()  # 回覆哪一個工作（可以同時有好幾位教授）
            if not last or not last.get("session"):
                raise ValueError("沒有可以接續的對話，請改按「繼續跑」")
            text = (body.get("text") or "").strip()
            if not text:
                raise ValueError("回覆是空的")
            return self.jobs.start("reply", text + "\n" + UNATTENDED, f"回覆：{last['title'].split('：', 1)[-1]}", session=last["session"], slug=last.get("slug"), key=last.get("key"))
        if path == "stop":
            return {"stopped": self.jobs.stop(body.get("job") or None) if body.get("job") else False}
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
            u = urlparse(self.path)
            if u.path == "/" and "state=" in u.query:  # Google 日曆登入回來
                from urllib.parse import parse_qs
                try:
                    r = app.gcal_callback({k: v[0] for k, v in parse_qs(u.query).items()})
                    msg = f"已連接 Google 日曆，讀到 {r['events']} 個跟教授有關的會議。可以關掉這一頁，回到應用程式。"
                except (ValueError, RuntimeError) as e:
                    msg = f"沒有連接成功：{e}"
                data = f'<!doctype html><meta charset="utf-8"><title>phdeasy</title><p style="font:16px system-ui;margin:40px">{html.escape(msg)}</p>'.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
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
            if self.path.startswith("/api/doc-upload"):
                try:
                    from urllib.parse import parse_qs
                    q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                    n = int(self.headers.get("Content-Length") or 0)
                    return self._json(200, app.doc_upload(q, self.rfile.read(n)))
                except (ValueError, RuntimeError) as e:
                    return self._json(400, {"error": str(e)})
            if self.path.startswith("/api/library-upload/"):
                try:
                    u = urlparse(self.path)
                    from urllib.parse import parse_qs
                    q = {k: v[0] for k, v in parse_qs(u.query).items()}
                    n = int(self.headers.get("Content-Length") or 0)
                    return self._json(200, app.library_upload(unquote(u.path.rsplit("/", 1)[-1]), self.rfile.read(n), q))
                except (ValueError, RuntimeError) as e:
                    return self._json(400, {"error": str(e)})
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


BOOT_STEPS = [("drive", "找 Google 雲端硬碟"), ("sync", "同步教授檔案"), ("rebuild", "更新教授資料"),
              ("tools", "檢查 AI（Claude Code）與流水線工具"), ("update", "檢查新版本")]


def startup(app, choose=True):
    """背景做（視窗先開，開機畫面顯示每一步與進度）：找雲端硬碟 → 選帳號 → 同步 → 重建資料 → 檢查工具 → 檢查新版本。"""
    b = app.boot
    def step(key, state, note=""):
        b["steps"][key] = {"state": state, "note": note}
        if state == "doing":
            b["step"] = key
    try:
        step("drive", "doing")
        if choose and app.need_account.is_set():
            step("drive", "doing", "這台登入了多個 Google 帳號：請選一個")
            app.account_chosen.wait()
        dst = target(app.runs)
        step("drive", "ok" if dst and dst.parent.exists() else "warn",
             str(dst) if dst and dst.parent.exists() else "找不到 Google 雲端硬碟：只用這台的資料（到設定看怎麼裝）")
        step("sync", "doing")

        def prog(i, total, rel, n):
            b["sync"] = {"done": i, "total": total, "cur": rel, "pulled": n.get("pull", 0) + n.get("conflict_pull", 0),
                         "pushed": n.get("push", 0) + n.get("conflict_push", 0) + n.get("shrunk", 0)}
        r = drive_sync(app.runs, hold=True, wait=60, progress=prog) if dst and dst.parent.exists() else 1
        if r == 3:  # 有資料夾讀不到、或一次要刪太多：不同步，用這台的資料
            step("sync", "warn", "同步先停下：有雲端資料夾讀不到，或一次要刪太多檔案；先用這台的資料，沒有刪任何東西（終端機有詳細原因）")
        elif r == 2:
            app.blocked = (busy_elsewhere(target(app.runs), device_id()) or {}).get("device") or "另一台電腦"
            step("sync", "warn", f"另一台電腦（{app.blocked}）正在用：已拉下雲端的資料給你看，這台先不推上去")
        else:
            app.closer = Closer(app.runs)
            sy = b.get("sync") or {}
            step("sync", "ok" if r == 0 else "warn",
                 (f"拉下 {sy.get('pulled', 0)}、推上 {sy.get('pushed', 0)} 個檔案" if (sy.get("pulled") or sy.get("pushed")) else "已經是最新的") if r == 0 else "沒有同步（只用這台的資料）")
        step("rebuild", "doing")
        step("rebuild", "ok" if rebuild(app.workspace) else "skip", "" if find_uv() else "沒有 uv：用雲端同步下來的資料")
        for name, fn in (("Notion", app.notion_import), ("Google 日曆", app.gcal_import)):  # 有連接才匯入；失敗不擋開機
            try:
                if (name == "Notion" and app.notion_status()) or (name != "Notion" and app.gcal_status()["connected"]):
                    fn()
            except Exception as e:
                print(f"{name} 匯入失敗：{e}")
        step("tools", "doing")
        c, u = find_claude(), find_uv()
        step("tools", "ok" if c and u else "warn", "Claude Code、uv 都在" if c and u else
             "、".join(x for x in ("沒有 Claude Code" if not c else "", "沒有 uv" if not u else "") if x) + "（只看資料不需要；要建新教授到設定安裝）")
        step("update", "doing")
        try:
            info = app.check_update()
        except Exception as e:
            info, err = None, str(e)
        if app.version == "dev":
            step("update", "skip", "開發版：用 git pull 更新")
        elif not info or not info.get("latest"):
            step("update", "warn", "沒辦法檢查新版（網路不通？）")
        elif info.get("available"):
            step("update", "new", f"有新版本 {info['latest']}（目前 {app.version}）")
        else:
            step("update", "ok", f"已經是最新版本 {app.version}")
    except Exception as e:
        print(f"啟動失敗：{e}")
        b["error"] = str(e)[:300]
    finally:
        app.syncing = False
        b["done"] = True


def open_mac_window(url, app):
    """Mac：跟 ieltsgod 一樣用 pywebview 開自己的視窗（不經過 Chrome）；沒有 pywebview 就回 False 走舊的方式。
    視窗關掉才回來；自動更新要重開時（app.quitting）由這裡把視窗關掉。"""
    try:
        import webview
    except Exception as e:
        print(f"沒有 pywebview（{e}），改用瀏覽器視窗")
        return False
    win = webview.create_window("我的博士申請", url, width=1360, height=900, min_size=(900, 600))

    def watch_quit():
        app.quitting.wait()
        try:
            win.destroy()
        except Exception:
            pass
    threading.Thread(target=watch_quit, daemon=True).start()
    webview.start()  # 主執行緒在這裡等到視窗關掉
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(default_workspace()))
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--browser", action="store_true", help="用一般瀏覽器開，不開成獨立視窗")
    ap.add_argument("--window", action="store_true", help="沒有 pywebview 時，Mac 也用 Chrome 開成獨立視窗")
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
    if FROZEN:
        app.version = version

        def update_loop():  # 打開時由開機流程查一次，之後每 6 小時再查
            while not app.quitting.wait(6 * 3600):
                try:
                    info = app.check_update()
                    if info and info.get("available"):
                        print(f"有新版：{info['latest']}（目前 {app.version}）")
                except Exception as e:
                    print(f"檢查更新失敗：{e}")
        threading.Thread(target=update_loop, daemon=True).start()
    app.runs.mkdir(parents=True, exist_ok=True)
    os.environ["PHDEASY_HOLD"] = "1"  # 子程序（重建、Claude Code）同步時不要放開這台的使用中
    if not choose_account(app.runs, ask=None):
        drives = find_drives()
        if len(drives) > 1:
            app.drive_choices = [d[0] for d in drives]
            app.need_account.set()
    threading.Thread(target=startup, args=(app,), daemon=True).start()

    port = free_port(a.port)
    app.port = port  # Google 日曆登入回呼用
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/web/loading.html"  # 開機畫面：顯示每一步與進度，做完自動進首頁
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

    if sys.platform == "darwin" and not (a.browser or a.no_browser) and open_mac_window(url, app):
        stop.set()  # 關掉視窗＝結束：最後同步、釋放使用中、停掉正在跑的流水線
        close_all()
        srv.shutdown()
        return
    exe = None if (a.browser or a.no_browser) else find_app_browser()
    if exe and (FROZEN or os.name == "nt" or a.window):
        win = AppWindow(exe, url, ws / ".window")
        win.open()
        win.wait_closed(alive=lambda: not app.quitting.is_set())  # 關掉視窗（或自動更新）＝結束：最後同步、釋放使用中、停掉正在跑的流水線
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
        app.quitting.wait()
        close_all()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
