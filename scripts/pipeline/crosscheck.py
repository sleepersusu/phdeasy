"""外部平台的文章清單解析，以及找出「外部有、OpenAlex 清單沒有」的候選文章。"""
import re
import xml.etree.ElementTree as ET

from .works import bare_doi, normalize_title, _similar

TITLE_MATCH_RATIO = 0.90


def _in(year, a, b):
    return year is not None and a <= year <= b


def _year(text):
    m = re.search(r"(19|20)\d{2}", str(text or ""))
    return int(m.group(0)) if m else None


def orcid_records(data, a, b):
    out = []
    for g in data.get("group", []):
        s = (g.get("work-summary") or [{}])[0]
        year = _year(((s.get("publication-date") or {}).get("year") or {}).get("value"))
        doi = next(
            (e["external-id-value"] for e in (g.get("external-ids") or {}).get("external-id", []) if e.get("external-id-type") == "doi"),
            None,
        )
        if _in(year, a, b):
            out.append({"doi": bare_doi(doi), "title": ((s.get("title") or {}).get("title") or {}).get("value"), "year": year, "source": "orcid"})
    return out


def pubmed_records(esummary, a, b):
    res = esummary.get("result", {})
    out = []
    for uid in res.get("uids", []):
        r = res[uid]
        year = _year(r.get("pubdate"))
        if not _in(year, a, b):
            continue
        doi = next((x["value"] for x in r.get("articleids", []) if x.get("idtype") == "doi"), None)
        out.append({"doi": bare_doi(doi), "title": r.get("title"), "year": year, "source": "pubmed", "pmid": uid})
    return out


def europepmc_records(data, a, b):
    out = []
    for r in (data.get("resultList") or {}).get("result", []):
        year = _year(r.get("pubYear"))
        if _in(year, a, b):
            out.append({"doi": bare_doi(r.get("doi")), "title": r.get("title"), "year": year, "source": "europepmc", "pmid": r.get("pmid")})
    return out


def pick_s2_author(candidates, known_dois):
    """candidates: {s2 作者 id: [論文]}；選與 OpenAlex DOI 重疊最多的；完全沒重疊回 None。"""
    best, best_n = None, 0
    for aid, papers in candidates.items():
        n = sum(1 for p in papers if bare_doi((p.get("externalIds") or {}).get("DOI")) in known_dois)
        if n > best_n:
            best, best_n = aid, n
    return best


def s2_records(papers, a, b):
    out = []
    for p in papers:
        if _in(p.get("year"), a, b):
            out.append({"doi": bare_doi((p.get("externalIds") or {}).get("DOI")), "title": p.get("title"), "year": p.get("year"), "source": "semantic_scholar"})
    return out


ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv_records(atom_text, a, b):
    root = ET.fromstring(atom_text)
    out = []
    for e in root.findall("a:entry", ATOM):
        year = _year(e.findtext("a:published", default="", namespaces=ATOM))
        if not _in(year, a, b):
            continue
        aid = re.sub(r"v\d+$", "", e.findtext("a:id", default="", namespaces=ATOM).rsplit("/abs/", 1)[-1])
        title = " ".join(e.findtext("a:title", default="", namespaces=ATOM).split())
        doi = e.findtext("arxiv:doi", default=None, namespaces=ATOM)
        out.append({"doi": bare_doi(doi), "title": title, "year": year, "source": "arxiv", "arxiv_id": aid})
    return out


def external_only(works, records):
    known = set()
    for w in works:
        if w.get("doi"):
            known.add(w["doi"])
        known.update(w.get("merged_dois") or [])
    titles = [w.get("title") for w in works]

    merged = {}
    for r in records:
        doi = bare_doi(r.get("doi"))
        if doi and doi in known:
            continue
        if any(_similar(r.get("title"), t) >= TITLE_MATCH_RATIO for t in titles):
            continue
        key = doi or normalize_title(r.get("title"))
        m = merged.setdefault(key, {**r, "doi": doi, "sources": set()})
        m["sources"].add(r["source"])
    out = []
    for m in merged.values():
        m.pop("source", None)
        m["sources"] = sorted(m["sources"])
        out.append(m)
    return out
