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

from drive_sync import run as drive_sync, target
from pipeline.drive_sync import busy_elsewhere, device_id, find_drives, release
from pipeline.window import AppWindow, find_app_browser
from pipeline.jobs import (FULLTEXT_KINDS, REJUDGE_KINDS, UNATTENDED, Jobs, exception_actions, find_claude, prompt_continue,
                           prompt_doc_edit, prompt_doc_translate, prompt_exception, prompt_library_draft, prompt_library_process, prompt_match, prompt_propose, prompt_new)

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
        self.claude_test = None
        self.version = "dev"
        self.update_info = None
        self.quitting = threading.Event()  # 自動更新時設起來：關掉視窗、結束程式，讓安裝程式接手
        self.boot = {"steps": {k: {"state": "todo", "note": ""} for k, _ in BOOT_STEPS}, "labels": dict(BOOT_STEPS),
                     "order": [k for k, _ in BOOT_STEPS], "step": "drive", "sync": {}, "done": False}
        self.update_state = {"stage": "", "got": 0, "total": 0, "error": ""}

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
                "exception_actions": {k: exception_actions(k) for k in sorted(FULLTEXT_KINDS | REJUDGE_KINDS | {"grant_unresolved", "possible_author_split"})},
                "settings": self.settings(), "update": self.update_info, "version": self.version,
                "boot": self.boot, "update_state": self.update_state}

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
                "folder": str(dst) if dst else None, "claude_test": self.claude_test,
                "keys": {"S2_API_KEY": keys.get("S2_API_KEY", False) or bool(os.environ.get("S2_API_KEY"))},
                "workspace": str(self.workspace)}

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
            raise ValueError((r.stdout + r.stderr).strip()[-400:] or "加入失敗")
        return r.stdout.strip()

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
        return {"ok": True, "result": out}

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
        if n and not self.jobs.running() and not self.blocked:  # 馬上顯示英文；中文在背景翻
            self.jobs.start("doc-translate", prompt_doc_translate(key, n), f"翻成中文：{key} 第 {n} 版")
            started = True
        return {"ok": True, "key": key, "version": n, "translating": started, "result": out}

    def me_update(self, body):
        """本人在首頁編輯簡介：只改摘要、標題列、研究興趣；舊的 me.json 先備份到 runs/_me/history/。"""
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
        if not new:
            raise ValueError("沒有要改的內容")
        hist = mep.parent / "history"
        hist.mkdir(exist_ok=True)
        (hist / f"me-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json").write_text(mep.read_text())
        mep.write_text(json.dumps({**me, **new}, ensure_ascii=False, indent=2))
        return {"ok": True, "changed": sorted(new)}

    def post(self, path, body):
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
                return self.jobs.start("doc-translate", prompt_doc_translate(key, v), f"翻成中文：{key} 第 {v} 版")
            b = body.get("block")
            if not isinstance(b, int) or b < 0:
                raise ValueError("段落不對")
            return self.jobs.start("doc-edit", prompt_doc_edit(key, v, b, (body.get("instruction") or "")[:300]), f"AI 編修：{key} 第 {v} 版第 {b + 1} 段")
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
            return {"ok": True, "result": res}
        if path in ("library-process", "library-draft"):
            if self.blocked:
                raise ValueError(f"另一台電腦（{self.blocked}）正在用，這台先不要跑流水線；那台關掉後重開這個程式")
            slug = self._lib_slug(body.get("slug"))
            if path == "library-process":
                return self.jobs.start("library", prompt_library_process(slug), f"討論文獻：{slug}", slug=slug)
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
        if path in ("new", "continue", "reply", "match", "propose", "exception") and self.blocked:
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
        if r == 2:
            app.blocked = (busy_elsewhere(target(app.runs), device_id()) or {}).get("device") or "另一台電腦"
            step("sync", "warn", f"另一台電腦（{app.blocked}）正在用：已拉下雲端的資料給你看，這台先不推上去")
        else:
            app.closer = Closer(app.runs)
            sy = b.get("sync") or {}
            step("sync", "ok" if r == 0 else "warn",
                 (f"拉下 {sy.get('pulled', 0)}、推上 {sy.get('pushed', 0)} 個檔案" if (sy.get("pulled") or sy.get("pushed")) else "已經是最新的") if r == 0 else "沒有同步（只用這台的資料）")
        step("rebuild", "doing")
        step("rebuild", "ok" if rebuild(app.workspace) else "skip", "" if find_uv() else "沒有 uv：用雲端同步下來的資料")
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
