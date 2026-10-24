"""全文找尋鏈：依序問每個來源要候選網址，下載並檢查檔頭，每次嘗試都記錄。"""
from .fetch import is_jats_xml, is_pdf, is_supplementary_url

SOURCES = [
    "zotero",
    "openalex",
    "landing",
    "unpaywall",
    "europepmc",
    "pmc_oa",
    "ncbi_efetch",
    "semantic_scholar",
    "preprints",
    "core",
    "inbox",
]
RETRIES = 3
TRANSIENT = ("timeout", "http_429", "http_5", "conn_error")


class SkipSource(Exception):
    """來源無法使用（例：沒設 API key），記錄後跳過。"""


def _transient(status):
    return any(status.startswith(t) for t in TRANSIENT)


def _fetch(url, download, sleep):
    status = "none"
    for attempt in range(RETRIES):
        data, status = download(url)
        if data is not None or not _transient(status):
            return data, status
        if attempt < RETRIES - 1:
            sleep(2 ** attempt)
    return None, status


def run_chain(work, resolvers, download, log, sleep):
    """resolvers: [(來源名, work -> [網址])]；download: 網址 -> (bytes|None, 狀態)。

    回傳 {"status": "ok", source, url, ext, content} 或 {"status": "no_free_fulltext", tried}。
    PDF 優先；整條鏈都沒有 PDF 時才用 JATS XML。
    """
    tried, xml_hit = [], None
    for name, resolve in resolvers:
        try:
            urls = resolve(work)
        except SkipSource as e:
            tried.append(f"{name}:skipped({e})")
            log({"id": work["id"], "source": name, "url": None, "result": f"skipped({e})"})
            continue
        except Exception as e:  # 來源 API 壞掉不擋整條鏈
            tried.append(f"{name}:error")
            log({"id": work["id"], "source": name, "url": None, "result": f"error({type(e).__name__}: {e})"})
            continue
        if not urls:
            tried.append(f"{name}:none")
            log({"id": work["id"], "source": name, "url": None, "result": "none"})
            continue
        results = []
        for url in urls:
            if is_supplementary_url(url):
                log({"id": work["id"], "source": name, "url": url, "result": "supplementary_url"})
                results.append("supplementary_url")
                continue
            data, status = _fetch(url, download, sleep)
            if data is not None and is_pdf(data):
                log({"id": work["id"], "source": name, "url": url, "result": "ok"})
                return {"status": "ok", "source": name, "url": url, "ext": "pdf", "content": data}
            if data is not None and is_jats_xml(data):
                result = "ok_xml"
                if xml_hit is None:
                    xml_hit = {"status": "ok", "source": name, "url": url, "ext": "xml", "content": data}
            elif data is not None:
                result = "not_pdf"
            else:
                result = status
            log({"id": work["id"], "source": name, "url": url, "result": result})
            results.append(result)
        tried.append(f"{name}:{','.join(results)}")
    if xml_hit:
        return xml_hit
    return {"status": "no_free_fulltext", "tried": tried}
