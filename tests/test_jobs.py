import io
import json
import time

from pipeline.jobs import ALLOWED_TOOLS, Jobs, claude_cmd, describe, prompt_new


def test_claude_cmd_is_limited_not_bypass():
    cmd = claude_cmd("claude", "hi", session="s1")
    assert "dontAsk" in cmd and "bypassPermissions" not in " ".join(cmd)
    assert cmd[cmd.index("--resume") + 1] == "s1"
    tools = cmd[cmd.index("--allowedTools") + 1]
    assert "Bash(uv run:*)" in tools and "Bash(rm" not in tools and "Bash(*)" not in tools
    assert all(not t.startswith("Bash(") or t.startswith(("Bash(uv ", "Bash(curl -s -m 5")) for t in ALLOWED_TOOLS)


def test_prompt_new_mentions_stop1():
    p = prompt_new("Jane Doe", "Uni", "0000-0001")
    assert "Jane Doe" in p and "Uni" in p and "0000-0001" in p and "停 1" in p


def test_describe_stream_events():
    assert describe({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"description": "跑測試"}}]}}) == "▸ Bash：跑測試"
    assert describe({"type": "result", "subtype": "success", "is_error": False}).startswith("✓")
    assert describe({"type": "user"}) is None


class FakeProc:
    def __init__(self, lines):
        self.stdout = io.StringIO("".join(json.dumps(x) + "\n" for x in lines))
        self.done = False

    def poll(self):
        return 0 if self.done else None

    def wait(self):
        self.done = True
        return 0


def test_jobs_records_session_result_and_calls_hook(tmp_path):
    events = [{"type": "system", "subtype": "init", "session_id": "abc"},
              {"type": "assistant", "message": {"content": [{"type": "text", "text": "到停 1 了"}]}},
              {"type": "result", "subtype": "success", "result": "請確認身分", "total_cost_usd": 1.5, "session_id": "abc"}]
    seen = []
    j = Jobs(tmp_path, tmp_path / "runs", claude="claude", popen=lambda *a, **k: FakeProc(events))
    j.on_done = seen.append
    job = j.start("new", "p", "建檔：X")
    for _ in range(50):
        if seen:
            break
        time.sleep(0.05)
    saved = j.load(job["id"])
    assert saved["session"] == "abc" and saved["result"] == "請確認身分" and saved["status"] == "done" and saved["cost_usd"] == 1.5
    assert any("到停 1 了" in l for l in j.log_tail(job["id"]))
    assert seen and seen[0]["id"] == job["id"]


def test_exception_prompts_by_action():
    from pipeline.jobs import exception_actions, prompt_exception
    assert {a for a, _ in exception_actions("abstract_only")} == {"retry_fulltext"}
    assert {a for a, _ in exception_actions("grant_unresolved")} == {"grant_yes", "grant_no"}
    p = prompt_exception("laranjo", {"id": "W1", "kind": "abstract_only", "detail": "只有摘要"}, "retry_fulltext", "")
    assert "W1" in p and "setup_fulltext.py runs/laranjo --only W1 --retry-missing" in p and "prof-cards" in p
    g = prompt_exception("laranjo", {"id": "ID:CL1", "kind": "grant_unresolved", "detail": "x"}, "grant_no", "不是她的")
    assert "ID:CL1" in g and "不是她的" in g and "本人決定" in g
    import pytest
    with pytest.raises(ValueError):
        prompt_exception("laranjo", {"id": "W1", "kind": "abstract_only"}, "grant_yes", "")


def test_prompt_propose_runs_skill_and_keeps_old_draft():
    from pipeline.jobs import UNATTENDED, prompt_propose
    p = prompt_propose("doe-jane")
    assert "prof-propose" in p and "runs/doe-jane" in p
    assert "_old" in p and "不要刪" in p  # 重新產生時舊草稿只移不刪
    assert "共同討論" in p  # 不拿與 Liliana 討論的研究計畫當本人的
    assert p.endswith(UNATTENDED)


def test_prompt_match_uses_interests_and_cv_only():
    from pipeline.jobs import prompt_match
    p = prompt_match("doe-jane")
    assert "CV" in p and "研究興趣與研究計畫" not in p


def test_codex_cmd_runs_in_workspace_with_network_and_resumes():
    from pipeline.jobs import codex_cmd
    c = codex_cmd("/bin/codex", "做事")
    assert c[:2] == ["/bin/codex", "exec"] and "--json" in c and "workspace-write" in c and c[-1].endswith("做事")
    assert "sandbox_workspace_write.network_access=true" in c
    assert "danger-full-access" not in c
    r = codex_cmd("/bin/codex", "繼續", session="abc-123")
    assert r[r.index("resume") + 1] == "abc-123"


