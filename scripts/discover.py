"""查詢教授：依本人的研究興趣（runs/_me/me.json）找近幾年主導相關研究的人 → runs/_discover/latest.json（首頁「查詢教授」讀它）。

  uv run python scripts/discover.py [--query "額外關鍵字"] [--from 2022] [--top 40]

只呼叫 OpenAlex（公開資料）；本人按「加入目標教授」之前，不會開始建教授檔案。
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pipeline.discover import aggregate, interest_query
from pipeline.http import get_json, openalex_params

RUNS = Path(__file__).resolve().parent.parent / "runs"
SELECT = "id,title,publication_year,doi,authorships,awards"


def search(q, since, pages=2):
    out = []
    for page in range(1, pages + 1):
        url = (f"https://api.openalex.org/works?filter=title_and_abstract.search:{quote(q)},from_publication_date:{since}-01-01,type:article"
               f"&per-page=200&page={page}&select={SELECT}{openalex_params()}")
        res = get_json(url).get("results") or []
        out += res
        if len(res) < 200:
            break
    return out


def enrich(cands):
    """一次查這些人的 OpenAlex 作者資料：h-index、總發表、ORCID、目前機構。"""
    for i in range(0, len(cands), 50):
        chunk = cands[i:i + 50]
        url = f"https://api.openalex.org/authors?filter=openalex:{'|'.join(c['id'] for c in chunk)}&per-page=50{openalex_params()}"
        by = {a["id"].rsplit("/", 1)[-1]: a for a in get_json(url).get("results") or []}
        for c in chunk:
            a = by.get(c["id"]) or {}
            last = (a.get("last_known_institutions") or [{}])[0]
            c.update({"h_index": (a.get("summary_stats") or {}).get("h_index"), "works_count": a.get("works_count"),
                      "orcid": (a.get("orcid") or "").rsplit("/", 1)[-1] or None,
                      "institution": last.get("display_name") or c["institution"], "country": last.get("country_code") or c["country"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="")
    ap.add_argument("--from", dest="since", type=int, default=datetime.now().year - 4)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    me = json.loads((RUNS / "_me" / "me.json").read_text())
    labels = [i.get("en") for i in me.get("interests") or [] if i.get("en")] + ([a.query] if a.query.strip() else [])
    exclude = set()
    for st in RUNS.glob("*/state.json"):
        aid = (json.loads(st.read_text()).get("author_id") or "").rsplit("/", 1)[-1]
        if aid:
            exclude.add(aid)
    results = {}
    for label in labels:
        results[label] = search(interest_query(label), a.since)
        print(f"  {label}：{len(results[label])} 篇", flush=True)
    cands = aggregate(results, exclude)[: a.top * 2]
    enrich(cands)
    cands = [c for c in cands if c.get("institution")][: a.top]  # 沒有機構的（多半是署名或資料不全）不列
    out = RUNS / "_discover"
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps({"created": datetime.now().astimezone().isoformat(timespec="seconds"), "since": a.since,
                                                 "interests": labels, "candidates": cands}, ensure_ascii=False, indent=1))
    print(f"DONE 查詢教授：{len(cands)} 位（{a.since} 年起、主導的論文標題或摘要寫到你的興趣）")


if __name__ == "__main__":
    main()
