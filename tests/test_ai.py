"""故意埋錯：AI 小幫手（照 ieltsgod）—— 失敗原因分類、自動換下一位、暫停、模型自動挑、額度紀錄。"""
import json

import pytest

import pipeline.ai as ai


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    ai.configure(tmp_path)
    ai.AI_COOL.clear()
    ai.AI_ALERTS.clear()
    ai.QUOTA.clear()
    ai.AI_LAST.__dict__.clear()
    monkeypatch.setattr(ai, "ai_bin", lambda pv: f"/bin/{pv}")
    return tmp_path


def test_fail_kind():
    assert ai.ai_fail_kind("Error 429: rate limit reached") == "quota"
    assert ai.ai_fail_kind("You have hit your usage limit") == "quota"
    assert ai.ai_fail_kind("Not logged in · Please run /login") == "auth"
    assert ai.ai_fail_kind("request timed out") == "timeout"
    assert ai.ai_fail_kind("segfault") == "other"


def test_auto_model_picks_cheap_for_easy_work_and_skips_bad_models():
    ai.ai_level("easy")
    assert ai.model_for("claude") == "claude-haiku-5-5"
    ai.ai_level("hard")
    assert ai.model_for("codex") == "gpt-6.1-sol"
    c = ai.w_settings()
    c["modelBad"] = {"codex": {"gpt-6.1-sol": __import__("time").time()}}
    ai.write_json(ai.WSET, c)
    assert ai.model_for("codex") == ""  # 這個帳號用不了：改用帳號預設
    ai.w_set(models={"claude": "claude-sonnet-5-5"})
    assert ai.model_for("claude") == "claude-sonnet-5-5"  # 本人選的優先
    ai.w_set(models={"claude": "made-up"})
    assert ai.model_of("claude") == ""  # 不認得的模型不用


def test_switches_to_next_tested_ai_and_cools_failed_one(monkeypatch):
    for pv in ("claude", "codex"):
        ai.set_tested(pv, True)
    calls = []

    def one(pv, prompt, timeout=600):
        calls.append(pv)
        if pv == "claude":
            raise RuntimeError("Claude AI usage limit reached")
        return "答案"
    monkeypatch.setattr(ai, "ai_run_one", one)
    assert ai.ai_run("claude", "hi") == "答案"
    assert calls == ["claude", "codex"] and ai.ai_used("claude") == "codex"
    assert ai.ai_cooling("claude")["kind"] == "quota"
    assert any("已自動改用 ChatGPT" in a["msg"] for a in ai.AI_ALERTS)
    calls.clear()
    assert ai.ai_run("claude", "hi") == "答案" and calls == ["codex"]  # 暫停中的不再試
    assert ai.quota_of("claude")["state"] == "out"


def test_untested_ai_is_not_used_as_backup_and_auto_switch_can_be_off(monkeypatch):
    ai.set_tested("claude", True)  # codex、gemini 沒測過：不能當備援
    monkeypatch.setattr(ai, "ai_run_one", lambda pv, p, timeout=600: (_ for _ in ()).throw(RuntimeError("429 too many requests")))
    with pytest.raises(RuntimeError):
        ai.ai_run("claude", "hi")
    assert any("沒有別的 AI 可以接手" in a["msg"] for a in ai.AI_ALERTS)
    ai.set_tested("codex", True)
    ai.w_set(autoSwitch=False)
    calls = []
    monkeypatch.setattr(ai, "ai_run_one", lambda pv, p, timeout=600: calls.append(pv) or (_ for _ in ()).throw(RuntimeError("429")))
    with pytest.raises(RuntimeError):
        ai.ai_run("claude", "hi")
    assert calls == ["claude"]  # 關掉自動換：只用選的那位


def test_all_fail_message_lists_each(monkeypatch):
    ai.set_tested("claude", True)
    ai.set_tested("codex", True)
    monkeypatch.setattr(ai, "ai_run_one", lambda pv, p, timeout=600: (_ for _ in ()).throw(RuntimeError("401 unauthorized")))
    with pytest.raises(RuntimeError) as e:
        ai.ai_run("claude", "hi")
    assert "Claude：沒登入或登入過期" in str(e.value) and "ChatGPT：沒登入或登入過期" in str(e.value)


def test_quota_from_codex_events_and_claude_rate_limit():
    ai.note_quota_codex("\n".join([json.dumps({"type": "x", "rate_limits": {"primary": {"used_percent": 85, "resets_in_seconds": 600}}}), "not json"]))
    q = ai.quota_of("codex")
    assert q["left"] == 15 and q["state"] == "warn" and q["resets"] > 0
    ai.note_quota_claude({"status": "rejected", "resetsAt": 4102444800000})
    assert ai.quota_of("claude")["state"] == "out" and ai.quota_of("claude")["resets"] == 4102444800


def test_order_and_current_provider():
    ai.w_set(provider="codex")
    assert ai.ai_order("gemini") == ["gemini", "codex", "claude", "stepfun"]
    assert ai.current_provider() == "codex"


def test_error_summary_and_friendly():
    assert ai.error_summary('{"error": {"message": "Quota exceeded"}}') == "Quota exceeded"
    assert "需要重新登入" in ai.friendly_error("claude", "401 Unauthorized")
    assert "個人的 Gmail" in ai.friendly_error("gemini", "GOOGLE_CLOUD_PROJECT required")


# ---------- StepFun（API，不用裝工具；本人在設定貼 key） ----------
def _key(tmp_path, key="sk-test-123456"):
    (tmp_path / "_me").mkdir(exist_ok=True)
    (tmp_path / "_me" / "secrets.env").write_text(f"S2_API_KEY=\nSTEPFUN_API_KEY={key}\n", encoding="utf-8")


