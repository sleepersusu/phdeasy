"""總覽：事實彙整、敘述的出處核對（每句要有出處、出處存在、數字對得上）。"""
from pipeline.profile import build_facts, check_draft, fact_lookup, render_profile_md

NET = {"roles": {"first": 1, "middle": 0, "last": 1, "unknown": 0, "corresponding": 1, "total": 2}, "years": {"2023": 1, "2024": 1},
       "topics": {"field": [["Medicine", 2]], "subfield": [["Health Informatics", 2]], "topic": [["mHealth", 2]], "domain": []},
       "coauthors_total": 3, "coauthors": [{"key": "A1", "name": "Ann Lee", "n": 2, "works": ["W1", "W2"], "years": {"2023": 1, "2024": 1}}]}
WORKS = [{"id": "W1", "title": "HeartBot", "year": 2024, "kind": "full"}, {"id": "W2", "title": "Walk", "year": 2023, "kind": "full"}]
CARDS = {"W1": {"fields": {"design": {"status": "ok", "type": "quasi-experimental"}, "sample": {"status": "ok", "n_enrolled": 92, "country": "United States"},
                           "summary": {"status": "ok", "text": "HeartBot 提升知識"}}},
         "W2": {"fields": {"design": {"status": "ok", "type": "rct"}, "sample": {"status": "ok", "n_enrolled": 210, "country": "United States"},
                           "summary": {"status": "ok", "text": "步數介入"}}}}
GRANTS = [{"key": "NIH:HS027803", "award_id": "R01HS027803", "title": "Diabetes prevention", "status": "confirmed", "target_role": "pi",
           "start": "2021-08-01", "end": "2026-07-31", "works": ["W1"], "funder": "AHRQ"}]


def facts():
    return build_facts({"name": "Y F"}, WORKS, NET, CARDS, GRANTS)


def test_build_facts_aggregates():
    f = facts()
    assert f["design_types"] == {"quasi-experimental": 1, "rct": 1}
    assert f["sample_countries"] == {"United States": 2}
    assert f["grants_pi"][0]["award_id"] == "R01HS027803" and f["grants_pi"][0]["active_2026"] is True
    assert f["top_coauthors"][0]["name"] == "Ann Lee"
    assert f["by_year"]["2024"] == ["W1"]


def test_fact_lookup_paths():
    f = facts()
    assert fact_lookup(f, "top_coauthors[0].n") == 2
    assert fact_lookup(f, "design_types.rct") == 1
    assert fact_lookup(f, "nope") is None


GOOD = {"sections": [
    {"key": "focus", "title": "研究主線", "claims": [
        {"text": "她的研究以行動健康介入為主，常用隨機對照試驗與準實驗設計。", "refs": ["W1", "W2", "fact:design_types"]},
        {"text": "最常合作的是 Ann Lee，共 2 篇。", "refs": ["fact:top_coauthors[0]"]}]},
    {"key": "questions", "title": "可以問教授的問題", "claims": [{"text": "HeartBot 下一步是否會做 RCT？", "refs": ["W1"]}]}]}


def test_good_draft_passes():
    assert check_draft(GOOD, facts(), {"W1", "W2"}) == []


def test_claim_without_refs_fails():
    d = {"sections": [{"key": "focus", "title": "x", "claims": [{"text": "她很有名。", "refs": []}]}]}
    assert check_draft(d, facts(), {"W1"})[0]["why"] == "no_refs"


def test_unknown_work_or_fact_ref_fails():
    d = {"sections": [{"key": "focus", "title": "x", "claims": [{"text": "a", "refs": ["W9", "fact:made_up"]}]}]}
    whys = {f["why"] for f in check_draft(d, facts(), {"W1"})}
    assert whys == {"unknown_ref:W9", "unknown_ref:fact:made_up"}


def test_number_not_backed_by_facts_fails():
    d = {"sections": [{"key": "focus", "title": "x", "claims": [{"text": "最常合作的是 Ann Lee，共 5 篇。", "refs": ["fact:top_coauthors[0]"]}]}]}
    assert check_draft(d, facts(), {"W1"})[0]["why"] == "number_not_in_refs:5"


def test_number_backed_by_card_ref_passes():
    d = {"sections": [{"key": "focus", "title": "x", "claims": [{"text": "HeartBot 研究納入 92 人。", "refs": ["W1"]}]}]}
    assert check_draft(d, facts(), {"W1", "W2"}, cards=CARDS) == []


def test_render_profile_md_lists_refs():
    md = render_profile_md({"name": "Y F"}, facts(), GOOD)
    assert "## 研究主線" in md and "〔W1、W2、fact:design_types〕" in md


def test_facts_distinguish_full_cards_from_fulltext():
    f = build_facts({"name": "Y F"}, WORKS, NET, CARDS, GRANTS, fulltext_ok=1)
    assert f["n_full_cards"] == 2 and f["n_fulltext"] == 1
    assert "n_full" not in f


def test_ref_to_named_item_must_mention_name():
    d = {"sections": [{"key": "c", "title": "x", "claims": [{"text": "Bob Smith 合作 2 篇。", "refs": ["fact:top_coauthors[0]"]}]}]}
    fails = check_draft(d, facts(), {"W1"})
    assert any(f["why"] == "ref_name_mismatch:Ann Lee" for f in fails)
