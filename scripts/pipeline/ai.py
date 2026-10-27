"""AI 小幫手：Claude Code／Gemini（Antigravity CLI）／Codex CLI（ChatGPT）三家，照 ieltsgod 的接法（本人 2026-10-27：全部照抄）。

- 安裝（官方安裝程式或 npm）、登入（瀏覽器、終端機、Antigravity 在背景操作只要貼 code）、登出、測試連線
- 每家可以選模型；「自動」＝重要的工作用最強的、簡單的（翻譯、分類）用最便宜的；這個帳號用不了的模型記一週不再挑
- 一位失敗（額度用完、沒登入、逾時）就自動換下一位能用的（可以關掉），暫停那位一陣子
- 額度：從工具輸出順便記下（Claude 的 rate_limit_event、Codex 的 rate_limits），設定頁顯示血條
- 設定存在 runs/_app/ai.json（只在這台，不同步）；agy 在 runs/_app/ai_work 裡跑（只有給 AI 的題目檔）

這裡只管「問一次、拿一個回答」的小工作（問 AI、翻譯、分類、測試）；背景建檔的流水線另由 pipeline/jobs.py 叫 Claude Code／Codex。
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

WIN = os.name == "nt"
WSET = None   # 設定檔：configure() 設成 runs/_app/ai.json
WDIR = None   # agy 跑的資料夾：runs/_app/ai_work
RUNS = None   # runs/：StepFun 的 key 在 runs/_me/secrets.env（本人在設定貼，經雲端硬碟同步）


def configure(runs):
    global WSET, WDIR, RUNS
    RUNS = str(runs)
    WSET = os.path.join(str(runs), "_app", "ai.json")
    WDIR = os.path.join(str(runs), "_app", "ai_work")


def read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


PROVIDERS = {
    "claude": {"name": "Claude", "tool": "Claude Code", "cmd": "claude", "npm": None},
    "gemini": {"name": "Gemini", "tool": "Antigravity CLI", "cmd": "agy", "npm": None},   # 2026-06-18 起 Google AI Pro／Ultra 改用 Antigravity CLI（agy）
    "codex": {"name": "ChatGPT", "tool": "Codex CLI", "cmd": "codex", "npm": "@openai/codex"},
}
# StepFun（本人 2026-10-27 加）：不用裝工具，OpenAI 相容的 API，本人在設定貼 key
PROVIDERS["stepfun"] = {"name": "StepFun", "tool": "Step API", "cmd": None, "npm": None, "api": True}
STEPFUN_URL = "https://api.stepfun.ai/v1/chat/completions"
PROVIDER_ORDER = ("claude", "gemini", "codex", "stepfun")
# 「問一次」的小工作：各自用哪一位可以在設定改；沒選的，StepFun 測試成功就用它，否則用預設那位
TASKS = {"ask": "問 AI（選取文字）", "translate": "翻譯（選取的文字、整篇全文）", "classify": "Meeting 文獻的主題與類型"}
# 每位 AI 可以選的模型：值、顯示名稱、說明。'' = 交給工具自己決定（自動）
MODELS = {"claude": [("", "自動", "重要的工作用 Opus 5.5，簡單的用 Haiku 5.5"), ("claude-opus-5-5", "Opus 5.5", "最強，最仔細"), ("claude-sonnet-5-5", "Sonnet 5.5", "較快、省額度"), ("claude-haiku-5-5", "Haiku 5.5", "最便宜、最快")],
          # Gemini：ieltsgod 列的 3.1 Pro 已經下架（2026-10 agy models 只剩 4 Argon、3.8 Flash）
          "gemini": [("", "自動", "重要的工作用 4 Argon，簡單的用 3.8 Flash"), ("Gemini 4 Argon (High)", "4 Argon", "最強"), ("Gemini 3.8 Flash (Medium)", "3.8 Flash", "較快、省額度")],
          "codex": [("", "自動", "重要的工作用 GPT-6.1 Sol，簡單的用 GPT-6 Luna"), ("gpt-6.1-sol", "GPT-6.1 Sol", "最新最強"), ("gpt-5.6-sol", "GPT-5.6 Sol", "上一代，便宜一些"), ("gpt-6-luna", "GPT-6 Luna", "最便宜、最快")]}
AUTO_PICK = {"claude": {"hard": "claude-opus-5-5", "easy": "claude-haiku-5-5"},
             "gemini": {"hard": "Gemini 4 Argon (High)", "easy": "Gemini 3.8 Flash (Medium)"},
             "codex": {"hard": "gpt-6.1-sol", "easy": "gpt-6-luna"}}
MODELS["stepfun"] = [("step-5-preview", "Step 5 Preview", "旗艦，1M 上下文"), ("step-3.7-flash", "Step 3.7 Flash", "較快、便宜"),
                     ("step-3.5-flash", "Step 3.5 Flash", "最便宜、只有文字"), ("", "自動", "重要的工作用 Step 5 Preview，簡單的用 Step 3.7 Flash")]
AUTO_PICK["stepfun"] = {"hard": "step-5-preview", "easy": "step-3.7-flash"}
MODEL_DEFAULT = {"claude": "", "gemini": "", "codex": "", "stepfun": "step-5-preview"}  # 本人指定用 Step 5 Preview

AI_LAST = threading.local()  # 這個工作實際用了哪一位、哪個模型、難易度


def w_settings():
    return (read_json(WSET, {}) or {}) if WSET else {}


def w_set(**kw):
    c = w_settings()
    c.update(kw)
    write_json(WSET, c)
    return c


def set_tested(pv, ok, msg=""):
    c = w_settings()
    t = c.get("tested") or {}
    t[pv] = {"ok": bool(ok), "t": int(time.time() * 1000), "msg": str(msg)[:600]}
    c["tested"] = t
    write_json(WSET, c)


def model_bad(pv, m):
    """這個模型最近試過、這個帳號不能用（7 天內）"""
    t = ((w_settings().get("modelBad") or {}).get(pv) or {}).get(m)
    return bool(t and time.time() - t < 7 * 86400)


def ai_level(level):
    """接下來這個工作是簡單（easy）還是重要（hard）的"""
    AI_LAST.level = level


def model_of(pv):
    m = (w_settings().get("models") or {}).get(pv)
    return m if m is not None and any(m == x[0] for x in MODELS.get(pv, [])) else MODEL_DEFAULT.get(pv, "")


def model_for(pv):
    """這一次實際要用的模型：選了「自動」就看工作難易度挑（這個帳號用不了的跳過，改用帳號預設）"""
    m = model_of(pv)
    if m == "":
        c = AUTO_PICK.get(pv, {}).get(getattr(AI_LAST, "level", None) or "hard", "")
        m = "" if (not c or model_bad(pv, c)) else c
    used = dict(getattr(AI_LAST, "used", None) or {})
    used[pv] = m
    AI_LAST.used = used
    return m


# ---------- 找工具 ----------
def win_refresh_path():
    """Windows：程式開著的時候才裝的工具（Node.js、Claude Code、Git），PATH 不會自己更新 → 從登錄檔重新讀一次"""
    if not WIN:
        return
    try:
        import winreg
        parts = []
        for root, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(root, key) as k:
                    v, _ = winreg.QueryValueEx(k, "Path")
                parts += os.path.expandvars(v).split(";")
            except OSError:
                pass
        cur = os.environ.get("PATH", "").split(";")
        low = {c.lower().rstrip("\\") for c in cur}
        add = [x for x in parts if x and x.lower().rstrip("\\") not in low]
        if add:
            os.environ["PATH"] = ";".join(cur + add)
    except Exception:
        pass


def win_git_bash():
    """Windows 上的 Claude Code 需要 Git for Windows 的 bash.exe；找到就告訴 Claude Code 在哪"""
    if not WIN:
        return None
    p = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if p and os.path.exists(p):
        return p
    win_refresh_path()
    cands = [os.path.join(os.environ.get(v, ""), "Git", "bin", "bash.exe") for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    cands.append(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs", "Git", "bin", "bash.exe"))
    g = shutil.which("git")
    if g:
        cands.insert(0, os.path.join(os.path.dirname(os.path.dirname(g)), "bin", "bash.exe"))
    for c in cands:
        if c and os.path.exists(c):
            os.environ["CLAUDE_CODE_GIT_BASH_PATH"] = c
            return c
    return None


def _search_bin(cmd):
    """在 PATH 和常見安裝位置找指令"""
    win_refresh_path()
    p = shutil.which(cmd)
    if p:
        return p
    home = os.path.expanduser("~")
    if WIN:
        appdata = os.environ.get("APPDATA", "")
        for c in (os.path.join(home, ".local", "bin", cmd + ".exe"), os.path.join(appdata, "npm", cmd + ".cmd"),
                  os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", cmd + ".cmd"),
                  os.path.join(home, "AppData", "Local", "Programs", cmd, cmd + ".exe")):
            if c and os.path.exists(c):
                return c
        return None
    for c in (home + "/.local/bin/" + cmd, home + "/.claude/local/" + cmd, "/opt/homebrew/bin/" + cmd,
              "/usr/local/bin/" + cmd, home + "/.npm-global/bin/" + cmd, home + "/.bun/bin/" + cmd):
        if os.path.exists(c):
            return c
    try:
        out = subprocess.run(["/bin/bash", "-lc", "command -v " + cmd], capture_output=True, text=True, timeout=8).stdout.strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return None


def stepfun_key():
    """StepFun 的 key：環境變數 STEPFUN_API_KEY，或 runs/_me/secrets.env（本人在設定貼的）。不印出、不寫進錯誤訊息。"""
    k = os.environ.get("STEPFUN_API_KEY")
    if k:
        return k.strip()
    try:
        with open(os.path.join(RUNS or "", "_me", "secrets.env"), encoding="utf-8") as f:
            for line in f:
                name, sep, v = line.partition("=")
                if sep and name.strip() == "STEPFUN_API_KEY":
                    return v.strip() or None
    except OSError:
        pass
    return None


def ai_bin(pv):
    if pv == "stepfun":  # API：有 key 就算「裝好了」
        return "api" if stepfun_key() else None
    env = os.environ.get(pv.upper() + "_BIN")
    if env == "none":
        return None          # 測試用：假裝沒裝
    if env and os.path.exists(env):
        return env
    if pv == "gemini":
        # 先找 Antigravity CLI（agy）；沒有的話才用舊的 Gemini CLI（只剩 API 金鑰還能用）
        if WIN:
            c = os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local")), "agy", "bin", "agy.exe")
            if os.path.exists(c):
                return c
        return _search_bin("agy") or _search_bin("gemini")
    return _search_bin(PROVIDERS[pv]["cmd"])


def is_agy(exe):
    return bool(exe) and os.path.basename(exe).lower().startswith("agy")


def old_gemini_only(exe):
    """裝的是舊的 Gemini CLI：2026-06-18 起 Google 帳號（含 AI Pro／Ultra）登入已停用，只剩 API 金鑰能用"""
    return bool(exe) and not is_agy(exe) and not os.environ.get("GEMINI_API_KEY")


def npm_bin():
    return _search_bin("npm")


def _json_from(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("沒有拿到 JSON")
    return json.loads(text[i:j + 1])


def _gemini_env():
    # Gemini CLI 不信任的資料夾會拒絕在背後執行；這裡只在 ai_work（只有給 AI 的題目檔）裡呼叫它，所以標成信任
    return dict(os.environ, GEMINI_CLI_TRUST_WORKSPACE="true")


def _wdir():
    os.makedirs(WDIR, exist_ok=True)
    return WDIR


def _run(cmd, inp=None, timeout=120, cwd=None, env=None):
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=cwd or _wdir(), env=env)


login_states = {k: {"proc": None, "url": "", "terminal": False} for k in PROVIDERS}
install_states = {k: {"proc": None, "log": [], "done": False, "ok": None, "error": ""} for k in PROVIDERS}


# --- 登入狀態 ---
def logged_in(pv, exe):
    if pv == "stepfun":
        return bool(stepfun_key())
    try:
        if pv == "claude":
            if os.environ.get("ANTHROPIC_API_KEY"):
                return True
            r = _run([exe, "auth", "status", "--json"], timeout=20)
            try:
                return bool(_json_from(r.stdout).get("loggedIn"))
            except Exception:
                pass
            t = (r.stdout or "") + (r.stderr or "")        # 舊版沒有 --json：看文字
            if re.search(r"not logged in|logged out|no credentials|please run.*login", t, re.I):
                return False
            if re.search(r"logged in|authenticated", t, re.I):
                return True
            if os.path.exists(os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")):
                return True
            return None                                     # 判斷不出來
        if pv == "codex":
            return _run([exe, "login", "status"], timeout=20).returncode == 0
        if pv == "gemini":
            if os.environ.get("GEMINI_API_KEY"):
                return True
            if is_agy(exe):
                return None          # Antigravity 的登入存在系統鑰匙圈，看不出來：用「測試連線」確認
            return False              # 舊 Gemini CLI 的 Google 登入已停用
    except Exception:
        return None
    return None


def provider_status(pv):
    exe = ai_bin(pv)
    ls, ins = login_states[pv], install_states[pv]
    tested = (w_settings().get("tested") or {}).get(pv)
    cool = ai_cooling(pv)
    return {"id": pv, "name": PROVIDERS[pv]["name"], "tool": ("Gemini CLI（舊版）" if pv == "gemini" and exe and not is_agy(exe) else PROVIDERS[pv]["tool"]),
            "needsAgy": pv == "gemini" and old_gemini_only(exe),
            "model": model_of(pv), "modelName": model_name(pv),
            "models": [{"v": v, "name": model_label(pv, v, n), "note": d, "bad": model_bad(pv, v)} for v, n, d in MODELS.get(pv, [])],
            "quota": quota_of(pv),
            "installed": bool(exe), "loggedIn": logged_in(pv, exe) if exe else False,
            "loggingIn": bool(ls["proc"] and ls["proc"].poll() is None), "loginUrl": ls.get("url", ""), "terminal": ls.get("terminal", False),
            "installing": bool(ins["proc"] and ins["proc"].poll() is None), "installDone": ins["done"], "installOk": ins["ok"],
            "installError": ins.get("error", ""), "installLog": ins["log"][-3:], "tested": tested,
            "needsNode": PROVIDERS[pv]["npm"] is not None and not npm_bin(),
            "needsGit": bool(WIN and pv == "claude" and exe and not win_git_bash()),
            "cool": ({"why": cool["why"], "min": max(1, round((cool["until"] - time.time()) / 60))} if cool else None)}


# --- 安裝 ---
def ai_install(pv):
    ins = install_states[pv]
    if ins["proc"] and ins["proc"].poll() is None:
        return
    ins.update(log=[], done=False, ok=None, error="")
    if pv == "claude":
        cmd = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]
               if WIN else ["/bin/bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"])
    elif pv == "gemini":      # 官方安裝方式：https://antigravity.google/docs/cli/install/
        cmd = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://antigravity.google/cli/install.ps1 | iex"]
               if WIN else ["/bin/bash", "-c", "curl -fsSL https://antigravity.google/cli/install.sh | bash"])
    else:
        npm = npm_bin()
        if not npm:
            ins.update(done=True, ok=False, error="需要先安裝 Node.js（https://nodejs.org 下載 LTS 版），裝好後重開程式。")
            return
        cmd = [npm, "install", "-g", PROVIDERS[pv]["npm"]]
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    ins["proc"] = p

    def reader():
        for line in p.stdout:
            line = line.strip()
            if line:
                ins["log"] = (ins["log"] + [line])[-6:]
            m = re.search(r'([A-Za-z]:\\[^\s"\']*?agy(?:\.exe)?|/[^\s"\']*/agy)\b', line) if pv == "gemini" else None
            if m and os.path.isfile(m.group(1)):
                os.environ["GEMINI_BIN"] = m.group(1)      # 安裝程式說裝在哪就用哪
        p.wait()
        ok = p.returncode == 0 and bool(ai_bin(pv)) and (pv != "gemini" or is_agy(ai_bin(pv)))
        err = ""
        if not ok:
            tail = " ".join(ins["log"][-2:])
            err = ("沒有權限安裝（npm 需要管理員權限）。" if re.search(r"EACCES|permission", tail, re.I) else "安裝沒有成功。") + " " + tail[:160]
        ins.update(done=True, ok=ok, error=err)
        print(PROVIDERS[pv]["tool"] + " 安裝" + ("完成" if ok else "沒有成功"))
    threading.Thread(target=reader, daemon=True).start()


# --- 登入 ---
def open_terminal(pv, exe, args):
    """打開一個終端機視窗跑指令（需要在終端機裡互動登入的工具用）"""
    ls = login_states[pv]
    if WIN:
        try:
            subprocess.Popen(["cmd", "/c", "start", PROVIDERS[pv]["tool"] + " login", "/max", "cmd", "/k", exe] + args,
                             creationflags=0x00000010, startupinfo=subprocess.STARTUPINFO(), cwd=_wdir())     # 登入要互動：開一個看得到的新視窗
            ls["terminal"] = True
            return True
        except Exception:
            return False
    if sys.platform != "darwin":
        return False
    cmd = "cd " + "'" + _wdir().replace("'", "'\\''") + "' && " + " ".join("'" + a.replace("'", "'\\''") + "'" for a in [exe] + args)
    try:
        subprocess.Popen(["osascript", "-e", 'tell application "Terminal" to activate',
                          "-e", 'tell application "Terminal" to do script "%s"' % cmd.replace("\\", "\\\\").replace('"', '\\"')])
        ls["terminal"] = True
        return True
    except Exception:
        return False


# --- Antigravity CLI 登入：在背景開一個看不見的終端機跑 agy，自動按選單，使用者只要把網頁給的 code 貼到程式 ---
AGY = {"state": "", "url": "", "error": "", "screen": "", "pty": None, "buf": "", "last": 0.0}
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class _Pty:
    """跨平台的「看不見的終端機」：Windows 用 pywinpty（ConPTY），Mac／Linux 用內建的 pty"""
    def __init__(self, argv, cwd):
        self.win = WIN
        if WIN:
            from winpty import PtyProcess
            self.p = PtyProcess.spawn(argv, cwd=cwd, dimensions=(40, 140))
        else:
            import fcntl
            import pty
            import termios
            m, s = pty.openpty()
            try:
                fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
            except Exception:
                pass
            env = dict(os.environ, TERM="xterm-256color", COLUMNS="140", LINES="40")
            self.p = subprocess.Popen(argv, stdin=s, stdout=s, stderr=s, cwd=cwd, env=env, start_new_session=True, close_fds=True)
            os.close(s)
            self.fd = m

    def read(self):
        if self.win:
            try:
                return self.p.read(4096)
            except EOFError:
                return None
            except Exception:
                return None if not self.p.isalive() else ""
        try:
            b = os.read(self.fd, 4096)
        except OSError:
            return None
        return b.decode("utf-8", "replace") if b else None

    def write(self, s):
        try:
            if self.win:
                self.p.write(s)
            else:
                os.write(self.fd, s.encode("utf-8"))
        except Exception:
            pass

    def alive(self):
        try:
            return self.p.isalive() if self.win else self.p.poll() is None
        except Exception:
            return False

    def kill(self):
        try:
            if self.win:
                self.p.terminate(force=True)
            else:
                self.p.kill()
        except Exception:
            pass
        if not self.win:
            try:
                os.close(self.fd)
            except OSError:
                pass


def agy_status():
    return {k: AGY[k] for k in ("state", "url", "error", "screen")}


def agy_stop():
    if AGY["pty"]:
        AGY["pty"].kill()
    AGY["pty"] = None


def agy_login_start():
    exe = ai_bin("gemini")
    if not exe or not is_agy(exe):
        raise RuntimeError("還沒安裝 Antigravity CLI")
    agy_stop()
    try:
        pt = _Pty([exe], _wdir())          # 問 AI 時 agy 也在這個資料夾跑：登入時順便「信任」它
    except Exception as e:
        raise RuntimeError("沒辦法在背景打開 Antigravity（%s），請改按「用終端機登入」。" % e)
    AGY.update(state="starting", url="", error="", screen="", pty=pt, buf="", last=time.time())

    def reader():
        while True:
            c = pt.read()
            if c is None:
                break
            if not c:
                time.sleep(0.05)
                continue
            # 終端機查詢（游標位置、終端機種類、背景色）：替它回答，不然有些程式會一直等
            if "\x1b[6n" in c:
                pt.write("\x1b[1;1R")
            if "\x1b[c" in c or "\x1b[0c" in c:
                pt.write("\x1b[?1;2c")
            if "\x1b]11;?" in c:
                pt.write("\x1b]11;rgb:ffff/ffff/ffff\x1b\\")
            t = _ANSI.sub("", c.replace("\r\n", "\n").replace("\r", "\n"))
            AGY["buf"] = (AGY["buf"] + t)[-8000:]
            AGY["last"] = time.time()
            lines = [x.rstrip() for x in AGY["buf"].split("\n") if x.strip()]
            AGY["screen"] = "\n".join(lines[-14:])
            m = [u for u in re.findall(r'https://[^\s\'"<>]+', AGY["buf"]) if "google" in u or "oauth" in u.lower()]
            if m and not AGY["url"]:
                AGY["url"] = m[-1]
    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=_agy_drive, args=(pt,), daemon=True).start()


def _agy_drive(pt):
    t0 = time.time()
    menu_at = None
    while AGY["pty"] is pt:
        time.sleep(0.5)
        low, st = AGY["buf"].lower(), AGY["state"]
        if not pt.alive() and st not in ("finishing", "done", "error"):
            AGY.update(state="error", error="Antigravity 意外結束了。可以再按一次登入，或改按「用終端機登入」。")
            return
        if st == "starting":
            if "not signed in" in low or "google oauth" in low or "sign in" in low:
                pt.write("\r")
                menu_at = time.time()
                AGY["state"] = "browser"      # 選「1. Google OAuth」：會打開瀏覽器
            elif time.time() - t0 > 20 and AGY["buf"].strip():
                AGY["state"] = "finishing"
                _agy_finish(pt, already=True)    # 沒有出現登入選單：大概本來就登入過了
                return
            elif time.time() - t0 > 45:
                AGY.update(state="error", error="Antigravity 一直沒有反應。請改按「用終端機登入」。")
                agy_stop()
                return
        elif st == "browser":
            if AGY["url"] or "code" in low[-1500:] or time.time() - menu_at > 6:
                AGY["state"] = "need_code"
        elif st == "need_code":
            if time.time() - t0 > 900:
                AGY.update(state="error", error="等太久了（15 分鐘），請再按一次登入。")
                agy_stop()
                return


def agy_send_code(code):
    pt = AGY["pty"]
    if not pt or AGY["state"] != "need_code":
        raise RuntimeError("登入已經結束，請再按一次登入")
    code = re.sub(r"\s+", "", code or "")
    if len(code) < 8:
        raise RuntimeError("這串 code 太短，請把網頁上整串複製貼上")
    AGY["mark"] = len(AGY["buf"])
    AGY["error"] = ""
    pt.write(code)
    time.sleep(0.3)
    pt.write("\r")
    AGY["state"] = "finishing"
    threading.Thread(target=_agy_finish, args=(pt,), daemon=True).start()


def _agy_finish(pt, already=False):
    """送出 code 之後：主題、服務條款、信任資料夾這幾個畫面都按 Enter（預設選項），最後測試連線"""
    start, enters = time.time(), 0
    while time.time() - start < 45 and pt.alive():
        time.sleep(0.5)
        new = AGY["buf"][AGY.get("mark", 0):].lower()
        if not already and re.search(r"invalid|incorrect|expired|failed to (?:sign|log|auth)|error", new) and enters == 0:
            AGY.update(state="need_code", error="這串 code 沒有成功（可能過期或複製不完整）。請重新複製網頁上整串 code 貼上；還是不行就按「重新開始」。")
            return
        if time.time() - AGY["last"] > 2.5:
            if enters >= (2 if already else 8):
                break
            pt.write("\r")
            enters += 1
            AGY["last"] = time.time()
    agy_stop()
    AGY["state"] = "testing"
    t = ai_test("gemini") or {}
    if t.get("ok"):
        AGY.update(state="done", error="")
    else:
        AGY.update(state="error", error="登入流程走完了，但測試連線沒有成功：" + str(t.get("msg") or "") + "。可以改按「用終端機登入」看看卡在哪一步。")


def gemini_prepare_auth():
    """先把舊的 Gemini CLI 設成「用 Google 帳號登入」，打開後直接跳到登入，不用自己選"""
    d = os.path.join(os.path.expanduser("~"), ".gemini")
    p = os.path.join(d, "settings.json")
    try:
        s = read_json(p, {}) or {}
        auth = s.setdefault("security", {}).setdefault("auth", {})
        if not auth.get("selectedType"):
            auth["selectedType"] = "oauth-personal"
            write_json(p, s)
    except Exception:
        pass


def ai_login(pv):
    exe = ai_bin(pv)
    if not exe:
        raise RuntimeError("還沒安裝 " + PROVIDERS[pv]["tool"])
    ls = login_states[pv]
    if ls["proc"] and ls["proc"].poll() is None:
        return
    ls.update(url="", terminal=False)
    if pv == "gemini" and is_agy(exe):
        # Antigravity CLI：第一次打開會自動開瀏覽器登入 Google（用有 AI Pro／Ultra 的帳號），登入後憑證存在系統鑰匙圈
        if not open_terminal(pv, exe, []):
            raise RuntimeError("沒辦法打開終端機，請自己打開終端機輸入 agy 登入")
        return
    if pv == "gemini":
        # 舊 Gemini CLI 沒有單獨的登入指令：在背後跑一次小問題，它會自己打開 Google 登入頁（OAuth），問「Do you want to continue? [Y/n]」時自動回答 y
        gemini_prepare_auth()
        p = subprocess.Popen([exe, "-p", "Reply with exactly one word: OK", "-o", "json"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             start_new_session=not WIN, cwd=_wdir(), env=_gemini_env())
        try:
            p.stdin.write("y\n")
            p.stdin.flush()
        except Exception:
            pass
    else:
        args = ["auth", "login", "--claudeai"] if pv == "claude" else ["login"]
        p = subprocess.Popen([exe] + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", start_new_session=not WIN)
    ls["proc"] = p

    def reader():
        for line in p.stdout:
            m = re.search(r"https://\S+", line)
            if m and not ls["url"]:
                ls["url"] = m.group(0)
    threading.Thread(target=reader, daemon=True).start()

    def fallback():              # 很快就結束又沒成功 → 改開終端機
        try:
            p.wait(timeout=8)
        except Exception:
            return
        if p.returncode != 0 and logged_in(pv, exe) is not True:
            open_terminal(pv, exe, ["/login"] if pv == "claude" else [] if pv == "gemini" else ["login"])
    threading.Thread(target=fallback, daemon=True).start()

    def killer():
        time.sleep(600)
        if p.poll() is None:
            p.kill()
    threading.Thread(target=killer, daemon=True).start()


def ai_logout(pv):
    """登出（換帳號用）：各工具自己的登出方式"""
    exe = ai_bin(pv)
    if not exe:
        raise RuntimeError("還沒安裝")
    if pv == "gemini" and is_agy(exe):
        open_terminal(pv, exe, ["/logout"])
    elif pv == "gemini":
        for n in ("oauth_creds.json", "google_accounts.json"):
            f = os.path.join(os.path.expanduser("~"), ".gemini", n)
            if os.path.exists(f):
                os.remove(f)
    elif pv == "codex":
        _run([exe, "logout"], timeout=30)
    else:
        _run([exe, "auth", "logout"], timeout=30)
    c = w_settings()
    t = c.get("tested") or {}
    t.pop(pv, None)
    c["tested"] = t
    write_json(WSET, c)


def ai_terminal(pv):
    exe = ai_bin(pv)
    if not exe:
        raise RuntimeError("還沒安裝")
    if pv == "gemini" and not is_agy(exe):
        gemini_prepare_auth()
    return open_terminal(pv, exe, ["/login"] if pv == "claude" else [])


# --- 呼叫 AI ---
# --- 自動換 AI：一位失敗（額度用完、沒登入、逾時…）就換下一位；全部都不行才通知 ---
AI_COOL = {}                 # pv -> {'until': 時間, 'why': 原因}：暫停一陣子不用它
AI_ALERTS = []               # 給網頁的通知：{'t', 'msg', 'level'}


def ai_alert(msg, level="bad"):
    now = int(time.time() * 1000)
    key = lambda x: x.replace("，暫停中", "")
    if any(key(a["msg"]) == key(msg) and now - a["t"] < 600000 for a in AI_ALERTS):
        return
    AI_ALERTS.append({"t": now, "msg": msg, "level": level})
    del AI_ALERTS[:-30]


def ai_fail_kind(msg):
    m = (msg or "").lower()
    if re.search(r"quota|rate.?limit|usage limit|limit reached|reached your|429|resource.?exhausted|exceeded|credit|billing|too many requests|capacity|overloaded", m):
        return "quota"
    if re.search(r"not logged in|log ?in|auth|401|403|credential|api key|permission|eligible|unauthori", m):
        return "auth"
    if re.search(r"timed? ?out|timeout|超過", m):
        return "timeout"
    return "other"


AI_COOL_MIN = {"quota": 60, "auth": 30, "timeout": 10, "other": 5}
AI_WHY = {"quota": "額度用完或太多請求", "auth": "沒登入或登入過期", "timeout": "太久沒有回應", "other": "執行失敗"}


def ai_cooling(pv):
    c = AI_COOL.get(pv)
    return c if c and c["until"] > time.time() else None


def ai_auto():
    return w_settings().get("autoSwitch", True) is not False


def ai_used(pv):
    return getattr(AI_LAST, "pv", None) or pv


def ai_order(prefer):
    c, out = w_settings(), []
    for p in [prefer, c.get("provider")] + list(c.get("providers") or []) + list(PROVIDER_ORDER):
        if p in PROVIDERS and p not in out:
            out.append(p)
    return out


def ai_run(pv, prompt, timeout=600, auto=None, allowed=None, level=None):
    if level:
        ai_level(level)
    try:
        return _ai_run(pv, prompt, timeout, auto, allowed)
    finally:
        AI_LAST.level = None        # 難易度只算這一次


def _ai_run(pv, prompt, timeout=600, auto=None, allowed=None):
    """送出 prompt；這位失敗就自動換下一位能用的 AI（可以在設定關掉）。實際用了誰：ai_used()"""
    AI_LAST.pv = pv
    tested = w_settings().get("tested") or {}
    if allowed and pv not in allowed:
        raise ValueError("這個功能不使用 " + PROVIDERS[pv]["name"])
    others = [x for x in ai_order(pv) if x != pv and (not allowed or x in allowed) and (tested.get(x) or {}).get("ok") and ai_bin(x)]
    if not (ai_auto() if auto is None else auto) or not others:
        try:
            return ai_run_one(pv, prompt, timeout)
        except Exception as e:       # 只有一位（或關掉自動換）：照原本的錯誤，另外跳通知說明
            kind = "timeout" if isinstance(e, subprocess.TimeoutExpired) else ai_fail_kind(str(e))
            if kind != "other":
                advice = "而且沒有別的 AI 可以接手。到設定「AI 小幫手」再加一位，之後就會自動切換。" if not others else "（自動切換已關閉）。"
                ai_alert("%s %s，%s" % (PROVIDERS.get(pv, {}).get("name", "AI"), AI_WHY[kind], advice))
            raise
    tried = []
    for p in [pv] + others:
        cool = ai_cooling(p)
        if cool:
            tried.append((p, cool["why"] + "，暫停中"))
            continue
        try:
            out = ai_run_one(p, prompt, timeout)
            AI_LAST.pv = p
            AI_COOL.pop(p, None)
            return out
        except subprocess.TimeoutExpired:
            kind = "timeout"
        except Exception as e:
            kind = ai_fail_kind(str(e))
        AI_COOL[p] = {"until": time.time() + AI_COOL_MIN[kind] * 60, "why": AI_WHY[kind], "kind": kind}
        tried.append((p, AI_WHY[kind]))
        nxt = [x for x in others if x != p and not ai_cooling(x)]
        print("%s 失敗（%s）%s" % (PROVIDERS[p]["name"], AI_WHY[kind], "，自動改用 " + PROVIDERS[nxt[0]]["name"] if nxt else ""))
        if nxt:
            ai_alert("%s %s，已自動改用 %s。" % (PROVIDERS[p]["name"], AI_WHY[kind], PROVIDERS[nxt[0]]["name"]), "info")
    names = "；".join("%s：%s" % (PROVIDERS[p]["name"], w) for p, w in tried)
    msg = "所有 AI 都暫時不能用（" + names + "）。等額度恢復再試，或到設定「AI 小幫手」重新登入／測試連線。"
    ai_alert(msg, "bad")
    raise RuntimeError(msg)


def ai_run_one(pv, prompt, timeout=600):
    """送出 prompt；「自動」挑的模型這個帳號用不了的話，記下來（一週內不再挑它），改用帳號預設再試一次"""
    try:
        return _ai_run_one(pv, prompt, timeout)
    except Exception as e:
        m = (getattr(AI_LAST, "used", None) or {}).get(pv)
        if model_of(pv) == "" and m and re.search(r"model|模型", str(e), re.I) and re.search(r"not (found|available|supported|exist)|invalid|unknown|access", str(e), re.I):
            c = w_settings()
            c.setdefault("modelBad", {}).setdefault(pv, {})[m] = int(time.time())
            write_json(WSET, c)
            return _ai_run_one(pv, prompt, timeout)
        raise


def _ai_run_one(pv, prompt, timeout=600):
    """送出 prompt，回傳 AI 的文字回答（只用這一位）。三家都不給碰檔案、不給跑指令"""
    exe = ai_bin(pv)
    if not exe:
        raise RuntimeError("找不到 " + PROVIDERS[pv]["tool"])
    if logged_in(pv, exe) is False:
        raise RuntimeError("Not logged in：還沒登入 " + PROVIDERS[pv]["name"])
    if pv == "claude":
        # 空資料夾跑：不讀專案的 CLAUDE.md，也沒有檔案可碰；stream-json 拿得到「用了哪個模型」和額度事件（rate_limit_event）
        base = [exe, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk"]
        mdl = model_for("claude")
        with tempfile.TemporaryDirectory() as d:
            r = _run(base + (["--model", mdl] if mdl else []), prompt, timeout, d)
            out = r.stdout.strip()
            # 這台的 Claude Code 太舊、不認得完整的模型名稱：改用簡稱 opus／sonnet／haiku 再試一次
            m_alias = re.search(r"claude-(opus|sonnet|haiku)-", mdl or "")
            if m_alias and re.search(r"model.{0,40}(not found|not exist|invalid|unknown|not available|not supported)|(invalid|unknown) model", out + (r.stderr or ""), re.I):
                mdl = m_alias.group(1)
                r = _run(base + ["--model", mdl], prompt, timeout, d)
                out = r.stdout.strip()
        res = None
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            if ev.get("type") == "system" and ev.get("model"):
                note_model("claude", mdl, ev["model"])
            if ev.get("type") == "rate_limit_event":
                note_quota_claude(ev.get("rate_limit_info") or {})
            if ev.get("type") == "result":
                res = ev
        if res is None:
            try:
                res = json.loads(out)
            except ValueError:
                res = None
        if isinstance(res, dict) and "result" in res:
            for mid in (res.get("modelUsage") or {}):
                note_model("claude", mdl, mid)
            if res.get("is_error"):
                if re.search(r"limit|quota|429", str(res.get("result") or ""), re.I):
                    set_quota("claude", {"state": "out"})
                raise RuntimeError(str(res.get("result") or res.get("subtype") or "回報錯誤"))
            if (QUOTA.get("claude") or {}).get("state") == "out":
                set_quota("claude", {"state": "ok"})
            return str(res.get("result") or "")
        if not out:
            raise RuntimeError((r.stderr or "沒有回應").strip()[-200:])
        return out
    if pv == "gemini" and is_agy(exe):
        # Antigravity CLI 無頭模式（-p、--output-format json、--print-timeout）；題目很長：寫成檔案，用 @檔案 附上
        wd = _wdir()
        pf = os.path.join(wd, "_給AI的題目.txt")
        with open(pf, "w", encoding="utf-8") as f:
            f.write(prompt)
        ask = ("Read the attached file @" + os.path.basename(pf) + " and do exactly what it says. "
               "Reply with the answer only. Do not edit any files or run any commands.")
        mdl = model_for("gemini")
        r = _run([exe, "-p", ask, "--output-format", "json", "--print-timeout", "%ds" % int(timeout)] + (["--model", mdl] if mdl else []), None, timeout + 30, wd)
        out = r.stdout.strip()
        try:
            w = _json_from(out)
        except ValueError:
            w = None
        if w is not None:
            if w.get("error") or (w.get("status") and str(w.get("status")).upper() != "SUCCESS"):
                raise RuntimeError(str(w.get("error") or w.get("status")))
            if "response" in w:
                return str(w.get("response") or "")
            res = w.get("result") if isinstance(w.get("result"), dict) else None
            if res is not None:
                if res.get("status") and str(res["status"]).upper() != "SUCCESS":
                    raise RuntimeError(str(res.get("error") or res["status"]))
                return str(res.get("response") or "")
        if not out:
            raise RuntimeError(((r.stderr or "") + " 沒有回應").strip()[-300:])
        return out
    if pv == "gemini":
        cmd = [exe, "-p", "Follow the instructions above and reply with the answer only.", "-o", "json"]
        r = _run(cmd, prompt, timeout, None, _gemini_env())
        out = r.stdout.strip()
        try:
            w = _json_from(out)
            if w.get("error"):
                raise RuntimeError(error_summary(out))
            if "response" in w:
                return str(w.get("response") or "")
        except ValueError:
            pass
        if not out or r.returncode != 0 and "response" not in out:
            raise RuntimeError(error_summary((r.stdout or "") + "\n" + (r.stderr or "")))
        return out
    if pv == "codex":
        fd, outf = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            mdl = model_for("codex")
            cmd = [exe, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "--color", "never", "-o", outf] + (["-m", mdl] if mdl else []) + ["-"]
            r = _run(cmd, prompt, timeout)
            text = open(outf, encoding="utf-8", errors="replace").read().strip() if os.path.exists(outf) else ""
            note_quota_codex(r.stdout)
        finally:
            try:
                os.remove(outf)
            except Exception:
                pass
        if not text:
            err = (r.stderr or r.stdout or "沒有回應").strip()
            if re.search(r"not logged in|login", err, re.I):
                err = "Not logged in"
            raise RuntimeError(err[-200:])
        return text
    if pv == "stepfun":
        return _stepfun(prompt, timeout)
    raise RuntimeError("不認得的 AI：" + pv)


def _stepfun(prompt, timeout=600):
    """StepFun Chat Completions（OpenAI 相容）：回 choices[0].message.content。錯誤訊息只留狀態碼和服務的說明，不帶出 key。"""
    key = stepfun_key()
    if not key:
        raise RuntimeError("Not logged in：還沒貼 StepFun 的 key")
    mdl = model_for("stepfun") or "step-5-preview"
    body = {"model": mdl, "messages": [{"role": "user", "content": prompt}],
            "reasoning_effort": "low" if getattr(AI_LAST, "level", None) == "easy" else "medium"}
    req = urllib.request.Request(STEPFUN_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            why = error_summary(e.read().decode("utf-8", "replace"))
        except Exception:
            why = ""
        why = why.replace(key, "***")
        kind = {401: "401 unauthorized（key 不對或過期）", 403: "403 forbidden", 429: "429 rate limit（額度或請求太多）"}.get(e.code, f"HTTP {e.code}")
        raise RuntimeError(f"StepFun {kind}：{why}"[:300]) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"連不到 StepFun（{e.reason}）") from None
    if d.get("model"):
        note_model("stepfun", mdl, d["model"])
    try:
        return str(d["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("StepFun 回應格式不對：" + json.dumps(d, ensure_ascii=False)[:200]) from None


def task_provider(task):
    """這個小工作用哪一位：本人在設定選的（而且能用）→ 沒選的話 StepFun 測試成功就用它 → 預設那位。"""
    c = w_settings()
    pv = (c.get("tasks") or {}).get(task)
    if pv in PROVIDERS and ai_bin(pv):
        return pv
    if ((c.get("tested") or {}).get("stepfun") or {}).get("ok") and ai_bin("stepfun"):
        return "stepfun"
    return current_provider()


# --- 額度和實際模型：從 AI 工具的輸出順便記下來，顯示在「AI 小幫手」 ---
QUOTA = {}       # pv -> {'state': ok/warn/out, 'left': 剩幾 %, 'resets': 秒, 't': 毫秒}
MODEL_SEEN = {}  # pv -> {選的別名: 實際模型 id}


def set_quota(pv, d):
    d = dict(d, t=int(time.time() * 1000))
    QUOTA[pv] = d
    try:
        c = w_settings()
        c.setdefault("quota", {})[pv] = d
        write_json(WSET, c)
    except Exception:
        pass


def note_model(pv, alias, mid):
    if not mid:
        return
    MODEL_SEEN.setdefault(pv, {})[alias or ""] = str(mid)
    try:
        c = w_settings()
        c.setdefault("modelSeen", {}).setdefault(pv, {})[alias or ""] = str(mid)
        write_json(WSET, c)
    except Exception:
        pass


def note_quota_claude(info):
    """Claude Code 的 rate_limit_event：status（allowed／allowed_warning／rejected）、utilization（0～1，快用完時才有）、resetsAt"""
    st, u, rs = info.get("status"), info.get("utilization"), info.get("resetsAt")
    if isinstance(rs, (int, float)) and rs > 1e12:
        rs = rs / 1000
    d = {"state": "out" if st == "rejected" else "warn" if st == "allowed_warning" else "ok", "kind": info.get("rateLimitType") or ""}
    if isinstance(u, (int, float)):
        d["left"] = max(0, round(100 - u * 100))
    if isinstance(rs, (int, float)):
        d["resets"] = int(rs)
    set_quota("claude", d)


def note_quota_codex(stdout):
    """Codex 的 --json 事件裡有 rate_limits（used_percent），找出來"""
    best = None

    def walk(o):
        nonlocal best
        if isinstance(o, dict):
            if isinstance(o.get("used_percent"), (int, float)):
                rs = o.get("resets_at") or (time.time() + o["resets_in_seconds"] if isinstance(o.get("resets_in_seconds"), (int, float)) else None)
                if best is None or o["used_percent"] > best[0]:
                    best = (o["used_percent"], rs)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for line in (stdout or "").splitlines():
        try:
            walk(json.loads(line))
        except ValueError:
            pass
    if best:
        left = max(0, round(100 - best[0]))
        set_quota("codex", {"state": "out" if left <= 0 else "warn" if left <= 20 else "ok", "left": left, **({"resets": int(best[1])} if best[1] else {})})


def quota_of(pv):
    q = QUOTA.get(pv) or (w_settings().get("quota") or {}).get(pv)
    if q and q.get("resets") and q["resets"] < time.time() and q.get("state") != "ok":
        q = dict(q, state="ok", left=None)   # 已經過了重置時間
    cool = ai_cooling(pv)
    if cool and cool.get("kind") == "quota":
        q = dict(q or {}, state="out")
    return q


def model_name(pv):
    """現在這一位用的模型名稱：自動的話，看過實際模型就顯示它，不然寫「自動」"""
    try:
        v = model_of(pv)
        if v == "":
            u = (getattr(AI_LAST, "used", None) or {}).get(pv)
            if u is None:
                return "自動"
            if u == "":
                return "帳號預設"
            v = u
        n = next((x[1] for x in MODELS.get(pv, []) if x[0] == v), v)
        return model_label(pv, v, n)
    except Exception:
        return ""


def model_label(pv, v, name):
    """顯示用的模型名稱：看過實際模型 id 就顯示版本（claude-opus-5-5-… → Opus 5.5）"""
    mid = (MODEL_SEEN.get(pv) or (w_settings().get("modelSeen") or {}).get(pv) or {}).get(v or "")
    if pv == "claude" and mid:
        m = re.search(r"(opus|sonnet|haiku|fable)-(\d+)(?:-(\d))?(?!\d)", mid)
        if m:
            return m.group(1).capitalize() + " " + m.group(2) + ("." + m.group(3) if m.group(3) else "")
    return name


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def error_summary(text):
    """從一大串錯誤訊息（含 stack trace）抓出真正的那一句"""
    text = ANSI.sub("", text or "")
    try:
        w = _json_from(text)
        if isinstance(w, dict) and w.get("error"):
            e = w["error"]
            return str(e.get("message") if isinstance(e, dict) else e)
    except Exception:
        pass
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    keep = [l for l in lines if not l.startswith("at ") and not l.startswith("file:") and not re.match(r"^[{}\[\],]+$", l)]
    pick = [l for l in keep if re.search(r"error|Error|failed|denied|required|not |cannot|must|請|錯誤", l)]
    return " / ".join((pick or keep or lines or ["沒有回應"])[:2])[:400]


def friendly_error(pv, msg):
    """把常見的錯誤翻成看得懂的中文和解法"""
    m, hints = msg or "", []
    if re.search(r"GOOGLE_CLOUD_PROJECT|ProjectIdRequired", m):
        hints.append("這個 Google 帳號（公司或學校的 Workspace 帳號）需要 Google Cloud 專案才能用 Gemini CLI。請改用個人的 Gmail 帳號登入。")
    elif re.search(r"[Ii]neligible|not eligible", m):
        hints.append("Google 判定這個帳號不能用 Gemini CLI。常見原因是家庭群組成員、帳號年齡設定未滿 18、或地區不支援。可以按「登出／換帳號」改用另一個個人 Gmail，或先改用 Claude／ChatGPT。")
    elif re.search(r"[Vv]alidat|[Vv]erif", m):
        hints.append("Google 要求這個帳號先驗證一次。按「用終端機登入／設定」，照畫面完成驗證後關掉，再按「測試連線」。")
    elif re.search(r"trust", m, re.I):
        hints.append("資料夾還沒被信任：請重開程式再試一次。")
    elif re.search(r"log ?in|auth|credential|401|403", m, re.I):
        hints.append("需要重新登入：按「登入」。")
    elif re.search(r"quota|429|rate", m, re.I):
        hints.append("用量達到上限，等一下再試。")
    return (" ".join(hints) + "（原始訊息：" + m[:220] + "）") if hints else m


def ai_test(pv):
    try:
        t0 = time.time()
        ai_level("easy")
        out = ai_run_one(pv, "This is a connection test. Reply with exactly one word: OK", 60)
        ai_level(None)
        ok = "OK" in out.upper()
        if ok:
            AI_COOL.pop(pv, None)
        set_tested(pv, ok, ("%.0f 秒" % (time.time() - t0)) if ok else ("回應：" + out[:80]))
    except subprocess.TimeoutExpired:
        set_tested(pv, False, "超過 60 秒沒有回應，當作失敗。請確認已登入，或按「用終端機登入」看看卡在哪裡。")
    except Exception as e:
        set_tested(pv, False, friendly_error(pv, str(e)))
    r = (w_settings().get("tested") or {}).get(pv)
    if r and not r.get("ok"):
        print("%s 連線測試失敗（模型：%s）：%s" % (PROVIDERS[pv]["name"], model_name(pv), r.get("msg")))
    return r


def set_model(pv, m):
    """換模型：存起來，馬上重新測試連線；這個模型不能用就換回原本的"""
    if pv not in PROVIDERS or not any(m == x[0] for x in MODELS[pv]):
        raise ValueError("不認得的模型")
    c = w_settings()
    old = model_of(pv)
    c.setdefault("models", {})[pv] = m
    write_json(WSET, c)
    t = ai_test(pv) or {}
    if not t.get("ok") and re.search(r"model|模型|not (found|available|supported)|invalid|unknown", t.get("msg") or "", re.I):
        c = w_settings()
        c.setdefault("models", {})[pv] = old
        c.setdefault("modelBad", {}).setdefault(pv, {})[m] = int(time.time())      # 這個帳號用不了：先關掉，一週後再讓你試
        write_json(WSET, c)
        ai_test(pv)
        return {"ok": False, "reverted": True, "model": old, "error": "這個模型現在不能用（" + (t.get("msg") or "")[:160] + "），已經換回原本的。"}
    if t.get("ok"):
        c = w_settings()
        (c.get("modelBad") or {}).get(pv, {}).pop(m, None)
        write_json(WSET, c)
    return {"ok": bool(t.get("ok")), "model": m, "tested": t}


def current_provider():
    c = w_settings()
    pv = c.get("provider")
    if pv in PROVIDERS and ai_bin(pv):
        return pv
    for p in PROVIDER_ORDER:
        if ai_bin(p) and ((c.get("tested") or {}).get(p) or {}).get("ok"):
            return p
    return "claude" if ai_bin("claude") else None


def engine_status(pv=None):
    ids = [pv] if pv in PROVIDERS else list(PROVIDER_ORDER)
    c = w_settings()
    return {"providers": {k: provider_status(k) for k in ids}, "selected": current_provider(), "autoSwitch": ai_auto(),
            "provider": c.get("provider"), "tasks": {k: {"label": v, "choice": (c.get("tasks") or {}).get(k) or "", "using": task_provider(k)} for k, v in TASKS.items()},
            "stepfunKey": ("…" + stepfun_key()[-4:]) if stepfun_key() else None}


# ---------- 背景工作（建檔流水線，大量派 agent）：每一類工作選引擎，每個引擎選各角色的模型（本人 2026-10-27） ----------
# Claude Code 派 agent 時用 opus／sonnet／haiku 這些代稱；改 ANTHROPIC_DEFAULT_*_MODEL 就能換成別的模型，流程不用改。
# StepFun 也走 Claude Code（StepFun 提供 Anthropic 相容的 API）：同一個工作裡全部角色都用 Step 的模型。
JOB_GROUPS = {
    "build": ("建檔（教授文章、解析卡、總覽、驗收）", ("new", "continue", "reply", "exception", "deep")),
    "library": ("Meeting 文獻（整理重點、擬初稿）", ("library", "library-draft")),
    "research": ("查詢與比對（教員名單、博士學程、補資訊、比對、計畫書草稿）", ("faculty", "programs", "discover-enrich", "match", "propose")),
    "docs": ("我的文件（AI 編修、翻譯）", ("doc-edit", "doc-translate")),
}
JOB_ENGINES = {"claude": "Claude（你的 Claude 帳號）", "stepfun": "StepFun（經 Claude Code）", "codex": "Codex（ChatGPT）"}
TIERS = {"main": "主控：照流程派工、跑腳本", "opus": "重的工作：讀全文、寫解析卡與重點、推翻、驗收", "sonnet": "一般：翻譯、查詢、比對", "haiku": "簡單的小工作"}
TIER_MODELS = {"claude": [("", "帳號預設"), ("claude-opus-5-5", "Opus 5.5"), ("claude-sonnet-5-5", "Sonnet 5.5"), ("claude-haiku-5-5", "Haiku 5.5")],
               "stepfun": [("step-5-preview", "Step 5 Preview"), ("step-3.7-flash", "Step 3.7 Flash"), ("step-3.5-flash", "Step 3.5 Flash")]}
TIER_DEFAULT = {"claude": {"main": "", "opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"},
                "stepfun": {"main": "step-5-preview", "opus": "step-5-preview", "sonnet": "step-5-preview", "haiku": "step-3.7-flash"}}
STEPFUN_BASES = {"api": ("https://api.stepfun.ai", "一般 API（按用量計費）"), "plan": ("https://api.stepfun.ai/step_plan", "Step Plan 訂閱")}

# 流程圖上會用到 AI 的步驟（派 agent 的角色）：各自可以選模型（本人 2026-10-27）。
# tier＝skill 裡寫的 model 代稱；progress＝工作進度那一關（pipeline/progress.py 的步驟）
FLOW_STEPS = [
    {"id": "setup.focus", "group": "build", "skill": "prof-setup", "role": "挑選者", "label": "挑必讀前五篇", "tier": "opus", "progress": "list"},
    {"id": "setup.programs", "group": "build", "skill": "prof-setup", "role": "查詢者", "label": "查博士學程", "tier": "sonnet", "progress": "programs"},
    {"id": "grants.extract", "group": "build", "skill": "prof-grants", "role": "抽取者", "label": "抽取論文致謝的計畫", "tier": "sonnet", "progress": "grants"},
    {"id": "grants.refute", "group": "build", "skill": "prof-grants", "role": "推翻者", "label": "推翻只有致謝當證據的計畫", "tier": "opus", "progress": "grants"},
    {"id": "cards.reader", "group": "build", "skill": "prof-cards", "role": "閱讀者", "label": "讀全文寫解析卡", "tier": "opus", "progress": "cards"},
    {"id": "cards.refute", "group": "build", "skill": "prof-cards", "role": "推翻者", "label": "推翻解析卡的推論", "tier": "opus", "progress": "cards"},
    {"id": "digest.digester", "group": "build", "skill": "prof-digest", "role": "整理者", "label": "重點、圖表、研究方法", "tier": "opus", "progress": "digest"},
    {"id": "profile.writer", "group": "build", "skill": "prof-profile", "role": "總覽撰寫者", "label": "寫教授總覽", "tier": "opus", "progress": "profile"},
    {"id": "profile.refute", "group": "build", "skill": "prof-profile", "role": "總覽推翻者", "label": "推翻總覽的句子", "tier": "opus", "progress": "profile"},
    {"id": "match.matcher", "group": "build", "skill": "prof-match", "role": "比對者", "label": "跟你的研究比對", "tier": "sonnet", "progress": "match"},
    {"id": "verify.judge", "group": "build", "skill": "prof-verify", "role": "獨立驗收者", "label": "獨立驗收", "tier": "opus", "progress": "verify"},
    {"id": "library.digester", "group": "library", "skill": "prof-library", "role": "整理者", "label": "整理重點、圖表、研究方法", "tier": "opus"},
    {"id": "library.drafter", "group": "library", "skill": "prof-library", "role": "擬稿者", "label": "用勾選的文獻擬初稿", "tier": "opus"},
    {"id": "research.discover", "group": "research", "skill": "prof-discover", "role": "查詢者", "label": "補排名、學程、資助、實驗室", "tier": "sonnet"},
    {"id": "research.match", "group": "research", "skill": "prof-match", "role": "比對者", "label": "重新比對", "tier": "sonnet"},
    {"id": "research.propose", "group": "research", "skill": "prof-propose", "role": "擬稿者", "label": "研究計畫書草稿", "tier": "opus"},
    {"id": "docs.editor", "group": "docs", "skill": "my-docs", "role": "編修者", "label": "每段 AI 編修", "tier": "opus"},
    {"id": "docs.translator", "group": "docs", "skill": "my-docs", "role": "翻譯者", "label": "翻成中文", "tier": "sonnet"},
]
FLOW_IDS = {s["id"]: s for s in FLOW_STEPS}


def job_group(kind):
    return next((g for g, (_, kinds) in JOB_GROUPS.items() if kind in kinds), None)


def job_tiers(engine):
    t = dict(TIER_DEFAULT.get(engine) or {})
    t.update(((w_settings().get("jobs") or {}).get("tiers") or {}).get(engine) or {})
    return t


def save_job_settings(d):
    """設定頁送來的：只收認得的類別、引擎、模型。"""
    c = w_settings()
    j = dict(c.get("jobs") or {})
    if isinstance(d.get("groups"), dict):
        g = dict(j.get("groups") or {})
        for k, v in d["groups"].items():
            if k in JOB_GROUPS:
                if v in JOB_ENGINES:
                    g[k] = v
                else:
                    g.pop(k, None)
        j["groups"] = {k: v for k, v in g.items() if k in JOB_GROUPS and v in JOB_ENGINES}
    if isinstance(d.get("tiers"), dict):
        t = {e: dict(v) for e, v in (j.get("tiers") or {}).items()}
        for e, roles in d["tiers"].items():
            ok = {m for m, _ in TIER_MODELS.get(e, [])}
            if e in TIER_MODELS and isinstance(roles, dict):
                cur = t.setdefault(e, {})
                for r, m in roles.items():
                    if r in TIERS and m in ok:
                        cur[r] = m
        j["tiers"] = t
    if isinstance(d.get("steps"), dict):  # 流程圖上單一步驟的模型；空字串＝照角色預設
        st = {e: dict(v) for e, v in (j.get("steps") or {}).items()}
        for e, chosen in d["steps"].items():
            ok = {m for m, _ in TIER_MODELS.get(e, []) if m}
            if e in TIER_MODELS and isinstance(chosen, dict):
                cur = st.setdefault(e, {})
                for sid, m in chosen.items():
                    if sid in FLOW_IDS and m in ok:
                        cur[sid] = m
                    elif sid in FLOW_IDS and not m:
                        cur.pop(sid, None)
        j["steps"] = {e: v for e, v in st.items() if v}
    if "stepfunBase" in d:
        if d["stepfunBase"] in STEPFUN_BASES:
            j["stepfunBase"] = d["stepfunBase"]
        else:
            j.pop("stepfunBase", None)
    c["jobs"] = j
    write_json(WSET, c)
    return j


def job_launch(kind, default_engine="claude"):
    """背景工作怎麼啟動：engine（claude／codex 哪個 CLI）、主控模型、要加的環境變數、要拿掉的環境變數、實際用誰（via）。"""
    j = w_settings().get("jobs") or {}
    via = (j.get("groups") or {}).get(job_group(kind) or "") or default_engine
    if via == "codex":
        return {"engine": "codex", "via": "codex", "model": None, "env": {}, "unset": [], "label": "Codex"}
    t = job_tiers(via)
    slots, note = _step_slots(job_group(kind), via, t)
    env = {f"ANTHROPIC_DEFAULT_{r.upper()}_MODEL": slots[r] for r in ("opus", "sonnet", "haiku") if slots.get(r)}
    if slots.get("opus"):
        env["ANTHROPIC_DEFAULT_FABLE_MODEL"] = slots["opus"]
    unset = []
    if via == "stepfun":
        key = stepfun_key()
        if not key:
            raise RuntimeError("這類背景工作設定用 StepFun，但還沒貼 StepFun 的 key：到「設定 → AI 小幫手」貼上，或改回 Claude")
        env.update({"ANTHROPIC_BASE_URL": STEPFUN_BASES[j.get("stepfunBase") or "api"][0], "ANTHROPIC_AUTH_TOKEN": key,
                    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000", "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"})
        unset = ["ANTHROPIC_API_KEY"]  # 不要跟 Claude 帳號的 key 混用
    label = (JOB_ENGINES.get(via, via).split("（")[0] + " " + (t.get("main") or "預設")).strip()
    return {"engine": "claude", "via": via, "model": t.get("main") or None, "env": env, "unset": unset, "label": label, "note": note}


def _step_slots(group, engine, tiers):
    """這類工作每個 AI 步驟要的模型 → 分到 opus／sonnet／haiku 三格（Claude Code 派 agent 只認這些代稱）；
    跟 skill 寫的代稱不同的步驟，寫成一段說明加在工作指示後面。每家最多三種模型，三格一定放得下。"""
    chosen = ((w_settings().get("jobs") or {}).get("steps") or {}).get(engine) or {}
    steps = [s for s in FLOW_STEPS if s["group"] == group]
    want = {s["id"]: chosen.get(s["id"]) or tiers.get(s["tier"]) for s in steps}
    slots = {r: tiers.get(r) for r in ("opus", "sonnet", "haiku")}
    need = [m for m in dict.fromkeys(want.values()) if m]
    alias = {}
    for r in ("opus", "sonnet", "haiku"):  # 已經在某一格的模型留在原格
        if slots[r] in need and slots[r] not in alias:
            alias[slots[r]] = r
    used_by = {alias[m] for m in alias}
    for m in need:
        if m not in alias:
            free = next((r for r in ("haiku", "sonnet", "opus") if r not in used_by), None)
            if free is None:
                raise ValueError("一類工作最多用三種模型")
            slots[free], alias[m] = m, free
            used_by.add(free)
    pick = lambda s: s["tier"] if slots.get(s["tier"]) == want[s["id"]] else alias[want[s["id"]]]  # 自己那一格就是要的模型：照 skill
    diff = [f"{s['skill']} {s['role']} → {pick(s)}" for s in steps if want[s["id"]] and pick(s) != s["tier"]]
    note = ("（本人在設定指定的模型：派下面這些 agent 時，Agent 工具的 model 參數改用指定的代稱，其他照 skill 寫的：" + "；".join(diff) + "。）") if diff else ""
    return slots, note


def jobs_status(default_engine="claude"):
    j = w_settings().get("jobs") or {}
    return {"groups": [{"id": g, "label": lab, "engine": (j.get("groups") or {}).get(g) or default_engine} for g, (lab, _) in JOB_GROUPS.items()],
            "engines": JOB_ENGINES, "roles": TIERS, "models": {e: [{"v": v, "name": n} for v, n in ms] for e, ms in TIER_MODELS.items()},
            "tiers": {e: job_tiers(e) for e in TIER_MODELS}, "stepfunBase": j.get("stepfunBase") or "api",
            "steps": FLOW_STEPS, "stepModels": j.get("steps") or {},
            "bases": {k: v[1] for k, v in STEPFUN_BASES.items()}}
