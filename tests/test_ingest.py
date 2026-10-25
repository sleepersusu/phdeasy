"""故意埋錯：ingest 必須抓到拿錯檔案、掃描檔、原檔被改。"""
import json

import pymupdf

from ingest import convert, verify_hashes
from pipeline.fetch import sha256_file

W = {"id": "W1", "title": "AI HeartBot to Increase Women's Awareness of Heart Attack", "kind": "full", "abstract": "Abs text."}


def _pdf(path, text):
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    doc.save(path)


def test_wrong_file_is_quarantined_and_falls_back_to_abstract(tmp_path):
    _pdf(tmp_path / "a.pdf", "Quality of life among colorectal cancer survivors. " + "word " * 600)
    text, stype, exc = convert(tmp_path, W, {"status": "ok", "path": "a.pdf", "ext": "pdf"})
    kinds = [k for k, _ in exc]
    assert "title_mismatch" in kinds and "abstract_only" in kinds
    assert stype == "abstract" and "[abs]" in text


def test_scanned_pdf_is_exception(tmp_path):
    _pdf(tmp_path / "s.pdf", "")
    _, stype, exc = convert(tmp_path, W, {"status": "ok", "path": "s.pdf", "ext": "pdf"})
    assert "no_text" in [k for k, _ in exc] and stype == "abstract"


def test_good_pdf_passes(tmp_path):
    _pdf(tmp_path / "g.pdf", "AI HeartBot to Increase Women's Awareness of Heart Attack\n" + "word " * 600)
    text, stype, exc = convert(tmp_path, W, {"status": "ok", "path": "g.pdf", "ext": "pdf"})
    assert stype == "pdf" and exc == [] and "[p.1]" in text


def test_no_fulltext_no_abstract_is_no_source(tmp_path):
    _, stype, exc = convert(tmp_path, {**W, "abstract": None}, {"status": "no_free_fulltext"})
    assert stype == "none" and [k for k, _ in exc] == ["no_source"]


def test_modified_original_is_detected(tmp_path):
    (tmp_path / "pdfs").mkdir()
    f = tmp_path / "pdfs" / "x.pdf"
    f.write_bytes(b"%PDF-1.4 original")
    hashes = {"pdfs/x.pdf": sha256_file(f)}
    (tmp_path / "inbox").mkdir()
    assert verify_hashes(tmp_path, hashes) == []
    f.write_bytes(b"%PDF-1.4 tampered")
    assert verify_hashes(tmp_path, hashes) == ["pdfs/x.pdf"]


def test_new_inbox_file_gets_hashed(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "mine.pdf").write_bytes(b"%PDF-1.4")
    hashes = {}
    verify_hashes(tmp_path, hashes)
    assert "inbox/mine.pdf" in hashes


def test_supplement_file_is_quarantined(tmp_path):
    _pdf(tmp_path / "app.pdf", "CONSORT-EHEALTH (V 1.6.1) - Submission/Publication Form\nAI HeartBot to Increase Women's Awareness of Heart Attack\n" + "word " * 600)
    _, stype, exc = convert(tmp_path, W, {"status": "ok", "path": "app.pdf", "ext": "pdf"})
    assert "not_main_text" in [k for k, _ in exc] and stype == "abstract"


def test_rules_version_forces_recheck():
    from ingest import needs_redo, RULES_VERSION
    prev = {"source_sha256": "h", "rules": RULES_VERSION - 1}
    assert needs_redo(prev, "h", True)
    assert not needs_redo({"source_sha256": "h", "rules": RULES_VERSION}, "h", True)
    assert needs_redo({"source_sha256": "h", "rules": RULES_VERSION}, "other", True)
    assert needs_redo({"source_sha256": "h", "rules": RULES_VERSION}, "h", False)  # 文字檔不見


def test_short_card_without_any_source_is_title_only(tmp_path):
    _, stype, exc = convert(tmp_path, {**W, "kind": "short", "abstract": None}, {"status": "not_needed"})
    assert stype == "none" and [k for k, _ in exc] == ["title_only"]


def test_title_only_does_not_count_toward_circuit(tmp_path):
    from pipeline.exceptions import INFO_KINDS
    assert "title_only" in INFO_KINDS


def test_preprint_text_for_published_article_is_flagged(tmp_path):
    _pdf(tmp_path / "g.pdf", "AI HeartBot to Increase Women's Awareness of Heart Attack\n" + "word " * 600)
    row = {"status": "ok", "path": "g.pdf", "ext": "pdf", "url": "https://www.medrxiv.org/content/10.1101/x.full.pdf"}
    text, stype, exc = convert(tmp_path, {**W, "type": "article"}, row)
    assert stype == "pdf" and [k for k, _ in exc] == ["preprint_text"]


def test_file_moved_by_reject_keeps_its_hash(tmp_path):
    (tmp_path / "pdfs" / "2024").mkdir(parents=True)
    (tmp_path / "pdfs" / "_rejected").mkdir()
    (tmp_path / "inbox").mkdir()
    f = tmp_path / "pdfs" / "2024" / "W1_x.xml"
    f.write_bytes(b"<article>supp</article>")
    hashes = {"pdfs/2024/W1_x.xml": sha256_file(f)}
    f.rename(tmp_path / "pdfs" / "_rejected" / "W1_x.xml")
    assert verify_hashes(tmp_path, hashes) == [] and "pdfs/_rejected/W1_x.xml" in hashes
    (tmp_path / "pdfs" / "_rejected" / "W1_x.xml").write_bytes(b"tampered")
    assert verify_hashes(tmp_path, hashes) == ["pdfs/_rejected/W1_x.xml"]
