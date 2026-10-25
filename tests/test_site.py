"""前端：所有需求欄位都要出現在資料與頁面上；缺資料時顯示「尚未產生」而不是空白。"""
import json

from pipeline.site import CARD_FIELDS, SECTIONS, build_site_data, render_html
from pipeline.state import init_run, set_stage


def make_run(tmp_path, with_card=False):
    run = init_run(tmp_path / "runs" / "demo", professor={"name": "Yoshimi Fukuoka", "institution": "UCSF"})
    set_stage(run, "grants", author_id="A0")
    wd = run / "work"
    works = [
        {"id": "W1", "title": "Study </script> One", "year": 2024, "type": "article", "kind": "full", "venue": "J A", "doi": "10.1/a",
         "authors": [{"id": "A0", "name": "Yoshimi Fukuoka", "position": "last", "is_corresponding": True, "institutions": []},
                     {"id": "A1", "name": "Ann Lee", "position": "first", "is_corresponding": False, "institutions": ["UCSF"]}],
         "target_position": "last", "target_corresponding": True, "abstract": "Abs.", "topic": {"name": "mHealth", "field": "Medicine"}},
        {"id": "W2", "title": "Poster", "year": 2023, "type": "conference-abstract", "kind": "short", "venue": None, "doi": None,
         "authors": [], "target_position": "middle", "target_corresponding": False, "abstract": "Short.", "topic": {}},
    ]
    (wd / "works.json").write_text(json.dumps(works))
    (wd / "author_candidates.json").write_text(json.dumps([{"id": "A0", "name": "Yoshimi Fukuoka", "orcid": "https://orcid.org/0000", "institutions": ["UCSF"]}]))
    (run / "pdfs" / "index.csv").write_text("id,year,kind,status,source,ext,path,sha256,url,tried,title\nW1,2024,full,ok,openalex,pdf,pdfs/2024/W1_Lee_Study.pdf,h,u,,Study\nW2,2023,short,not_needed,,,,,,,Poster\n")
    (wd / "ingest.json").write_text(json.dumps({"W1": {"source_type": "pdf"}, "W2": {"source_type": "abstract"}}))
    (wd / "network.json").write_text(json.dumps({
        "roles": {"first": 0, "middle": 1, "last": 1, "unknown": 0, "corresponding": 1, "total": 2},
        "years": {"2023": 1, "2024": 1}, "topics": {"field": [["Medicine", 1]], "subfield": [], "topic": [["mHealth", 1]], "domain": []},
        "coauthors_total": 1, "coauthors_linked": 1,
        "coauthors": [{"key": "A1", "name": "Ann Lee", "linked": True, "merged_names": [], "n": 1, "works": ["W1"], "years": {"2024": 1},
                       "institutions": [["UCSF", 1]], "as_first": 1, "as_last": 0, "as_corresponding": 0}],
        "possible_splits": [{"keys": ["A1", "A9"], "names": ["Ann Lee", "Ann Lee"], "counts": [1, 1], "combined_n_max": 2}]}))
    (wd / "grants").mkdir()
    (wd / "grants" / "grants_final.json").write_text(json.dumps([
        {"key": "NIH:HS027803", "award_id": "R01HS027803", "funder": "AHRQ", "title": "Diabetes prevention", "target_role": "pi", "status": "confirmed",
         "pi_names": ["YOSHIMI FUKUOKA"], "start": "2021-08-01", "end": "2026-07-31", "total_award": 1, "works": ["W1"],
         "evidence": [{"type": "nih_pi"}], "refute": {"verdict": "keep", "reason": "ok"}}]))
    if with_card:
        c = run / "work" / "cards" / "W1"
        c.mkdir(parents=True)
        (c / "card.json").write_text(json.dumps({"id": "W1", "fields": {
            "summary": {"text": "大意文字", "citations": [{"quote": "We enrolled 92 women", "loc": "p.2"}], "status": "ok"},
            "limitations": {"author_stated": [{"text": "便利樣本", "citations": [{"quote": "convenience sample", "loc": "p.9"}]}], "inferred": []}}}))
    return run


def test_card_fields_are_the_seven_required():
    assert [label for _, label in CARD_FIELDS] == ["大意", "研究設計", "研究樣本", "研究缺口", "解決什麼", "發現", "研究限制"]


