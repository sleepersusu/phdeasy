"""E2E 總檢查：乾淨的批次全部通過；每一種埋進去的錯都要被對應的檢查抓到。"""
import json

from pipeline.e2e import run_all
from pipeline.fetch import sha256_file
from pipeline.state import init_run, set_stage

TEXT = "# W1 | pdf | Study\n\n[p.1]\nStudy Title. We enrolled 92 women in the United States.\n[p.2]\nKnowledge scores increased from 2.4 to 3.1.\n"


def card():
    C = lambda q, l: {"quote": q, "loc": l}
    return {"id": "W1", "basis": "fulltext", "kind": "full", "fields": {
        "summary": {"status": "ok", "text": "研究", "citations": [C("We enrolled 92 women in the United States", "p.1")]},
        "design": {"status": "ok", "type": "cross-sectional", "text": "橫斷", "citations": [C("We enrolled 92 women in the United States", "p.1")]},
        "sample": {"status": "ok", "text": "92 位", "n_enrolled": 92, "n_analyzed": 92, "country": "United States", "citations": [C("We enrolled 92 women", "p.1")]},
        "gap": {"status": "not_in_source", "claims": []},
        "solves": {"status": "ok", "claims": [{"text": "x", "citations": [C("We enrolled 92 women", "p.1")]}]},
        "findings": {"status": "ok", "claims": [{"text": "由 2.4 到 3.1", "citations": [C("Knowledge scores increased from 2.4 to 3.1", "p.2")]}]},
        "limitations": {"status": "not_in_source", "author_stated": [], "inferred": []}}}


def make(tmp_path):
    run = init_run(tmp_path / "runs" / "demo", professor={"name": "Y F"})
    set_stage(run, "verify", author_id="A0", works_total=1)
    wd = run / "work"
    (wd / "works.json").write_text(json.dumps([{"id": "W1", "title": "Study", "year": 2024, "type": "article", "kind": "full", "doi": "10.1/a",
                                                "authors": [{"id": "A0", "name": "Y F", "position": "last"}, {"id": "A1", "name": "Ann Lee", "position": "first"}]}]))
    (wd / "text").mkdir()
    (wd / "text" / "W1.txt").write_text(TEXT)
    (run / "pdfs" / "2024").mkdir(parents=True)
    pdf = run / "pdfs" / "2024" / "W1_Lee_Study.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    (wd / "hashes.json").write_text(json.dumps({"pdfs/2024/W1_Lee_Study.pdf": sha256_file(pdf)}))
    (run / "pdfs" / "index.csv").write_text("id,year,kind,status,source,ext,path,sha256,url,tried,title\nW1,2024,full,ok,openalex,pdf,pdfs/2024/W1_Lee_Study.pdf,h,u,,Study\n")
    (wd / "cards" / "W1").mkdir(parents=True)
    (wd / "cards" / "W1" / "card.json").write_text(json.dumps(card()))
    (wd / "network.json").write_text(json.dumps({"coauthors": [{"key": "A1", "n": 1}]}))
    (wd / "count-diff.json").write_text("[]")
    (wd / "grants").mkdir()
    (wd / "grants" / "grants_final.json").write_text(json.dumps([{"key": "NIH:X", "status": "confirmed", "works": ["W1"], "evidence": [{"type": "nih_pi"}]}]))
    (wd / "profile").mkdir()
    (wd / "profile" / "facts.json").write_text(json.dumps({"n_works": 1}))
    (wd / "profile" / "final.json").write_text(json.dumps({"sections": [{"key": "f", "title": "t", "claims": [{"text": "共 1 篇", "refs": ["fact:n_works", "W1"]}]}]}))
    (run / "out" / "zotero").mkdir(parents=True)
    (run / "out" / "zotero" / "demo.ris").write_text(f"TY  - JOUR\nN1  - OpenAlex W1\nL1  - file://{pdf.resolve()}\nER  - \n")
    (run / "out" / "site").mkdir(parents=True)
    (run / "out" / "site" / "index.html").write_text('<html>"id": "W1"</html>')
    (run / "out" / "profile.md").write_text("# x")
    (wd / "cards" / "W1" / "i18n.json").write_text(json.dumps({
        "id": "W1", "title_zh": "研究", "keywords_zh": list("abcde"), "keywords_en": list("abcde"),
        "en": {"summary": "Study", "design": "Cross-sectional", "sample": "92 women",
               "solves": ["x"], "findings": ["from 2.4 to 3.1"]}}))
    (wd / "grants" / "i18n.json").write_text(json.dumps({"NIH:X": {"funder_zh": "x"}}))
    return run


