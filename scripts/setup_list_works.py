"""停 1 第二步：抓目標作者在年份範圍內的文章、去重、外部平台交叉比對。

  uv run python scripts/setup_list_works.py runs/<slug> --author A5047259794 [--from 2022 --to 2026] [--affil "San Francisco"]

產出：work/openalex_raw.json、work/works.json、work/dropped.json、work/candidates.json、work/crosscheck_log.json
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from pipeline.crosscheck import (
    arxiv_records,
    europepmc_records,
    external_only,
    orcid_records,
    pick_s2_author,
    pubmed_records,
    s2_records,
)
from pipeline.http import get, get_json, openalex_params, s2_headers
from pipeline.works import dedupe, normalize_work, strip_prefix

SELECT = "id,doi,title,display_name,publication_year,type,primary_location,best_oa_location,locations,authorships,abstract_inverted_index,primary_topic,is_retracted,ids"


def fetch_openalex(author, a, b):
    out, cursor = [], "*"
    while cursor:
        url = (
            f"https://api.openalex.org/works?filter=author.id:{author},publication_year:{a}-{b}"
            f"&per-page=200&cursor={cursor}&select={SELECT}{openalex_params()}"
        )
        d = get_json(url)
        out.extend(d["results"])
        cursor = d["meta"].get("next_cursor") if d["results"] else None
    return out


def crosscheck(author_rec, name, affil, works, a, b, log):
    recs = []

    def attempt(source, fn):
        try:
            got = fn()
            recs.extend(got)
            log.append({"source": source, "result": "ok", "records": len(got)})
        except Exception as e:
            log.append({"source": source, "result": f"error({type(e).__name__}: {e})"})

    orcid = (author_rec.get("orcid") or "").rsplit("/", 1)[-1]
    if orcid:
        attempt("orcid", lambda: orcid_records(get_json(f"https://pub.orcid.org/v3.0/{orcid}/works"), a, b))
    else:
        log.append({"source": "orcid", "result": "skipped(no orcid)"})

    parts = name.split()
    au = f"{parts[-1]} {parts[0][0]}" if len(parts) > 1 else name

    def pubmed():
        term = f'{au}[au] AND {a}:{b}[dp]' + (f' AND "{affil}"[ad]' if affil else "")
        ids = get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=500&term={quote(term)}")["esearchresult"]["idlist"]
        if not ids:
            return []
        return pubmed_records(get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id={','.join(ids)}"), a, b)

    attempt("pubmed", pubmed)

    def epmc():
        q = f'AUTH:"{au}" AND PUB_YEAR:[{a} TO {b}]' + (f' AND AFF:"{affil}"' if affil else "")
        return europepmc_records(get_json(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&pageSize=500&query={quote(q)}"), a, b)

    attempt("europepmc", epmc)

    def s2():
        known = {w["doi"] for w in works if w["doi"]}
        cands = {}
        for c in get_json(f"https://api.semanticscholar.org/graph/v1/author/search?query={quote(name)}&limit=5", min_interval=1.1, retry_429=(5, 15, 30), headers=s2_headers())["data"]:
            cands[c["authorId"]] = get_json(
                f"https://api.semanticscholar.org/graph/v1/author/{c['authorId']}/papers?fields=title,year,externalIds&limit=500", min_interval=1.1, retry_429=(5, 15, 30), headers=s2_headers()
            )["data"]
        pick = pick_s2_author(cands, known)
        return s2_records(cands[pick], a, b) if pick else []

    attempt("semantic_scholar", s2)

    def arxiv():
        data, status = get(f"https://export.arxiv.org/api/query?search_query=au:{quote(parts[-1] + '_' + parts[0][0])}&max_results=200")
        if data is None:
            raise RuntimeError(status)
        return arxiv_records(data.decode("utf-8"), a, b)

    attempt("arxiv", arxiv)
    return external_only(works, recs)


def main_institutions(author_rec, works, author, share=0.1):
    """主要機構：OpenAlex 的「最近機構」；OpenAlex 沒給（有些人這欄是空的）就用他在這批文章裡至少 10% 都掛的機構。"""
    last = {i.get("display_name") for i in author_rec.get("last_known_institutions") or [] if i.get("display_name")}
    if last:
        return last
    cnt = {}
    for w in works:
        me = next((x for x in w["authors"] if x["id"] == author), None)
        for i in set((me or {}).get("institutions") or []):
            cnt[i] = cnt.get(i, 0) + 1
    return {i for i, n in cnt.items() if n >= max(1, share * len(works))}


def affiliation_flags(works, author, main_insts):
    """目標作者在該篇的機構不在主要機構清單 → 給停 1 本人看。沒有主要機構可比時不標（不然整批都會是不符）。"""
    flags = []
    if not main_insts:
        return flags
    for w in works:
        me = next((x for x in w["authors"] if x["id"] == author), None)
        insts = set((me or {}).get("institutions") or [])
        if insts and not insts & main_insts:
            flags.append({"id": w["id"], "title": w["title"], "institutions": sorted(insts)})
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--author", required=True)
    ap.add_argument("--from", dest="a", type=int, default=2022)
    ap.add_argument("--to", dest="b", type=int, default=2026)
    ap.add_argument("--affil", default=None, help="PubMed／Europe PMC 機構過濾字串")
    args = ap.parse_args()
    run = Path(args.run)
    work = run / "work"

    author_rec = get_json(f"https://api.openalex.org/authors/{args.author}?x=1{openalex_params()}")
    raw = fetch_openalex(args.author, args.a, args.b)
    (work / "openalex_raw.json").write_text(json.dumps(raw, ensure_ascii=False))
    works = [normalize_work(w, args.author) for w in raw]
    kept, dropped = dedupe(works, args.a, args.b)

    main_insts = main_institutions(author_rec, kept, args.author)
    flags = affiliation_flags(kept, args.author, main_insts)
    for w in kept:
        w["affiliation_flag"] = any(f["id"] == w["id"] for f in flags)

    log = []
    cands = crosscheck(author_rec, author_rec["display_name"], args.affil, kept, args.a, args.b, log)

    (work / "works.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2))
    (work / "dropped.json").write_text(json.dumps(dropped, ensure_ascii=False, indent=2))
    (work / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False, indent=2))
    (work / "crosscheck_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))

    full = sum(1 for w in kept if w["kind"] == "full")
    print(f"DONE OpenAlex {len(raw)} 筆 → 保留 {len(kept)}（完整卡 {full}、短卡 {len(kept) - full}），合併／排除 {len(dropped)}，"
          f"外部候選 {len(cands)}，機構不符 {len(flags)}，疑似重複 {sum(1 for w in kept if w.get('possible_duplicate_of'))}")
    for l in log:
        print(f"  crosscheck {l['source']}: {l['result']} {l.get('records', '')}")


if __name__ == "__main__":
    main()
