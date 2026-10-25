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
