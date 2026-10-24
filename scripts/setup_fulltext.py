"""全文找尋鏈：逐篇找免費全文，歸位到 pdfs/<年>/，寫 pdfs/index.csv、work/fulltext_log.jsonl、work/hashes.json、missing.md。

  uv run python scripts/setup_fulltext.py runs/<slug> [--only W123,W456] [--retry-missing]

可接續：index.csv 已是 ok 的文章不重做；--retry-missing 只重跑 no_free_fulltext 的（例：本人補了 inbox 之後）。
Unpaywall 需要環境變數 UNPAYWALL_EMAIL，CORE 需要 CORE_API_KEY；沒設就跳過並記錄。
"""
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from pipeline.fetch import citation_pdf_urls, match_inbox, missing_report, pdf_relpath, sha256_file, zotero_pdf_paths
from pipeline.fulltext import SkipSource, run_chain
from pipeline.index import find_existing, load_index, save_index
from pipeline.http import get, get_json
from pipeline.works import _similar

ZOTERO = "http://127.0.0.1:23119/api/users/0"


def r_zotero(w):
    data, status = get("http://127.0.0.1:23119/connector/ping", timeout=3, min_interval=0)
    if data is None:
        raise SkipSource("Zotero 未開啟")
    if not w.get("doi"):
        return []
    items = get_json(f"{ZOTERO}/items?q={quote(w['doi'])}&qmode=everything&itemType=-attachment&limit=25", min_interval=0)
    children = {it["key"]: get_json(f"{ZOTERO}/items/{it['key']}/children", min_interval=0) for it in items}
    return ["file://" + quote(p) for p in zotero_pdf_paths(items, children, w["doi"])]


def r_openalex(w):
    return list(w.get("pdf_candidates") or [])


def r_landing(w):
    urls = []
    for page in dict.fromkeys(w.get("landing_pages") or []):
        data, status = get(page, accept="text/html")
        if data:
            urls += [u for u in citation_pdf_urls(data, page) if u not in urls]
    return urls


def r_unpaywall(w):
    email = os.environ.get("UNPAYWALL_EMAIL")
    if not email:
        raise SkipSource("未設 UNPAYWALL_EMAIL")
    if not w.get("doi"):
        return []
    d = get_json(f"https://api.unpaywall.org/v2/{quote(w['doi'])}?email={quote(email)}")
    return [l["url_for_pdf"] for l in d.get("oa_locations") or [] if l.get("url_for_pdf")]


