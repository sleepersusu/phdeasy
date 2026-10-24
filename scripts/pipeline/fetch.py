"""檔案檢查、歸位命名、缺全文報告、Zotero 附件解析。"""
import hashlib
import re
import unicodedata
from urllib.parse import unquote, urlparse


def is_pdf(data):
    return bool(data) and b"%PDF-" in data[:1024]


def is_jats_xml(data):
    head = (data or b"")[:4096].lower()
    return b"<article" in head and b"<body" in (data or b"").lower()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ascii_slug(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", "-", text).strip("-")


def pdf_relpath(work, ext):
    authors = work.get("authors") or []
    surname = _ascii_slug((authors[0].get("name") or "").split()[-1]) if authors and authors[0].get("name") else "NA"
    words = _ascii_slug(work.get("title") or "").split("-")[:6]
    short = "-".join(w for w in words if w)[:60] or "untitled"
    return f"pdfs/{work.get('year')}/{work['id']}_{surname}_{short}.{ext}"


def missing_report(works, have, tried):
    rows = [w for w in works if w["kind"] == "full" and w["id"] not in have]
    lines = [
        "# 找不到免費全文的文章",
        "",
        f"共 {len(rows)} 篇。請從學校圖書館下載 PDF 放進 `inbox/`（檔名隨意，ingest 會用 DOI 對應；檔名含文章 id 最保險）。",
        "",
        "| 文章 id | 年 | 標題 | 連結 | 已試來源 |",
        "|---|---|---|---|---|",
    ]
    for w in rows:
        link = f"https://doi.org/{w['doi']}" if w.get("doi") else "（無 DOI）"
        t = (w.get("title") or "").replace("|", "/")
        lines.append(f"| {w['id']} | {w['year']} | {t} | {link} | {'; '.join(tried.get(w['id'], []))} |")
    return "\n".join(lines) + "\n"


def zotero_pdf_paths(items, children, doi):
    doi = (doi or "").lower()
    paths = []
    for it in items:
        if (it.get("data", {}).get("DOI") or "").lower() != doi:
            continue
        for ch in children.get(it["key"], []):
            d = ch.get("data", {})
            href = ((ch.get("links") or {}).get("enclosure") or {}).get("href", "")
            if d.get("itemType") == "attachment" and d.get("contentType") == "application/pdf" and href.startswith("file://"):
                paths.append(unquote(urlparse(href).path))
    return paths
