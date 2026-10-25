"""故意埋錯：討論文獻的 DOI 抽取、Zotero 唯讀清單、RIS 匯出、勾選擬初稿只能引勾選的文獻與她的文章。"""
from pipeline.library import (check_lib_draft, doi_from_text, lib_entry_paths, parse_zotero_items, ris_export, tag_item)
from pipeline.propose import active_grants
from test_propose import version


def test_doi_from_first_page_text():
    assert doi_from_text("J Med Internet Res 2024;26:e5\nhttps://doi.org/10.2196/51234.\nAbstract") == "10.2196/51234"
    assert doi_from_text("DOI: 10.1016/S0140-6736(24)01234-5 Received") == "10.1016/s0140-6736(24)01234-5"
    assert doi_from_text("no identifier here") is None


def test_tag_item_records_who_gave_it_and_when():
    w = tag_item({"id": "W1", "title": "T"}, given_by="Liliana", discussion="2026-11-03", note="看方法", source="doi", today="2026-11-04")
    assert w["library"] == {"given_by": "Liliana", "discussion": "2026-11-03", "note": "看方法", "source": "doi", "added": "2026-11-04"}
    assert w["kind"] == "full"


def test_zotero_items_are_listed_read_only():
    raw = [{"key": "AB12", "data": {"itemType": "journalArticle", "title": "Paper A", "DOI": "10.1/ABC", "date": "2023-05-01",
                                    "creators": [{"lastName": "Lee", "firstName": "Ann"}]}},
           {"key": "NOTE", "data": {"itemType": "note", "note": "x"}},
           {"key": "CD34", "data": {"itemType": "journalArticle", "title": "No DOI", "date": "2021"}}]
    got = parse_zotero_items(raw)
    assert got == [{"key": "AB12", "title": "Paper A", "doi": "10.1/abc", "year": "2023", "authors": "Lee"},
                   {"key": "CD34", "title": "No DOI", "doi": None, "year": "2021", "authors": ""}]


def test_ris_has_chinese_notes_and_pdf_and_who_gave_it():
    items = [{"id": "W1", "title": "Paper A", "year": 2023, "doi": "10.1/abc", "venue": "JMIR", "authors": [{"name": "Ann Lee"}],
              "library": {"given_by": "Liliana", "discussion": "2026-11-03"}}]
    ris = ris_export(items, {"W1": {"key_points": [{"zh": "重點一", "en": "Point one"}]}}, {"W1": "/abs/path/a.pdf"})
    assert "TY  - JOUR" in ris and "DO  - 10.1/abc" in ris and "AU  - Ann Lee" in ris
    assert "重點一" in ris and "Liliana" in ris and "L1  - /abs/path/a.pdf" in ris
    assert ris.strip().endswith("ER  -")


def test_library_figure_paths_point_into_library_folder():
    figs = [{"label": "Figure 1", "image": "../papers/2023_Lee_x_W1/figures/figure-1.png"}, {"label": "Table 1", "image": None}]
    assert [f["image"] for f in lib_entry_paths(figs)] == ["../../library/out/papers/2023_Lee_x_W1/figures/figure-1.png", None]


GRANTS = [{"key": "NIH:NOW", "status": "confirmed", "start": "2023-01-01", "end": "2027-06-30", "title": "now"}]
ACT = {g["key"]: g for g in active_grants(GRANTS, today="2026-10-26")}


def draft(refs_paper="L1"):
    v = version()
    for k in ("synopsis", "rationale", "contribution"):
        v[k]["refs"] = [refs_paper]
    v["gaps"][0]["refs"] = [refs_paper]
    v["studies"][0]["methods"]["refs"] = [refs_paper]
    return v


def test_draft_from_selected_papers_passes():
    assert check_lib_draft(draft("L1"), selected={"L1", "L2"}, prof_ids={"W1", "W2"}, active=ACT) == []


def test_draft_cannot_cite_unselected_library_paper_and_must_use_selection():
    w = {f["why"] for f in check_lib_draft(draft("L9"), selected={"L1"}, prof_ids={"W1"}, active=ACT)}
    assert "unknown_paper:L9" in w and "must_cite_selected" in w


def test_draft_needs_sources_on_every_claim_section():
    v = draft("L1")
    v["contribution"]["refs"] = []
    assert "needs_source" in {f["why"] for f in check_lib_draft(v, selected={"L1"}, prof_ids={"W1"}, active=ACT)}