def test_site_data_has_every_requirement(tmp_path):
    d = build_site_data(make_run(tmp_path))
    for key in ("professor", "pipeline", "counts", "roles", "years", "topics", "coauthors", "possible_splits", "grants", "works", "exceptions", "decisions", "files"):
        assert key in d, key
    assert d["professor"]["orcid"] == "https://orcid.org/0000"
    assert len(d["works"]) == 2
    assert d["coauthors"][0]["name"] == "Ann Lee"
    assert d["grants"][0]["status"] == "confirmed"


def test_every_work_has_all_card_fields_even_without_card(tmp_path):
    d = build_site_data(make_run(tmp_path))
    for w in d["works"]:
        assert [f["key"] for f in w["card"]["fields"]] == [k for k, _ in CARD_FIELDS]
        assert all(f["state"] == "pending" for f in w["card"]["fields"])
        assert "cards" in w["card"]["pending_note"]


def test_card_values_used_when_present(tmp_path):
    d = build_site_data(make_run(tmp_path, with_card=True))
    w1 = next(w for w in d["works"] if w["id"] == "W1")
    f = {x["key"]: x for x in w1["card"]["fields"]}
    assert f["summary"]["state"] == "ok" and f["summary"]["text"] == "大意文字"
    assert f["summary"]["citations"][0]["loc"] == "p.2"
    assert f["limitations"]["author_stated"][0]["text"] == "便利樣本"
    assert f["design"]["state"] == "pending"  # 卡片缺的欄位仍顯示待補


def test_work_links_pdf_relative_to_site_and_fulltext_state(tmp_path):
    d = build_site_data(make_run(tmp_path))
    w1 = next(w for w in d["works"] if w["id"] == "W1")
    assert w1["pdf_href"] == "../../pdfs/2024/W1_Lee_Study.pdf"
    assert w1["fulltext"] == "ok" and w1["grants"] == ["NIH:HS027803"]
    w2 = next(w for w in d["works"] if w["id"] == "W2")
    assert w2["pdf_href"] is None and w2["fulltext"] == "not_needed"


def test_decisions_include_possible_splits(tmp_path):
    d = build_site_data(make_run(tmp_path))
    assert any("Ann Lee" in x["text"] for x in d["decisions"])


def test_html_has_all_sections_and_escapes_script(tmp_path):
    html = render_html(build_site_data(make_run(tmp_path)))
    for sid, _ in SECTIONS:
        assert f'id="{sid}"' in html
    for _, label in CARD_FIELDS:
        assert label in html
    assert "Study </script> One" not in html  # 標題裡的 </script> 不能破壞頁面
    assert html.count("<script>") == 2  # 比對程式＋主程式（資料在 <script id="inline-data" type="application/json">）


def test_work_exception_states(tmp_path):
    from pipeline.exceptions import add_exception, resolve_exception
    run = make_run(tmp_path)
    add_exception(run, "W1", "ingest", "abstract_only", "x")
    add_exception(run, "W1", "setup", "year_mismatch", "y")
    add_exception(run, "W2", "ingest", "no_text", "z")
    resolve_exception(run, "W2", "ingest", "no_text", "ok")
    d = build_site_data(run)
    w1 = next(w for w in d["works"] if w["id"] == "W1")
    assert sorted(e["state"] for e in w1["exceptions"]) == ["info", "open"]
    w2 = next(w for w in d["works"] if w["id"] == "W2")
    assert [e["state"] for e in w2["exceptions"]] == ["resolved"]


def test_claim_fields_and_fixed_facts_shown(tmp_path):
    run = make_run(tmp_path)
    c = run / "work" / "cards" / "W1"
    c.mkdir(parents=True)
    (c / "card.json").write_text(json.dumps({"id": "W1", "basis": "fulltext", "fields": {
        "design": {"status": "ok", "type": "quasi-experimental", "text": "準實驗", "citations": []},
        "sample": {"status": "ok", "text": "92 位", "n_enrolled": 92, "n_analyzed": 85, "country": "United States", "citations": []},
        "findings": {"status": "ok", "claims": [{"text": "知識提升", "citations": [{"quote": "Knowledge scores increased", "loc": "p.3"}]}]},
        "gap": {"status": "not_in_source", "claims": []}}}))
    d = build_site_data(run)
    f = {x["key"]: x for x in next(w for w in d["works"] if w["id"] == "W1")["card"]["fields"]}
    assert f["findings"]["claims"][0]["text"] == "知識提升"
    assert f["design"]["facts"]["設計類型"] == "準實驗（quasi-experimental）"
    assert f["sample"]["facts"]["納入人數"] == 92 and f["sample"]["facts"]["分析人數"] == 85
    assert f["gap"]["state"] == "not_in_source"


