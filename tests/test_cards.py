"""解析卡：格式、引句、數字、雙軌比對、裁決、推翻、組裝。每種錯都要被抓到。"""
import copy

from pipeline.cards import (
    validate_card,
    check_card,
    numbers_in,
    diff_fixed,
    apply_judge,
    apply_refute,
    assemble,
)

TEXT = """# W1 | pdf | HeartBot

[p.1]
Background: Few chatbot studies have targeted women's heart attack knowledge.
[p.2]
We enrolled 92 women aged 26-70 years in the United States; 85 completed the posttest.
This was a nonrandomized, quasi-experimental pre-post design.
[p.3]
Knowledge scores increased from 2.4 to 3.1 (P<.001).
[p.4]
Several limitations must be acknowledged. First, this study was not a randomized controlled trial.
"""


def C(quote, loc):
    return {"quote": quote, "loc": loc}


def good_card():
    return {
        "id": "W1", "basis": "fulltext",
        "fields": {
            "summary": {"status": "ok", "text": "以準實驗設計評估 HeartBot 對女性心臟病知識的效果。", "citations": [C("nonrandomized, quasi-experimental pre-post design", "p.2")]},
            "design": {"status": "ok", "type": "quasi-experimental", "text": "非隨機前後測準實驗設計", "citations": [C("This was a nonrandomized, quasi-experimental pre-post design", "p.2")]},
            "sample": {"status": "ok", "text": "美國 92 位 26–70 歲女性，85 位完成後測", "population": "26–70 歲女性", "n_enrolled": 92, "n_analyzed": 85,
                       "country": "United States", "setting": "線上", "period": "來源未提及",
                       "citations": [C("We enrolled 92 women aged 26-70 years in the United States; 85 completed the posttest", "p.2")]},
            "gap": {"status": "ok", "claims": [{"text": "很少聊天機器人研究針對女性的心臟病知識", "citations": [C("Few chatbot studies have targeted women's heart attack knowledge", "p.1")]}]},
            "solves": {"status": "ok", "claims": [{"text": "評估 HeartBot 能否提升知識", "citations": [C("nonrandomized, quasi-experimental pre-post design", "p.2")]}]},
            "findings": {"status": "ok", "claims": [{"text": "知識分數由 2.4 升到 3.1", "citations": [C("Knowledge scores increased from 2.4 to 3.1", "p.3")]}]},
            "limitations": {"status": "ok",
                            "author_stated": [{"text": "不是隨機對照試驗", "citations": [C("this study was not a randomized controlled trial", "p.4")]}],
                            "inferred": [{"text": "前後測沒有對照組，無法排除練習效果", "basis": "設計為單組前後測", "citations": [C("quasi-experimental pre-post design", "p.2")]}]},
        },
    }


def test_valid_card_passes_schema():
    assert validate_card(good_card(), kind="full") == []


def test_missing_field_is_caught():
    c = good_card()
    del c["fields"]["gap"]
    assert any("gap" in e for e in validate_card(c, kind="full"))


def test_empty_text_without_not_in_source_is_caught():
    c = good_card()
    c["fields"]["summary"]["text"] = ""
    assert any("summary" in e for e in validate_card(c, kind="full"))


def test_not_in_source_is_allowed_without_citations():
    c = good_card()
    c["fields"]["gap"] = {"status": "not_in_source", "claims": []}
    assert validate_card(c, kind="full") == []


def test_bad_design_type_is_caught():
    c = good_card()
    c["fields"]["design"]["type"] = "a kind of study"
    assert any("design.type" in e for e in validate_card(c, kind="full"))


def test_short_card_only_needs_summary():
    c = {"id": "W2", "basis": "abstract", "fields": {"summary": {"status": "ok", "text": "會議摘要", "citations": [C("Few chatbot studies have targeted", "p.1")]}}}
    assert validate_card(c, kind="short") == []


def test_check_card_passes_good_card():
    assert check_card(good_card(), TEXT) == []


def test_fabricated_quote_is_caught():
    c = good_card()
    c["fields"]["findings"]["claims"][0]["citations"][0]["quote"] = "Knowledge scores increased from 2.4 to 3.9"
    fails = check_card(c, TEXT)
    assert any(f["path"].startswith("findings") and f["why"] == "not_found" for f in fails)


def test_wrong_page_is_caught():
    c = good_card()
    c["fields"]["gap"]["claims"][0]["citations"][0]["loc"] = "p.3"
    assert any(f["why"] == "wrong_loc:p.1" for f in check_card(c, TEXT))


def test_sample_number_not_in_quotes_is_caught():
    c = good_card()
    c["fields"]["sample"]["n_enrolled"] = 120
    assert any(f["why"] == "number_not_in_quotes:120" for f in check_card(c, TEXT))


def test_finding_number_not_in_quotes_is_caught():
    c = good_card()
    c["fields"]["findings"]["claims"][0]["text"] = "知識分數由 2.4 升到 3.5"
    assert any(f["why"] == "number_not_in_quotes:3.5" for f in check_card(c, TEXT))


def test_claim_without_citation_is_caught():
    c = good_card()
    c["fields"]["solves"]["claims"][0]["citations"] = []
    assert any(f["why"] == "no_citation" for f in check_card(c, TEXT))


def test_numbers_in_handles_ranges_decimals_and_chinese():
    assert numbers_in("美國 92 位 26–70 歲女性，P<.001，2.4 升到 3.1") == ["92", "26", "70", ".001", "2.4", "3.1"]


