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


def find_codex():
    """Codex CLI（OpenAI）：Claude 額度用完時的備用引擎。npm 裝在使用者資料夾時 PATH 可能沒有，多找幾個地方。"""
    import os
    for c in (shutil.which("codex"), shutil.which("codex.cmd"), os.path.expanduser("~/.npm-global/bin/codex"),
              os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd")):
        if c and os.path.exists(c):
            return c
    return None


CODEX_PREFIX = ("（你在 phdeasy 專案根目錄。專案規則在 CLAUDE.md；各階段的做法在 .claude/skills/<名稱>/SKILL.md，需要時自己讀。"
                "說明裡寫「派 subagent／派 agent」的地方，你沒有 subagent，就自己照那份工作說明一步一步做。"
                "指令一律在專案根目錄用 uv run python scripts/… 跑。）\n")


def codex_cmd(codex, prompt, session=None):
    """Codex 在工作區裡可以寫檔、可以連網（流水線要查 OpenAlex 等）；不給整台電腦的權限。"""
    base = [codex, "exec", "--json", "--skip-git-repo-check", "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
    return base + (["resume", session, prompt] if session else [CODEX_PREFIX + prompt])


def describe_codex(ev):
    """Codex 的 --json 事件 → 給本人看的一行。"""
    t, item = ev.get("type"), ev.get("item") or {}
    if t == "thread.started":
        return "Codex 已啟動"
    if t == "item.completed":
        if item.get("type") == "agent_message":
            return (item.get("text") or "").strip() or None
        if item.get("type") == "command_execution":
            return f"▸ 指令：{str(item.get('command') or '')[:160]}"
        if item.get("type") == "file_change":
            return "▸ 改檔：" + "、".join(c.get("path", "") for c in item.get("changes") or [])[:160]
        return None
    if t == "turn.completed":
        return "✓ 這一段跑完了"
    if t in ("turn.failed", "error"):
        return f"✗ 結束：{((ev.get('error') or {}).get('message') or ev.get('message') or '')[:200]}"
    return None


def claude_cmd(claude, prompt, session=None):
    cmd = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "dontAsk", "--allowedTools", ",".join(ALLOWED_TOOLS)]
    if session:
        cmd += ["--resume", session]
    return cmd


UNATTENDED = ("（這是應用程式在背景執行的工作，沒有人在旁邊按允許：派 subagent 一律在前景等它回來，不要用背景執行；"
              "到停點或熔斷之前不要結束這一輪；權限被拒就停下並說明卡在哪，不要繞路。）")


def slug_of(name):
    """教授資料夾名稱：<姓>-<名> 小寫（同 prof-setup）；逗號後的學位、括號裡的字、中間名都拿掉。"""
    import re
    import unicodedata
    n = re.sub(r"\(.*?\)", " ", (name or "").split(",")[0])
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    toks = [t for t in re.split(r"[^A-Za-z-]+", n) if t and not re.fullmatch(r"(?i)(dr|prof|professor|md|phd|ms|mph|rn)", t)]
    if not toks:
        return None
    return re.sub(r"-+", "-", f"{toks[-1]}-{toks[0]}".lower()) if len(toks) > 1 else toks[0].lower()


def prompt_new(name, institution, orcid=None, slug=None):
    p = f"幫我建教授檔案：{name.strip()}，{institution.strip()}"
    if orcid and orcid.strip():
        p += f"（ORCID {orcid.strip()}）"
    if slug:
        p += f"。批次資料夾用 runs/{slug}"
    return p + "。照 CLAUDE.md 與 prof-setup 跑到停 1，把停 1 要我決定的事列清楚後停下。" + UNATTENDED


def prompt_continue(slug):
    return (f"繼續 runs/{slug}：先跑 drive_sync，讀 state.json，從目前的 stage 接續；"
            "自動段一路跑到下一個停點（停 1 或停 2）或熔斷，然後把要我決定的事列清楚後停下。" + UNATTENDED)


def prompt_match(slug):
    return (f"對 runs/{slug} 重新比對：照 .claude/skills/prof-match/SKILL.md，先把 work/match/draft.json 與 refute.json 移到 work/match/_old/（不要刪），"
            "依 runs/_me/me.json 目前的研究興趣與 CV（不含與教授共同討論的研究計畫）重新跑 2.1–2.5，完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_library_process(slug):
    return (f"處理 runs/{slug} 的討論文獻：照 .claude/skills/prof-library/SKILL.md 的 A 段（drive_sync → library.py process → 整理者（重點＋研究方法一次寫完）→ "
            "digest check（只修一輪）→ assemble → ris → build_site），完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_library_draft(slug, ids):
    return (f"用 runs/{slug} 的討論文獻擬初稿：照 .claude/skills/prof-library/SKILL.md 的 B 段，勾選的文獻是 {','.join(ids)}；"
            "只能引這幾篇與她的文章，完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_doc_translate(key, version):
    return (f"把本人的文件 {key} 第 {version} 版翻成中文：照 .claude/skills/my-docs/SKILL.md 的 A 段（翻譯者 → check → index → drive_sync），"
            "完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_doc_edit(key, version, block, instruction):
    req = (instruction or "").strip() or "整體潤飾"
    return (f"AI 編修本人的文件 {key}：第 {version} 版、第 {block + 1} 段（--block {block}），本人的要求：「{req}」。"
            "照 .claude/skills/my-docs/SKILL.md 的 B 段（編修者 → apply-edit 存成新版本 → index → drive_sync），只改這一段，完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_discover_enrich():
    return ("幫查詢教授的結果補資訊：照 .claude/skills/prof-discover/SKILL.md 的 A（--enrich-todo 只列還沒補過的 → 查詢者上網查 QS／US News 排名、"
            "每位教授掛名的博士學程與資助、實驗室網址，每個值附出處 → 合成 enrich-new.json → --merge），完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_programs(slug, name, institution, orcid=None):
    return (f"查 {name}（{institution}{'，ORCID ' + orcid if orcid else ''}）本人掛名、可以收博士生的博士學程與各學程的資助："
            f"照 .claude/skills/prof-discover/SKILL.md 的 B，寫 runs/{slug}/work/programs.json，再跑 scripts/programs.py runs/{slug}，"
            "完成後回報 DONE 那一行。" + UNATTENDED)


def prompt_propose(slug):
    return (f"幫 runs/{slug} 擬研究構想草稿：先跑 drive_sync；已有 work/proposal/draft.json 就先移到 work/proposal/_old/（不要刪）；"
            "照 .claude/skills/prof-propose/SKILL.md 跑 inputs → 擬稿 → check（只修一輪）→ assemble → build_site，"
            "只依本人的 CV 與這位教授目前期間內的經費，不要把本人與教授共同討論的研究計畫當成本人的；完成後回報 DONE 那一行。" + UNATTENDED)


FULLTEXT_KINDS = {"abstract_only", "title_only", "no_source", "no_text", "title_mismatch", "not_main_text", "unreadable", "wrong_file"}
REJUDGE_KINDS = {"dual_track_unresolved", "field_unresolved", "no_card"}


def exception_actions(kind):
    """例外紀錄上可以按的按鈕：[(動作, 按鈕文字)]。每個都會開一個 Claude Code 背景工作。"""
    if kind in FULLTEXT_KINDS:
        return [("retry_fulltext", "讓 AI 再找一次全文")]
    if kind == "grant_unresolved":
        return [("grant_yes", "是她的計畫"), ("grant_no", "不是，拿掉")]
    if kind == "possible_author_split":
        return [("split_merge", "是同一人，合併"), ("split_keep", "不同人，分開")]
    if kind in REJUDGE_KINDS:
        return [("rejudge", "請 AI 重新判")]
    return []


def prompt_exception(slug, exc, action, note=""):
    if action != "note" and action not in {a for a, _ in exception_actions(exc.get("kind"))}:
        raise ValueError(f"{exc.get('kind')} 沒有「{action}」這個動作")
    head = f"runs/{slug} 的例外紀錄：{exc.get('id')}（{exc.get('kind')}：{exc.get('detail', '')}）。"
    extra = f"本人補充：{note.strip()}。" if note and note.strip() else ""
    tail = ("做完把這筆例外標為已解決（state_cli／pipeline.exceptions.resolve_exception，寫明怎麼解決），"
            "跑 build_home.py runs，最後用兩三句話回報結果。" + UNATTENDED)
    if action == "retry_fulltext":
        return (head + extra + f"請再找一次這篇的全文：先跑 drive_sync，再跑 `uv run python scripts/setup_fulltext.py runs/{slug} --only {exc['id']} --retry-missing`"
                "（本人放進 inbox/ 的 PDF 也會被用上），接著跑 ingest。如果這篇改成有全文：照 prof-cards 只重做這一篇（甲、乙、核對、裁決、推翻、組裝），"
                "重翻這篇的 i18n，跑 profile.py facts 與 assemble。如果還是找不到，就保留例外、在回報裡寫清楚試了哪些來源。" + tail)
    if action in ("grant_yes", "grant_no"):
        verdict = "這筆計畫是她的（請依計畫實際資料把狀態改為 confirmed，角色照來源判斷）" if action == "grant_yes" else "這筆計畫不是她的，請移到 out/rejected.md"
        return (head + extra + f"本人決定：{verdict}。記進 work/owner_decisions.json 與 protocol.md 的例外，照 prof-grants 的規則重跑 apply-refute 與 grants.csv。" + tail)
    if action in ("split_merge", "split_keep"):
        verdict = "這幾個作者 id 是同一人，請合併（寫進 work/owner_decisions.json 的 author_aliases）" if action == "split_merge" else "這幾個作者 id 是不同人，請維持分開（寫進 keep_separate）"
        return (head + extra + f"本人決定：{verdict}。照 prof-network 重跑 build 與 Haiku 計數 check，總覽受影響的句子照 prof-profile 修正一輪。" + tail)
    if action == "rejudge":
        return (head + extra + "請照 prof-cards 的規則，只針對這一篇重新做會出這個例外的那一步（雙軌裁決或重新寫卡），再組裝。" + tail)
    return head + extra + "照本人的補充處理這筆例外，遵守 CLAUDE.md 與對應 skill 的規則。" + tail


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


MAX_JOBS = 3  # 同時最多幾個背景工作（每位教授一次一個）


class Jobs:
    def __init__(self, workspace, runs, claude=None, popen=subprocess.Popen):
        self.workspace, self.dir = Path(workspace), Path(runs) / "_app" / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.claude, self.popen = claude, popen
        self.codex = None
        self.engine = lambda: "claude"  # 應用程式設定裡可以改成 "codex"（Claude 額度用完時的備用）
        self.procs, self.lock = {}, threading.Lock()  # {工作 id: 程序}
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

    def active(self):
        """正在跑的工作（依開始時間）。"""
        ids = [jid for jid, p in list(self.procs.items()) if p.poll() is None]
        return sorted((j for j in (self.load(i) for i in ids) if j), key=lambda j: j["started"])

    def running(self):
        return any(p.poll() is None for p in list(self.procs.values()))

    def recent(self, n=8):
        js = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime)[-n:]
        return [json.loads(p.read_text()) for p in reversed(js)]

    def start(self, kind, prompt, title, session=None, slug=None, key=None):
        """key：同一個 key 一次只能有一個工作（預設是教授 slug；文件類用文件名）。"""
        engine = self.engine()
        if engine == "codex":
            exe = self.codex or find_codex()
            if not exe:
                raise RuntimeError("找不到 Codex CLI：請先安裝（npm install -g @openai/codex）並登入，或在設定把 AI 引擎改回 Claude Code")
        else:
            exe = self.claude or find_claude()
            if not exe:
                raise RuntimeError("找不到 Claude Code：請先安裝並登入（https://claude.com/claude-code）")
        key = key or slug or kind
        with self.lock:
            act = self.active()
            same = next((j for j in act if j.get("key") == key), None)
            if same:
                raise RuntimeError(f"這位教授（或這份文件）已經有一個工作在跑：{same['title']}，等它到停點或跑完再按" if slug or key.startswith("doc")
                                   else f"已經有一個同類的工作在跑：{same['title']}")
            if len(act) >= MAX_JOBS:
                raise RuntimeError(f"已經有 {MAX_JOBS} 個工作在跑，等其中一個到停點或跑完再開新的")
            job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "kind": kind, "title": title, "key": key,
                   "slug": slug, "prompt": prompt, "session": session, "status": "running",
                   "started": int(time.time()), "ended": None, "result": None, "cost_usd": None, "engine": engine}
            self._save(job)
            log = open(self.dir / f"{job['id']}.log", "a", encoding="utf-8")
            cmd = codex_cmd(exe, prompt, session) if engine == "codex" else claude_cmd(exe, prompt, session)
            proc = self.popen(cmd, cwd=str(self.workspace),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            self.procs[job["id"]] = proc
            threading.Thread(target=self._pump, args=(job, proc, log), daemon=True).start()
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
                if job.get("engine") == "codex":
                    if ev.get("type") == "thread.started":
                        job["session"] = ev.get("thread_id")
                    item = ev.get("item") or {}
                    if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
                        job["result"] = item.get("text")  # 最後一則訊息就是回報
                    text = describe_codex(ev)
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

    def stop(self, jid=None):
        """停一個工作；不給 id 就全部停（關掉程式時）。"""
        hit = False
        for i, p in list(self.procs.items()):
            if (jid is None or i == jid) and p.poll() is None:
                p.terminate()
                hit = True
        return hit