def test_describe_codex_events():
    from pipeline.jobs import describe_codex
    assert describe_codex({"type": "thread.started", "thread_id": "t"}) == "Codex 已啟動"
    assert describe_codex({"type": "item.completed", "item": {"type": "agent_message", "text": "好了"}}) == "好了"
    assert "uv run" in describe_codex({"type": "item.completed", "item": {"type": "command_execution", "command": "uv run python scripts/x.py"}})
    assert describe_codex({"type": "turn.completed"}).startswith("✓")
    assert describe_codex({"type": "turn.failed", "error": {"message": "quota"}}).startswith("✗")


def test_jobs_use_codex_when_chosen(tmp_path):
    import io, json
    from pipeline.jobs import Jobs

    class P:
        def __init__(self, cmd, **kw):
            self.cmd = cmd
            self.stdout = io.StringIO("\n".join(json.dumps(e) for e in [
                {"type": "thread.started", "thread_id": "th-1"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "DONE 完成"}},
                {"type": "turn.completed"}]) + "\n")
        def wait(self): return 0
        def poll(self): return 0
    seen = []
    j = Jobs(tmp_path, tmp_path / "runs", claude="/bin/claude", popen=lambda cmd, **kw: seen.append(cmd) or P(cmd, **kw))
    j.codex, j.engine = "/bin/codex", lambda: "codex"
    job = j.start("x", "做事", "標題")
    import time; time.sleep(0.2)
    done = j.load(job["id"])
    assert seen[0][0] == "/bin/codex" and done["session"] == "th-1" and done["result"] == "DONE 完成" and done["engine"] == "codex"
    assert "CLAUDE.md" in seen[0][-1]  # Codex 不會自己讀 skills：開頭告訴它規則在哪


class HangProc:
    """一直在跑、直到被停掉的假程序。"""
    def __init__(self):
        import threading
        self.ev = threading.Event()
        self.stdout = self
        self.killed = False

    def __iter__(self):
        self.ev.wait(5)
        return iter(())

    def poll(self):
        return 0 if self.ev.is_set() else None

    def wait(self):
        self.ev.wait(5)
        return -15 if self.killed else 0

    def terminate(self):
        self.killed = True
        self.ev.set()


def test_jobs_run_in_parallel_up_to_three_one_per_professor(tmp_path):
    import pytest
    from pipeline.jobs import MAX_JOBS
    procs = []
    j = Jobs(tmp_path, tmp_path / "runs", claude="claude", popen=lambda *a, **k: procs.append(HangProc()) or procs[-1])
    a = j.start("new", "p", "建檔：A", slug="a-a")
    b = j.start("new", "p", "建檔：B", slug="b-b")
    with pytest.raises(RuntimeError, match="這位教授"):
        j.start("continue", "p", "繼續：a-a", slug="a-a")  # 同一位教授一次一個
    j.start("doc-edit", "p", "AI 編修", key="doc:ps")
    assert MAX_JOBS == 3 and len(j.active()) == 3 and j.running()
    with pytest.raises(RuntimeError, match="3 個"):
        j.start("new", "p", "建檔：D", slug="d-d")
    assert j.stop(b["id"]) is True  # 只停 B
    for _ in range(50):
        if len(j.active()) == 2:
            break
        time.sleep(0.05)
    assert {x["id"] for x in j.active()} == {a["id"], j.active()[1]["id"]} and b["id"] not in {x["id"] for x in j.active()}
    assert j.load(b["id"])["status"] == "failed"
    j.stop()  # 不給 id：全部停
    for _ in range(50):
        if not j.running():
            break
        time.sleep(0.05)
    assert not j.running()


def test_no_stop1_decisions_become_buttons():
    """不停在停 1：原本要本人決定的事記成例外，事後在教授頁按按鈕。"""
    from pipeline.exceptions import INFO_KINDS
    from pipeline.jobs import exception_actions, prompt_exception, prompt_new
    for kind, act in (("external_candidates", "add_external"), ("possible_duplicate", "dup_merge"), ("affiliation_mismatch", "drop_work")):
        assert kind in INFO_KINDS and [a for a, _ in exception_actions(kind)] == [act]
        assert "build_site" in prompt_exception("x", {"id": "W1", "kind": kind, "detail": "d"}, act)
    p = prompt_new("Jane Doe", "Uni", slug="doe-jane")
    assert "不要停" in p and "prof-verify" in p