def results(run):
    return {r["name"]: r for r in run_all(run)}


def test_clean_run_passes_everything(tmp_path):
    r = results(make(tmp_path))
    bad = {k: v["detail"] for k, v in r.items() if not v["pass"]}
    assert bad == {}


def test_tampered_original_caught(tmp_path):
    run = make(tmp_path)
    (run / "pdfs" / "2024" / "W1_Lee_Study.pdf").write_bytes(b"%PDF-1.4 changed")
    assert not results(run)["hashes_unchanged"]["pass"]


def test_fabricated_quote_in_final_card_caught(tmp_path):
    run = make(tmp_path)
    c = card()
    c["fields"]["findings"]["claims"][0]["citations"][0]["quote"] = "Knowledge scores increased from 2.4 to 3.9"
    (run / "work" / "cards" / "W1" / "card.json").write_text(json.dumps(c))
    assert not results(run)["cards_quotes"]["pass"]


def test_missing_card_caught(tmp_path):
    run = make(tmp_path)
    (run / "work" / "cards" / "W1" / "card.json").unlink()
    r = results(run)
    assert not r["cards_coverage"]["pass"]


def test_ris_pointing_to_missing_file_caught(tmp_path):
    run = make(tmp_path)
    (run / "out" / "zotero" / "demo.ris").write_text("TY  - JOUR\nN1  - OpenAlex W1\nL1  - file:///nope/x.pdf\nER  - \n")
    assert not results(run)["ris"]["pass"]


def test_state_mismatch_caught(tmp_path):
    run = make(tmp_path)
    set_stage(run, "verify", works_total=5)
    assert not results(run)["state_consistent"]["pass"]


def test_profile_unknown_ref_caught(tmp_path):
    run = make(tmp_path)
    (run / "work" / "profile" / "final.json").write_text(json.dumps({"sections": [{"key": "f", "title": "t", "claims": [{"text": "x", "refs": ["W9"]}]}]}))
    assert not results(run)["profile_traceable"]["pass"]


def test_grant_without_evidence_caught(tmp_path):
    run = make(tmp_path)
    (run / "work" / "grants" / "grants_final.json").write_text(json.dumps([{"key": "NIH:X", "status": "confirmed", "works": [], "evidence": []}]))
    assert not results(run)["grants_evidence"]["pass"]


def test_no_free_fulltext_without_trying_all_sources_caught(tmp_path):
    run = make(tmp_path)
    (run / "pdfs" / "index.csv").write_text("id,year,kind,status,source,ext,path,sha256,url,tried,title\nW1,2024,full,no_free_fulltext,,,,,,openalex:none,Study\n")
    assert not results(run)["fulltext_tried_all"]["pass"]


def test_no_free_fulltext_with_server_errors_is_inconclusive(tmp_path):
    run = make(tmp_path)
    chain = "zotero:none; openalex:none; landing:none; unpaywall:skipped(x); europepmc:http_500,http_403; pmc_oa:none; ncbi_efetch:none; semantic_scholar:none; preprints:none; core:skipped(x); inbox:none"
    (run / "pdfs" / "index.csv").write_text(f'id,year,kind,status,source,ext,path,sha256,url,tried,title\nW1,2024,full,no_free_fulltext,,,,,,"{chain}",Study\n')
    r = results(run)
    assert r["fulltext_tried_all"]["pass"]
    assert not r["fulltext_conclusive"]["pass"]


def test_stale_fulltext_count_in_state_caught(tmp_path):
    run = make(tmp_path)
    set_stage(run, "verify", fulltext_ok=0)
    assert not results(run)["state_consistent"]["pass"]


def test_missing_translation_caught(tmp_path):
    run = make(tmp_path)
    assert results(run)["i18n"]["pass"]
    (run / "work" / "cards" / "W1" / "i18n.json").unlink()
    assert not results(run)["i18n"]["pass"]


def test_wrong_number_in_translation_caught(tmp_path):
    run = make(tmp_path)
    p = run / "work" / "cards" / "W1" / "i18n.json"
    t = json.loads(p.read_text())
    t["en"]["findings"] = ["from 2.4 to 3.9"]
    p.write_text(json.dumps(t))
    assert not results(run)["i18n"]["pass"]
