"""OpenAlex 沒有摘要的文章，改向 Europe PMC（PubMed 摘要）要；寫回 work/works.json 並標 abstract_source。

  uv run python scripts/fill_abstracts.py runs/<slug>
"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from pipeline.crosscheck import epmc_abstract
from pipeline.http import get_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    args = ap.parse_args()
    p = Path(args.run) / "work" / "works.json"
    works = json.loads(p.read_text())
    filled, still = 0, []
    for w in works:
        if w.get("abstract"):
            w.setdefault("abstract_source", "openalex")
            continue
        q = f"EXT_ID:{w['pmid']} AND SRC:MED" if w.get("pmid") else (f'DOI:"{w["doi"]}"' if w.get("doi") else None)
        ab = epmc_abstract(get_json(f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core&query={quote(q)}")) if q else None
        if ab:
            w["abstract"], w["abstract_source"] = ab, "europepmc"
            filled += 1
        else:
            still.append(w["id"])
    p.write_text(json.dumps(works, ensure_ascii=False, indent=2))
    print(f"DONE 補摘要 {filled} 篇；仍無摘要 {len(still)}：{still}")


if __name__ == "__main__":
    main()