def _pmcid(w):
    if w.get("pmcid"):
        return w["pmcid"]
    q = f'DOI:"{w["doi"]}"' if w.get("doi") else (f"EXT_ID:{w['pmid']}" if w.get("pmid") else None)
    if not q:
        return None
    res = get_json(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core&query={quote(q)}")
    hit = next(iter((res.get("resultList") or {}).get("result", [])), {})
    w["_epmc_pdfs"] = [u["url"] for u in (hit.get("fullTextUrlList") or {}).get("fullTextUrl", []) if u.get("documentStyle") == "pdf" and u.get("availabilityCode") in ("OA", "F")]
    w["pmcid"] = hit.get("pmcid")
    return w["pmcid"]


def r_europepmc(w):
    pmc = _pmcid(w)
    urls = list(w.get("_epmc_pdfs") or [])
    if pmc:
        urls += [f"https://europepmc.org/articles/{pmc}?pdf=render", f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML"]
    return urls


def r_pmc_oa(w):
    pmc = w.get("pmcid") or _pmcid(w)
    if not pmc:
        return []
    data, status = get(f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmc}")
    urls = []
    if data:
        for link in ET.fromstring(data).iter("link"):
            if link.get("format") == "pdf":
                urls.append(link.get("href").replace("ftp://ftp.ncbi.nlm.nih.gov", "https://ftp.ncbi.nlm.nih.gov"))
    urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/pdf/")
    return urls


def r_s2(w):
    if not w.get("doi"):
        return []
    d = get_json(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(w['doi'])}?fields=openAccessPdf,externalIds", min_interval=1.1)
    urls = []
    if (d.get("openAccessPdf") or {}).get("url"):
        urls.append(d["openAccessPdf"]["url"])
    if (d.get("externalIds") or {}).get("ArXiv"):
        urls.append(f"https://arxiv.org/pdf/{d['externalIds']['ArXiv']}")
    return urls


def r_preprints(w):
    urls = []
    for doi in w.get("merged_dois") or []:
        m = re.match(r"10\.21203/rs\.3\.(rs-\d+)/v(\d+)", doi)
        if m:
            urls.append(f"https://www.researchsquare.com/article/{m.group(1)}/v{m.group(2)}.pdf")
        if doi.startswith("10.1101/"):
            d = get_json(f"https://api.biorxiv.org/details/medrxiv/{doi}")
            coll = d.get("collection") or get_json(f"https://api.biorxiv.org/details/biorxiv/{doi}").get("collection") or []
            for c in coll[-1:]:
                server = c.get("server", "medrxiv").lower()
                urls.append(f"https://www.{server}.org/content/{doi}v{c['version']}.full.pdf")
    data, status = get(f'https://export.arxiv.org/api/query?search_query=ti:%22{quote(w["title"] or "")}%22&max_results=3', min_interval=3)
    if data:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in ET.fromstring(data).findall("a:entry", ns):
            if _similar(" ".join(e.findtext("a:title", "", ns).split()), w["title"]) >= 0.9:
                urls.append(e.findtext("a:id", "", ns).replace("/abs/", "/pdf/"))
    return urls


def r_core(w):
    key = os.environ.get("CORE_API_KEY")
    if not key:
        raise SkipSource("未設 CORE_API_KEY")
    if not w.get("doi"):
        return []
    data, status = get(f'https://api.core.ac.uk/v3/search/works?q=doi:%22{quote(w["doi"])}%22&limit=5', headers={"Authorization": f"Bearer {key}"})
    if data is None:
        raise RuntimeError(status)
    return [r["downloadUrl"] for r in json.loads(data).get("results", []) if r.get("downloadUrl")]


def make_inbox_resolver(run, works):
    files = {}
    for p in sorted((run / "inbox").glob("**/*.pdf")):
        try:
            import pymupdf

            with pymupdf.open(p) as doc:
                files[str(p)] = "\n".join(doc[i].get_text() for i in range(min(2, len(doc))))
        except Exception:
            files[str(p)] = ""
    matched = match_inbox(files, works)

    def r_inbox(w):
        return ["file://" + quote(matched[w["id"]])] if w["id"] in matched else []

    return r_inbox


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--only", default=None)
    ap.add_argument("--retry-missing", action="store_true")
    args = ap.parse_args()
    run = Path(args.run)
    works = json.loads((run / "work" / "works.json").read_text())
    index = load_index(run)
    hashes_p = run / "work" / "hashes.json"
    hashes = json.loads(hashes_p.read_text()) if hashes_p.exists() else {}
    only = set(args.only.split(",")) if args.only else None

    resolvers = [
        ("zotero", r_zotero),
        ("openalex", r_openalex),
        ("landing", r_landing),
        ("unpaywall", r_unpaywall),
        ("europepmc", r_europepmc),
        ("pmc_oa", r_pmc_oa),
        ("semantic_scholar", r_s2),
        ("preprints", r_preprints),
        ("core", r_core),
        ("inbox", make_inbox_resolver(run, works)),
    ]
    logf = open(run / "work" / "fulltext_log.jsonl", "a")

    def log(entry):
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()

    done = 0
    for w in works:
        if only and w["id"] not in only:
            continue
        prev = index.get(w["id"])
        if prev and prev["status"] in ("ok", "not_needed"):
            continue
        if prev and prev["status"] == "no_free_fulltext" and not args.retry_missing:
            continue
        row = {"id": w["id"], "year": w["year"], "kind": w["kind"], "title": w["title"]}
        existing = find_existing(run, w["id"])
        if w["kind"] == "short":
            row["status"] = "not_needed"
        elif existing:
            h = sha256_file(run / existing)
            hashes[existing] = h
            row.update(status="ok", source=(prev or {}).get("source") or "existing", ext=existing.rsplit(".", 1)[-1], path=existing, sha256=h)
        else:
            res = run_chain(w, resolvers, lambda u: get(u, timeout=45), log, sleep=__import__("time").sleep)
            if res["status"] == "ok":
                rel = pdf_relpath(w, res["ext"])
                dest = run / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    dest.write_bytes(res["content"])
                h = sha256_file(dest)
                hashes[rel] = h
                row.update(status="ok", source=res["source"], ext=res["ext"], path=rel, sha256=h, url=res["url"])
            else:
                row.update(status="no_free_fulltext", tried="; ".join(res["tried"]))
        index[w["id"]] = row
        save_index(run, index)
        hashes_p.write_text(json.dumps(hashes, ensure_ascii=False, indent=2))
        done += 1
        print(f"  {w['id']} {row['status']} {row.get('source', '')}", flush=True)
    logf.close()

    have = {i for i, r in index.items() if r["status"] == "ok"}
    tried = {i: r.get("tried", "").split("; ") for i, r in index.items() if r["status"] == "no_free_fulltext"}
    (run / "missing.md").write_text(missing_report(works, have, tried))
    full = [w for w in works if w["kind"] == "full"]
    by_src = {}
    for r in index.values():
        if r["status"] == "ok":
            by_src[r["source"]] = by_src.get(r["source"], 0) + 1
    print(f"DONE 本次處理 {done}；完整卡 {len(full)} 篇，有全文 {len(have)}（{by_src}），無免費全文 {len(tried)}")


if __name__ == "__main__":
    main()