def test_profile_narrative_included_when_present(tmp_path):
    run = make_run(tmp_path)
    (run / "work" / "profile").mkdir()
    (run / "work" / "profile" / "final.json").write_text(json.dumps({"sections": [
        {"key": "focus", "title": "研究主線", "claims": [{"text": "以行動健康介入為主", "refs": ["W1", "fact:design_types"]}]}]}))
    d = build_site_data(run)
    assert d["profile"][0]["title"] == "研究主線"
    assert d["profile"][0]["claims"][0]["refs"] == ["W1", "fact:design_types"]
    html = render_html(d)
    assert 'id="profile"' in html


def test_profile_missing_is_empty_list(tmp_path):
    assert build_site_data(make_run(tmp_path))["profile"] == []


def test_bilingual_fields_and_grants(tmp_path):
    run = make_run(tmp_path, with_card=True)
    (run / "work" / "cards" / "W1" / "i18n.json").write_text(json.dumps({
        "id": "W1", "title_zh": "研究一", "en": {"summary": "Summary in English", "limitations": {"author_stated": ["Convenience sample"], "inferred": []}},
        "keywords_zh": ["女性"], "keywords_en": ["women"]}))
    (run / "work" / "grants" / "i18n.json").write_text(json.dumps({"NIH:HS027803": {"title_zh": "糖尿病預防", "summary_en": "S en", "summary_zh": "S zh"}}))
    d = build_site_data(run)
    w1 = next(w for w in d["works"] if w["id"] == "W1")
    assert w1["title_zh"] == "研究一" and w1["keywords_en"] == ["women"]
    f = {x["key"]: x for x in w1["card"]["fields"]}
    assert f["summary"]["text_en"] == "Summary in English"
    assert f["limitations"]["author_stated"][0]["text_en"] == "Convenience sample"
    g = d["grants"][0]
    assert g["title_zh"] == "糖尿病預防" and g["summary_zh"] == "S zh"
    w2 = next(w for w in d["works"] if w["id"] == "W2")
    assert w2["title_zh"] is None  # 沒翻譯時明確為 None，頁面顯示「尚未翻譯」


def test_html_has_match_section_and_language_switch(tmp_path):
    html = render_html(build_site_data(make_run(tmp_path)))
    assert 'id="match"' in html
    assert "function rankDocs" in html  # 比對邏輯內嵌
    assert 'data-lang="zh"' in html and 'data-lang="en"' in html and 'data-lang="both"' in html


def test_build_site_writes_data_json(tmp_path):
    import json, sys
    sys.path.insert(0, "scripts")
    import build_site
    run = make_run(tmp_path)
    sys.argv = ["build_site.py", str(run)]
    build_site.main()
    d = json.loads((run / "out" / "site" / "data.json").read_text())
    assert d["professor"] and d["works"]


def test_site_data_carries_recommendations_and_staleness(tmp_path):
    import json
    from pipeline.match import me_fingerprint
    run = make_run(tmp_path)
    (run / "out").mkdir(exist_ok=True)
    (run / "out" / "match.json").write_text(json.dumps({"fingerprint": "old", "targets": [], "read_first": []}))
    d = build_site_data(run)
    assert d["recommend"]["targets"] == [] and d["recommend"]["stale"] in (True, False)


def test_header_uses_institution_confirmed_at_stop1(tmp_path):
    # OpenAlex／計畫查詢記到的機構可能是兼任單位（例：UTS），頁首用本人在停 1 確認的機構
    run = make_run(tmp_path)
    (run / "work" / "grants").mkdir(parents=True, exist_ok=True)
    (run / "work" / "grants" / "fetch_log.json").write_text(json.dumps({"institution": "Other University", "country": "US"}))
    d = build_site_data(run)
    assert d["professor"]["institution"] == "UCSF" and d["professor"]["country"] == "US"


def test_site_data_has_basic_info_and_current_grants(tmp_path):
    run = make_run(tmp_path)
    (run / "work" / "basic.json").write_text(json.dumps({"position": {"title": "Professor", "institution": "UCSF"}, "metrics": {"h_index": 3}}))
    d = build_site_data(run)
    assert d["basic"]["position"]["title"] == "Professor" and d["basic"]["metrics"]["h_index"] == 3
    assert isinstance(d["basic"]["active_grants"], list)
    (run / "work" / "basic.json").unlink()
    assert build_site_data(run)["basic"] == {"active_grants": build_site_data(run)["basic"]["active_grants"]}
