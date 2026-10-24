from pipeline.fulltext import run_chain, SkipSource, SOURCES

PDF = b"%PDF-1.7 body"
HTML = b"<!DOCTYPE html>paywall"


def make_dl(table):
    """table: url -> list of (bytes|None, status) returned on successive calls"""
    calls = []

    def dl(url):
        calls.append(url)
        seq = table[url]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return dl, calls


def test_stops_at_first_valid_pdf_and_logs_attempts():
    log = []
    dl, calls = make_dl({"u1": [(HTML, "ok")], "u2": [(PDF, "ok")], "u3": [(PDF, "ok")]})
    res = run_chain(
        {"id": "W1"},
        [("openalex", lambda w: ["u1"]), ("europepmc", lambda w: ["u2"]), ("semantic_scholar", lambda w: ["u3"])],
        dl, log.append, sleep=lambda s: None,
    )
    assert res["status"] == "ok" and res["source"] == "europepmc" and res["ext"] == "pdf"
    assert "u3" not in calls
    assert [e["result"] for e in log] == ["not_pdf", "ok"]


def test_retries_transient_errors_three_times():
    log = []
    dl, calls = make_dl({"u1": [(None, "timeout"), (None, "http_503"), (PDF, "ok")]})
    res = run_chain({"id": "W1"}, [("openalex", lambda w: ["u1"])], dl, log.append, sleep=lambda s: None)
    assert res["status"] == "ok"
    assert calls == ["u1", "u1", "u1"]


def test_does_not_retry_forbidden():
    log = []
    dl, calls = make_dl({"u1": [(None, "http_403")]})
    res = run_chain({"id": "W1"}, [("openalex", lambda w: ["u1"])], dl, log.append, sleep=lambda s: None)
    assert res["status"] == "no_free_fulltext"
    assert calls == ["u1"]


def test_gives_up_after_three_transient_failures():
    log = []
    dl, calls = make_dl({"u1": [(None, "timeout")]})
    res = run_chain({"id": "W1"}, [("openalex", lambda w: ["u1"])], dl, log.append, sleep=lambda s: None)
    assert res["status"] == "no_free_fulltext" and len(calls) == 3


def test_skipped_and_empty_sources_are_logged():
    log = []

    def needs_key(w):
        raise SkipSource("no UNPAYWALL_EMAIL")

    dl, _ = make_dl({})
    res = run_chain({"id": "W1"}, [("unpaywall", needs_key), ("europepmc", lambda w: [])], dl, log.append, sleep=lambda s: None)
    assert res["status"] == "no_free_fulltext"
    assert res["tried"] == ["unpaywall:skipped(no UNPAYWALL_EMAIL)", "europepmc:none"]
    assert {e["source"] for e in log} == {"unpaywall", "europepmc"}


def test_resolver_exception_is_logged_not_raised():
    log = []

    def boom(w):
        raise RuntimeError("api down")

    dl, _ = make_dl({"u": [(PDF, "ok")]})
    res = run_chain({"id": "W1"}, [("semantic_scholar", boom), ("preprints", lambda w: ["u"])], dl, log.append, sleep=lambda s: None)
    assert res["status"] == "ok" and res["source"] == "preprints"
    assert log[0]["result"].startswith("error")


def test_accepts_jats_xml():
    log = []
    xml = b'<?xml version="1.0"?><article><body><p>x</p></body></article>'
    dl, _ = make_dl({"u": [(xml, "ok")]})
    res = run_chain({"id": "W1"}, [("europepmc", lambda w: ["u"])], dl, log.append, sleep=lambda s: None)
    assert res["ext"] == "xml"


def test_prefers_pdf_over_xml_within_source_order():
    # XML 只在整條鏈都沒有 PDF 時才採用
    log = []
    xml = b'<?xml version="1.0"?><article><body><p>x</p></body></article>'
    dl, _ = make_dl({"x": [(xml, "ok")], "p": [(PDF, "ok")]})
    res = run_chain({"id": "W1"}, [("europepmc", lambda w: ["x"]), ("preprints", lambda w: ["p"])], dl, log.append, sleep=lambda s: None)
    assert res["ext"] == "pdf" and res["source"] == "preprints"


def test_source_order_constant():
    assert SOURCES[0] == "zotero" and SOURCES[-1] == "inbox"
    assert "unpaywall" in SOURCES and "core" in SOURCES


def test_supplementary_url_skipped_without_download():
    log = []
    dl, calls = make_dl({"https://x.org/a_app4.pdf": [(PDF, "ok")], "https://x.org/main.pdf": [(PDF, "ok")]})
    res = run_chain({"id": "W1"}, [("openalex", lambda w: ["https://x.org/a_app4.pdf", "https://x.org/main.pdf"])], dl, log.append, sleep=lambda s: None)
    assert res["url"] == "https://x.org/main.pdf"
    assert calls == ["https://x.org/main.pdf"]
    assert log[0]["result"] == "supplementary_url"
