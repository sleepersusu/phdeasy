from pipeline.http import user_agent
from pipeline.fetch import citation_pdf_urls


def test_localhost_uses_plain_user_agent():
    # Zotero 會拒絕帶瀏覽器 UA 的本機請求
    assert "Mozilla" not in user_agent("http://127.0.0.1:23119/connector/ping")
    assert "Mozilla" not in user_agent("http://localhost:23119/api/users/0/items")
    assert "Mozilla" in user_agent("https://europepmc.org/x")


def test_citation_pdf_urls_from_meta_tags():
    html = b'''<html><head>
    <meta name="citation_title" content="x">
    <meta name="citation_pdf_url" content="https://journal.org/a.pdf">
    <meta content="/rel/b.pdf" name="citation_pdf_url" />
    </head></html>'''
    assert citation_pdf_urls(html, "https://journal.org/article/1") == ["https://journal.org/a.pdf", "https://journal.org/rel/b.pdf"]


def test_citation_pdf_urls_none():
    assert citation_pdf_urls(b"<html></html>", "https://x") == []
