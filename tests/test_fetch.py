from pipeline.fetch import is_pdf, is_jats_xml, sha256_file, missing_report, pdf_relpath, zotero_pdf_paths


def test_is_pdf_accepts_real_header():
    assert is_pdf(b"%PDF-1.7\n...")


def test_is_pdf_accepts_header_after_leading_whitespace():
    assert is_pdf(b"\r\n%PDF-1.4")


def test_is_pdf_rejects_html_paywall_page():
    assert not is_pdf(b"<!DOCTYPE html><html>Access denied</html>")


def test_is_pdf_rejects_empty():
    assert not is_pdf(b"")


def test_is_jats_xml():
    assert is_jats_xml(b'<?xml version="1.0"?><article xmlns:x="y"><body>..</body></article>')
    assert not is_jats_xml(b'{"error": "not found"}')
    assert not is_jats_xml(b"<?xml version='1.0'?><error/>")
    assert not is_jats_xml(b"<?xml version='1.0'?><article><front>only</front></article>")


def test_sha256_file(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_pdf_relpath_pattern():
    w = {"id": "W123", "year": 2024, "title": "An App-Based Physical Activity Intervention: A Randomized Trial!",
         "authors": [{"name": "Yoshimi Fukuoka"}]}
    assert pdf_relpath(w, "pdf") == "pdfs/2024/W123_Fukuoka_An-App-Based-Physical-Activity-Intervention.pdf"


def test_pdf_relpath_folds_accents_and_handles_no_author():
    w = {"id": "W1", "year": 2022, "title": "Café über", "authors": []}
    assert pdf_relpath(w, "xml") == "pdfs/2022/W1_NA_Cafe-uber.xml"


def test_missing_report_lists_attempts():
    works = [
        {"id": "W1", "title": "Has PDF", "doi": "10.1/a", "year": 2022, "kind": "full"},
        {"id": "W2", "title": "No PDF", "doi": "10.1/b", "year": 2023, "kind": "full"},
        {"id": "W3", "title": "Short", "doi": None, "year": 2023, "kind": "short"},
    ]
    tried = {"W2": ["openalex:http_403", "europepmc:none"]}
    md = missing_report(works, have={"W1"}, tried=tried)
    assert "W2" in md and "https://doi.org/10.1/b" in md
    assert "openalex:http_403" in md
    assert "W1" not in md
    assert "W3" not in md  # 短卡不需要全文


def test_zotero_pdf_paths_matches_doi_exactly():
    items = [
        {"key": "P1", "data": {"itemType": "journalArticle", "DOI": "10.2196/40764"}},
        {"key": "P2", "data": {"itemType": "journalArticle", "DOI": "10.2196/407640"}},
    ]
    children = {
        "P1": [
            {"data": {"itemType": "attachment", "contentType": "application/pdf"},
             "links": {"enclosure": {"href": "file:///Users/u/Zotero/storage/K1/a%20b.pdf"}}},
            {"data": {"itemType": "note"}, "links": {}},
        ],
        "P2": [
            {"data": {"itemType": "attachment", "contentType": "application/pdf"},
             "links": {"enclosure": {"href": "file:///wrong.pdf"}}},
        ],
    }
    assert zotero_pdf_paths(items, children, "10.2196/40764") == ["/Users/u/Zotero/storage/K1/a b.pdf"]


def test_match_inbox_by_id_in_filename_then_doi_in_text():
    from pipeline.fetch import match_inbox
    works = [{"id": "W1", "doi": "10.1/aa"}, {"id": "W2", "doi": "10.2196/40764"}, {"id": "W3", "doi": None}]
    files = {
        "/in/W1 paper.pdf": "nothing",
        "/in/random.pdf": "... https://doi.org/10.2196/40764 JMIR ...",
        "/in/other.pdf": "doi:10.2196/407640 different paper",
    }
    assert match_inbox(files, works) == {"W1": "/in/W1 paper.pdf", "W2": "/in/random.pdf"}


def test_supplementary_urls_detected():
    from pipeline.fetch import is_supplementary_url
    assert is_supplementary_url("https://jmir.org/api/download?alt_name=cancer_v8i1e31576_app4.pdf&filename=x.pdf")
    assert is_supplementary_url("https://ars.els-cdn.com/content/image/1-s2.0-S0-mmc1.pdf")
    assert is_supplementary_url("https://journal.org/article/10.1/abc/suppl_file/supplement.pdf")
    assert is_supplementary_url("https://www.mdpi.com/x/s1")
    assert not is_supplementary_url("https://cardio.jmir.org/2022/2/e40764/PDF")
    assert not is_supplementary_url("https://link.springer.com/content/pdf/10.1007/s00520-022-06870-5.pdf")


def test_needs_fulltext_includes_not_led_short_cards():
    from pipeline.fetch import needs_fulltext
    assert needs_fulltext({"kind": "full"})
    assert needs_fulltext({"kind": "short", "short_reason": "not_led"})  # 致謝段找計畫要用
    assert not needs_fulltext({"kind": "short"})


def test_osf_guid_and_pdf_pick():
    from pipeline.fetch import osf_guid, osf_pdfs
    assert osf_guid(["https://doi.org/x", "https://osf.io/7mux6"]) == "7mux6"
    assert osf_guid(["https://osf.io/preprints/psyarxiv/abc12"]) == "abc12"
    assert osf_guid(["https://example.org"]) is None
    listing = [("SAP", "plan.pdf", "https://osf.io/download/2/"), ("Protocol", "trial protocol.pdf", "https://osf.io/download/1/"),
               ("Protocol", "notes.docx", "https://osf.io/download/3/")]
    assert osf_pdfs(listing) == ["https://osf.io/download/1/", "https://osf.io/download/2/"]  # 只要 PDF，Protocol 資料夾優先
    tricky = [("Engagement trajectories", "Analysis plan (protocol v2).pdf", "https://osf.io/download/e/"),
              ("Protocol", "2026 Effect of a mobile health intervention.pdf", "https://osf.io/download/p/")]
    assert osf_pdfs(tricky)[0] == "https://osf.io/download/p/"  # 名為 Protocol 的資料夾勝過檔名含 protocol