def test_stepfun_needs_key_and_calls_chat_completions(cfg, monkeypatch):
    monkeypatch.undo()  # 用真的 ai_bin：StepFun 有沒有「裝」看 key
    assert ai.stepfun_key() is None and ai.ai_bin("stepfun") is None  # 沒 key＝沒裝
    _key(cfg)
    assert ai.stepfun_key() == "sk-test-123456" and ai.ai_bin("stepfun") and ai.logged_in("stepfun", "api") is True
    sent = {}

    class R:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake(req, timeout=0):
        sent.update(url=req.full_url, auth=req.headers.get("Authorization"), body=json.loads(req.data))
        return R(json.dumps({"choices": [{"message": {"content": " 好的 "}}], "model": "step-5-preview"}).encode())
    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    ai.ai_level("hard")
    assert ai._ai_run_one("stepfun", "hello") == "好的"
    assert sent["url"] == "https://api.stepfun.ai/v1/chat/completions" and sent["auth"] == "Bearer sk-test-123456"
    assert sent["body"]["model"] == "step-5-preview" and sent["body"]["messages"][-1]["content"] == "hello"


def test_stepfun_http_errors_become_switchable_kinds(cfg, monkeypatch):
    monkeypatch.undo()
    _key(cfg)
    import io
    import urllib.error

    def boom(code):
        def f(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b'{"error":{"message":"bad key"}}'))
        return f
    monkeypatch.setattr(ai.urllib.request, "urlopen", boom(401))
    with pytest.raises(RuntimeError) as e:
        ai._ai_run_one("stepfun", "hi")
    assert ai.ai_fail_kind(str(e.value)) == "auth" and "sk-test" not in str(e.value)  # 錯誤訊息不能帶出 key
    monkeypatch.setattr(ai.urllib.request, "urlopen", boom(429))
    with pytest.raises(RuntimeError) as e:
        ai._ai_run_one("stepfun", "hi")
    assert ai.ai_fail_kind(str(e.value)) == "quota"


def test_task_routing_prefers_choice_then_tested_stepfun():
    assert set(ai.TASKS) == {"ask", "translate", "classify"}
    ai.w_set(provider="claude")
    assert ai.task_provider("translate") == "claude"  # StepFun 還沒測過：用預設那位
    ai.set_tested("stepfun", True)
    assert ai.task_provider("translate") == "stepfun"  # 測過了：沒特別選的工作改用 StepFun
    ai.w_set(tasks={"ask": "gemini"})
    assert ai.task_provider("ask") == "gemini" and ai.task_provider("classify") == "stepfun"
    ai.w_set(tasks={"ask": "nonsense"})
    assert ai.task_provider("ask") == "stepfun"


# ---------- 背景工作（流水線，大量派 agent）：每一類工作選引擎，每個引擎選各角色的模型 ----------
def test_job_launch_claude_maps_agent_roles_to_chosen_models(cfg):
    L = ai.job_launch("new")
    assert L["engine"] == "claude" and L["via"] == "claude"
    assert L["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-5-5" and L["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-5-5"
    assert "ANTHROPIC_BASE_URL" not in L["env"]
    ai.w_set(jobs={"tiers": {"claude": {"opus": "claude-sonnet-5-5", "main": "claude-haiku-5-5"}}})
    L = ai.job_launch("library")
    assert L["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-sonnet-5-5" and L["model"] == "claude-haiku-5-5"


def test_job_launch_stepfun_points_claude_code_at_stepfun(cfg, monkeypatch):
    monkeypatch.undo()
    ai.w_set(jobs={"groups": {"library": "stepfun"}})
    with pytest.raises(RuntimeError, match="key"):
        ai.job_launch("library")  # 還沒貼 key
    _key(cfg)
    L = ai.job_launch("library-draft")
    e = L["env"]
    assert L["engine"] == "claude" and L["via"] == "stepfun" and L["model"] == "step-5-preview"
    assert e["ANTHROPIC_BASE_URL"] == "https://api.stepfun.ai" and e["ANTHROPIC_AUTH_TOKEN"] == "sk-test-123456"
    assert {e[f"ANTHROPIC_DEFAULT_{t}_MODEL"] for t in ("OPUS", "SONNET", "HAIKU", "FABLE")} <= {"step-5-preview", "step-3.7-flash"}  # 派 agent 也不會叫到 Claude 的模型
    assert "ANTHROPIC_API_KEY" in L["unset"]
    assert ai.job_launch("new")["via"] == "claude"  # 別類工作照舊
    ai.w_set(jobs={"groups": {"library": "stepfun"}, "stepfunBase": "plan"})
    assert ai.job_launch("library")["env"]["ANTHROPIC_BASE_URL"] == "https://api.stepfun.ai/step_plan"


def test_job_settings_reject_unknown_values(cfg):
    ai.save_job_settings({"groups": {"build": "codex", "library": "nonsense", "bogus": "claude"},
                          "tiers": {"stepfun": {"opus": "step-3.7-flash", "main": "claude-opus-5-5"}}, "stepfunBase": "x"})
    j = ai.w_settings()["jobs"]
    assert j["groups"] == {"build": "codex"} and j["tiers"]["stepfun"] == {"opus": "step-3.7-flash"} and "stepfunBase" not in j
    assert ai.job_launch("deep")["engine"] == "codex"
    assert ai.job_launch("unknown-kind", default_engine="codex")["engine"] == "codex"
