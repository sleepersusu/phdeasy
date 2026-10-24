"""停 1 之後：把本人決定加入的外部候選加進 work/works.json。

  uv run python scripts/add_works.py runs/<slug> --doi 10.2196/31576 --doi 10.1016/... [--year-from-candidates]

OpenAlex 年份與候選來源（PubMed 等）不同時，以候選來源為準並保留 openalex_year，記例外。
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from pipeline.exceptions import add_exception
from pipeline.http import get_json, openalex_params
from pipeline.state import load_state
from pipeline.works import fill_target_by_name, normalize_work
from setup_list_works import SELECT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--doi", action="append", required=True)
    args = ap.parse_args()
    run = Path(args.run)
    st = load_state(run)
    works = json.loads((run / "work" / "works.json").read_text())
    cands = {c["doi"]: c for c in json.loads((run / "work" / "candidates.json").read_text())}
    have = {w["doi"] for w in works}
    surname = st["professor"]["name"].split()[-1]
    for doi in args.doi:
        doi = doi.lower()
        if doi in have:
            print(f"SKIP {doi} 已在清單")
            continue
        raw = get_json(f"https://api.openalex.org/works/doi:{quote(doi)}?select={SELECT}{openalex_params()}")
        w = fill_target_by_name(normalize_work(raw, st["author_id"]), surname)
        w["added_by_owner"] = True
        c = cands.get(doi) or {}
        if c.get("year") and c["year"] != w["year"]:
            w["openalex_year"], w["year"] = w["year"], c["year"]
            add_exception(run, w["id"], "setup", "year_mismatch", f"OpenAlex {w['openalex_year']}，{'/'.join(c.get('sources', []))} {c['year']}；依本人決定加入，年份採 {c['year']}")
        if w.get("target_link") == "name_only":
            add_exception(run, w["id"], "setup", "author_not_linked", "OpenAlex 未把目標作者連到作者 id，作者序以姓名比對補上")
        if not w.get("pmid") and c.get("pmid"):
            w["pmid"] = c["pmid"]
        works.append(w)
        print(f"ADD {w['id']} {w['year']} {w['title'][:60]}")
    (run / "work" / "works.json").write_text(json.dumps(works, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
