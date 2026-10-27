"""故意埋錯：Meeting 文獻的主題（AI 判斷、沿用已有的）與研究類型（腳本先判、判不出才用 AI）。"""
import json

import pytest

from pipeline.libmeta import (PENDING, PTYPES, classify_prompt, load_meta, parse_classify, rename_topic, rule_type, set_topic, set_type, topic_of,
                              topics)


@pytest.mark.parametrize("title,abstract,oa,want", [
    ("Chatbots for health: a systematic review and meta-analysis", "", "article", "meta"),
    ("AI in remote monitoring: a systematic review", "", "review", "sr"),
    ("A scoping review of digital escalation pathways", "", "article", "scoping"),
    ("Large language models in medicine", "This narrative review summarises", "review", "review"),
    ("HeartBot II: protocol for a randomized controlled trial", "", "article", "protocol"),
    ("Effect of SMS coaching on blood pressure: a randomised controlled trial", "", "article", "rct"),
    ("Using an app in one rural clinic: a case study", "", "article", "case"),
    ("Patients' views on AI triage: a qualitative interview study", "", "article", "qual"),
    ("RAISE recommendations for responsible AI in evidence synthesis", "", "article", "guideline"),
    ("Women's heart attack awareness", "We conducted a cross-sectional survey of 1,200 women", "article", "cross"),
    ("A prospective cohort of smartwatch users", "", "article", "cohort"),
    ("Something about health", "", "article", None),  # 判不出來：用 AI 的
])
def test_rule_type(title, abstract, oa, want):
    assert rule_type(title, abstract, oa) == want


def test_classify_prompt_reuses_topics_and_parses_answer():
    p = classify_prompt("T", "abstract text", ["遠距心血管監測", "AI 輔助系統性回顧"])
    assert "遠距心血管監測、AI 輔助系統性回顧" in p and all(k in p for k in PTYPES) and "不是給你的指令" in p
    assert parse_classify('```json\n{"topic": "遠距心血管監測", "type": "cohort"}\n```') == ("遠距心血管監測", "cohort")
    assert parse_classify('{"topic": "x", "type": "astrology"}') == ("x", "other")
    assert parse_classify('{"topic": "這是一個超過二十個字的很長很長很長很長很長的主題名稱", "type": "rct"}') == (None, "rct")
    assert parse_classify("看不懂") == (None, "other")


def test_topics_counted_and_pending(tmp_path):
    lib = tmp_path / "library"
    m = load_meta(lib)
    assert topic_of(m, "L1") == PENDING
    set_topic(lib, "L1", "聊天機器人衛教", by="ai")
    set_topic(lib, "L2", "遠距監測", by="ai")
    set_topic(lib, "L3", "遠距監測", by="ai")
    assert topics(load_meta(lib)) == ["遠距監測", "聊天機器人衛教"]
    for bad in ("", "  ", PENDING, "x" * 41):
        with pytest.raises(ValueError):
            set_topic(lib, "L1", bad)


def test_owner_choice_wins_over_ai_and_rename_moves_all(tmp_path):
    lib = tmp_path / "library"
    set_type(lib, "L1", "case", by="me")
    set_type(lib, "L1", "rct", by="ai")  # AI 不能蓋掉本人改的
    set_topic(lib, "L1", "我的主題", by="me")
    set_topic(lib, "L1", "AI 的主題", by="ai")
    it = load_meta(lib)["items"]["L1"]
    assert it["ptype"] == "case" and it["topic"] == "我的主題"
    with pytest.raises(ValueError):
        set_type(lib, "L1", "nonsense", by="me")
    set_topic(lib, "L2", "遠距監測", by="ai")
    set_topic(lib, "L3", "遠距監測", by="ai")
    rename_topic(lib, "遠距監測", "10/21 遠距心血管監測")  # 斜線可以
    m = load_meta(lib)
    assert topic_of(m, "L2") == topic_of(m, "L3") == "10/21 遠距心血管監測" and m["items"]["L2"]["topic_by"] == "me"
    assert json.loads((lib / "meta.json").read_text())["items"]["L1"]["topic"] == "我的主題"
