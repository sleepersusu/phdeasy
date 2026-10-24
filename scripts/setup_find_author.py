"""停 1 第一步：在 OpenAlex 找候選作者身分，寫 work/author_candidates.json 並印出比較表。

  uv run python scripts/setup_find_author.py runs/<slug> "Yoshimi Fukuoka" [--orcid 0000-...]
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from pipeline.http import get_json, openalex_params
from pipeline.works import strip_prefix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("name")
    ap.add_argument("--orcid", default=None)
    args = ap.parse_args()

    if args.orcid:
        url = f"https://api.openalex.org/authors?filter=orcid:{args.orcid}{openalex_params()}"
    else:
        url = f"https://api.openalex.org/authors?search={quote(args.name)}&per-page=10{openalex_params()}"
    res = get_json(url)["results"]

    cands = []
    for a in res:
        cands.append(
            {
                "id": strip_prefix(a["id"]),
                "name": a["display_name"],
                "orcid": a.get("orcid"),
                "works_count": a.get("works_count"),
                "cited_by": a.get("cited_by_count"),
                "institutions": [i.get("display_name") for i in a.get("last_known_institutions") or []],
                "past_institutions": sorted({(x.get("institution") or {}).get("display_name") for x in a.get("affiliations") or []} - {None}),
                "top_topics": [t.get("display_name") for t in (a.get("topics") or [])[:5]],
                "alt_names": a.get("display_name_alternatives", [])[:8],
            }
        )
    out = Path(args.run) / "work" / "author_candidates.json"
    out.write_text(json.dumps(cands, ensure_ascii=False, indent=2))
    for c in cands:
        print(f"{c['id']}\t{c['name']}\t{c['orcid']}\tworks={c['works_count']}\t{'; '.join(c['institutions'])}\t{'; '.join(c['top_topics'][:3])}")
    print(f"DONE 候選 {len(cands)} 位 → {out}")


if __name__ == "__main__":
    main()
