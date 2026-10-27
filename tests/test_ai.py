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
    assert ai.ai_order("gemini") == ["gemini", "codex", "claude"]
    assert ai.current_provider() == "codex"


def test_error_summary_and_friendly():
    assert ai.error_summary('{"error": {"message": "Quota exceeded"}}') == "Quota exceeded"
    assert "需要重新登入" in ai.friendly_error("claude", "401 Unauthorized")
    assert "個人的 Gmail" in ai.friendly_error("gemini", "GOOGLE_CLOUD_PROJECT required")
