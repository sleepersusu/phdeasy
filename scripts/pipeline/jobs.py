"""應用程式在背景叫 Claude Code 跑流水線（一次一個工作）。

- 建新教授：`claude -p "幫我建教授檔案：<姓名>，<學校>"`，Claude Code 照 CLAUDE.md 與 skills 跑到停 1。
- 停點回覆：`claude -p --resume <session> "<本人的回覆>"`，接著同一個對話繼續跑。
- 繼續：`claude -p "繼續 runs/<slug>…"`，從 state.json 的 stage 接續（對話不見了也能接）。
權限：dontAsk＋只允許流水線用到的工具，其他一律拒絕（本人 2026-10-25 決定，不用 bypassPermissions）。
工作紀錄在 runs/_app/jobs/<id>.json 與 .log，只在這台電腦（Claude Code 的對話只能在同一台接續）。
"""
import json
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep", "Agent", "Task", "TodoWrite", "WebFetch", "WebSearch",
    "Bash(uv run:*)", "Bash(uv sync:*)", "Bash(uv --version)",
    "Bash(curl -s -m 5 -o /dev/null:*)",  # 開工檢查 OpenAlex 連線
]


def find_claude():
    return shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")


def claude_cmd(claude, prompt, session=None):
    cmd = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "dontAsk", "--allowedTools", ",".join(ALLOWED_TOOLS)]
    if session:
        cmd += ["--resume", session]
    return cmd


UNATTENDED = ("（這是應用程式在背景執行的工作，沒有人在旁邊按允許：派 subagent 一律在前景等它回來，不要用背景執行；"
              "到停點或熔斷之前不要結束這一輪；權限被拒就停下並說明卡在哪，不要繞路。）")


def prompt_new(name, institution, orcid=None):
    p = f"幫我建教授檔案：{name.strip()}，{institution.strip()}"
    if orcid and orcid.strip():
        p += f"（ORCID {orcid.strip()}）"
    return p + "。照 CLAUDE.md 與 prof-setup 跑到停 1，把停 1 要我決定的事列清楚後停下。" + UNATTENDED


def prompt_continue(slug):
    return (f"繼續 runs/{slug}：先跑 drive_sync，讀 state.json，從目前的 stage 接續；"
            "自動段一路跑到下一個停點（停 1 或停 2）或熔斷，然後把要我決定的事列清楚後停下。" + UNATTENDED)


def describe(event):
    """stream-json 的一行 → 給本人看的一行文字（看不懂的事件回 None）。"""
    t = event.get("type")
    if t == "system" and event.get("subtype") == "init":
        return "Claude Code 已啟動"
    if t == "assistant":
        out = []
        for c in (event.get("message") or {}).get("content") or []:
            if c.get("type") == "text" and c.get("text", "").strip():
                out.append(c["text"].strip())
            elif c.get("type") == "tool_use":
                inp = c.get("input") or {}
                what = inp.get("description") or inp.get("command") or inp.get("file_path") or inp.get("prompt", "")[:80]
                out.append(f"▸ {c.get('name')}：{str(what)[:160]}")
        return "\n".join(out) or None
    if t == "result":
        return "✓ 這一段跑完了" if event.get("subtype") == "success" and not event.get("is_error") else f"✗ 結束：{event.get('subtype')}"
    return None


class Jobs:
    def __init__(self, workspace, runs, claude=None, popen=subprocess.Popen):
        self.workspace, self.dir = Path(workspace), Path(runs) / "_app" / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.claude, self.popen = claude, popen
        self.proc, self.lock = None, threading.Lock()
        self.on_done = None  # 工作結束後要做的事（例：重建資料、同步雲端）

    def _path(self, jid):
        return self.dir / f"{jid}.json"

    def load(self, jid):
        p = self._path(jid)
        return json.loads(p.read_text()) if p.exists() else None

    def _save(self, job):
        self._path(job["id"]).write_text(json.dumps(job, ensure_ascii=False, indent=1))

    def latest(self):
        js = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        return json.loads(js[-1].read_text()) if js else None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, kind, prompt, title, session=None, slug=None):
        claude = self.claude or find_claude()
        if not claude:
            raise RuntimeError("找不到 Claude Code：請先安裝並登入（https://claude.com/claude-code）")
        with self.lock:
            if self.running():
                raise RuntimeError("已經有一個工作在跑，等它到停點或跑完再開新的")
            job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "kind": kind, "title": title,
                   "slug": slug, "prompt": prompt, "session": session, "status": "running",
                   "started": int(time.time()), "ended": None, "result": None, "cost_usd": None}
            self._save(job)
            log = open(self.dir / f"{job['id']}.log", "a", encoding="utf-8")
            self.proc = self.popen(claude_cmd(claude, prompt, session), cwd=str(self.workspace),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            threading.Thread(target=self._pump, args=(job, self.proc, log), daemon=True).start()
            return job

    def _pump(self, job, proc, log):
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                text = line
            else:
                if ev.get("session_id"):
                    job["session"] = ev["session_id"]
                if ev.get("type") == "result":
                    job["result"] = ev.get("result")
                    job["cost_usd"] = ev.get("total_cost_usd")
                text = describe(ev)
            if text:
                log.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
                log.flush()
        code = proc.wait()
        log.close()
        job.update(status="done" if code == 0 else "failed", ended=int(time.time()))
        self._save(job)
        if self.on_done:
            self.on_done(job)

    def log_tail(self, jid, n=200):
        p = self.dir / f"{jid}.log"
        return p.read_text(encoding="utf-8").splitlines()[-n:] if p.exists() else []

    def stop(self):
        if self.running():
            self.proc.terminate()
            return True
        return False