def test_diff_fixed_equal():
    a = good_card()
    b = {"id": "W1", "design": {"type": "quasi-experimental"}, "sample": {"n_enrolled": 92, "n_analyzed": 85, "country": "united states"}}
    assert diff_fixed(a, b) == []


def test_diff_fixed_detects_differences():
    a = good_card()
    b = {"id": "W1", "design": {"type": "rct"}, "sample": {"n_enrolled": 92, "n_analyzed": 92, "country": "USA"}}
    d = {x["field"]: x for x in diff_fixed(a, b)}
    assert set(d) == {"design.type", "sample.n_analyzed"}  # USA 與 United States 視為相同
    assert d["sample.n_analyzed"]["a"] == 85 and d["sample.n_analyzed"]["b"] == 92


def test_apply_judge_sets_value_or_unresolved():
    c = good_card()
    out, unresolved = apply_judge(c, [{"field": "sample.n_analyzed", "verdict": "b", "value": 92, "reason": "x"},
                                      {"field": "design.type", "verdict": "unresolved", "reason": "原文兩種說法"}])
    assert out["fields"]["sample"]["n_analyzed"] == 92
    assert out["fields"]["design"]["status"] == "unresolved" and unresolved == ["design.type"]
    assert c["fields"]["sample"]["n_analyzed"] == 85  # 不改原物件


def test_apply_refute_rejects_claim_and_partial_citation():
    c = good_card()
    c["fields"]["findings"]["claims"].append({"text": "參與者滿意度高", "citations": [C("Knowledge scores increased", "p.3"), C("Several limitations must be acknowledged", "p.4")]})
    verdicts = [
        {"path": "findings[0]", "verdict": "keep"},
        {"path": "findings[1]", "verdict": "partial", "drop_citations": [1], "reason": "第二個出處講的是限制"},
        {"path": "gap[0]", "verdict": "reject", "reason": "背景文獻的說法不是本文缺口"},
    ]
    out, rejected = apply_refute(c, verdicts)
    assert len(out["fields"]["findings"]["claims"][1]["citations"]) == 1
    assert out["fields"]["gap"]["claims"] == [] and out["fields"]["gap"]["status"] == "not_in_source"
    assert [r["path"] for r in rejected] == ["gap[0]", "findings[1].citations[1]"]


def test_apply_refute_partial_that_drops_all_citations_rejects_claim():
    c = good_card()
    out, rejected = apply_refute(c, [{"path": "solves[0]", "verdict": "partial", "drop_citations": [0], "reason": "x"}])
    assert out["fields"]["solves"]["claims"] == []
    assert any(r["path"] == "solves[0]" for r in rejected)


def test_assemble_drops_failed_citations_and_reports():
    c = good_card()
    c["fields"]["findings"]["claims"].append({"text": "捏造的發現", "citations": [C("this sentence does not exist anywhere", "p.3")]})
    card, rejected = assemble(c, TEXT)
    assert len(card["fields"]["findings"]["claims"]) == 1
    assert rejected and rejected[0]["why"] == "not_found"
    assert check_card(card, TEXT) == []  # 組裝後必定全部通過


def test_assemble_never_mutates_input():
    c = good_card()
    before = copy.deepcopy(c)
    assemble(c, TEXT)
    assert c == before


def test_assemble_sample_with_wrong_count_clears_count_and_reports():
    c = good_card()
    c["fields"]["sample"]["n_enrolled"] = 120
    card, rejected = assemble(c, TEXT)
    assert card["fields"]["sample"]["n_enrolled"] is None  # 錯的人數被清掉，不會留在卡上
    assert any(r["why"] == "number_not_in_quotes:120" for r in rejected)
    assert check_card(card, TEXT) == []


def test_missing_refute_paths():
    from pipeline.cards import missing_refute_paths
    c = good_card()
    verdicts = [{"path": "gap[0]", "verdict": "keep"}, {"path": "findings[0]", "verdict": "maybe"}]
    assert missing_refute_paths(c, verdicts) == ["solves[0]", "findings[0]", "limitations.author_stated[0]", "limitations.inferred[0]"]


def test_country_list_equals_multiple():
    a = good_card()
    a["fields"]["sample"]["country"] = "Canada, Brazil, Italy, United States"
    b = {"design": {"type": "quasi-experimental"}, "sample": {"n_enrolled": 92, "n_analyzed": 85, "country": "multiple"}}
    assert diff_fixed(a, b) == []


def test_apply_judge_adds_evidence_citation():
    c = good_card()
    out, _ = apply_judge(c, [{"field": "design.type", "verdict": "b", "value": "single-arm", "reason": "x",
                              "evidence": {"quote": "This was a nonrandomized, quasi-experimental", "loc": "p.2"}}])
    assert out["fields"]["design"]["type"] == "single-arm"
    assert {"quote": "This was a nonrandomized, quasi-experimental", "loc": "p.2"} in out["fields"]["design"]["citations"]


def test_assemble_unbacked_sample_count_only_clears_that_count():
    c = good_card()
    c["fields"]["sample"]["n_analyzed"] = 263
    card, rejected = assemble(c, TEXT)
    s = card["fields"]["sample"]
    assert s["status"] == "ok" and s["n_analyzed"] is None and s["n_enrolled"] == 92
    assert any(r["why"] == "number_not_in_quotes:263" for r in rejected)
    assert check_card(card, TEXT) == []


def test_assemble_wrong_number_in_sample_text_makes_field_unresolved():
    c = good_card()
    c["fields"]["sample"]["text"] = "美國 120 位女性"
    card, _ = assemble(c, TEXT)
    assert card["fields"]["sample"]["status"] == "unresolved"
    assert check_card(card, TEXT) == []
