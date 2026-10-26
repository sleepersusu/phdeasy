"""查詢教授：依本人的研究興趣（runs/_me/me.json）找近幾年主導相關研究的人 → runs/_discover/latest.json（首頁「查詢教授」讀它）。

  uv run python scripts/discover.py [--query "額外關鍵字"] [--from 2022] [--top 40]
  uv run python scripts/discover.py --enrich-todo     # 列出還沒補過的學校（排名、獎學金）與人（掛名的博士學程、實驗室網址）
  uv run python scripts/discover.py --merge           # 核對 AI 新補的 runs/_discover/enrich-new.json（每個值都要有出處），累積進 enrich.json 再併進 latest.json

重新查詢時，enrich.json 裡已補過的學校與人照留，只有新出現的要補。

只呼叫 OpenAlex（公開資料）；本人按「加入目標教授」之前，不會開始建教授檔案。
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pipeline.discover import aggregate, check_enrich, best_funding, combine_enrich, enrich_todo, interest_query, merge_enrich
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
    for c in cands:  # 實驗室網址：先看 ORCID 本人填的網站（有就不用 AI 查）
        if not c.get("orcid"):
            continue
        try:
            urls = (get_json(f"https://pub.orcid.org/v3.0/{c['orcid']}/researcher-urls").get("researcher-url") or [])
        except RuntimeError:
            continue
        u = next(((x.get("url") or {}).get("value") for x in urls if ((x.get("url") or {}).get("value") or "").startswith("http")), None)
        if u:
            c["lab_url"], c["lab_src"] = u, f"https://orcid.org/{c['orcid']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="")
    ap.add_argument("--from", dest="since", type=int, default=datetime.now().year - 4)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--enrich-todo", action="store_true")
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    out = RUNS / "_discover"
    if a.enrich_todo or a.merge:
        d = json.loads((out / "latest.json").read_text())
        enr_p, new_p = out / "enrich.json", out / "enrich-new.json"
        enr = json.loads(enr_p.read_text()) if enr_p.exists() else {}
        if a.enrich_todo:
            print(json.dumps(enrich_todo(d["candidates"], enr), ensure_ascii=False, indent=1))
            return
        new = json.loads(new_p.read_text()) if new_p.exists() else {}
        fails = check_enrich(new)
        for f in fails:
            print(f"FAIL {f['where']} {f['why']}")
        if fails:
            raise SystemExit(1)
        enr = combine_enrich(enr, new)
        enr_p.write_text(json.dumps(enr, ensure_ascii=False, indent=1))
        if new_p.exists():
            new_p.unlink()
        d["candidates"] = merge_enrich(d["candidates"], enr)
        d["enriched"] = datetime.now().astimezone().isoformat(timespec="seconds")
        (out / "latest.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
        cs = d["candidates"]
        cnt = lambda f: sum(1 for c in cs if f(c))
        print(f"DONE 補資訊併入 {len(cs)} 位：QS {cnt(lambda c: c.get('qs_rank'))}、US News {cnt(lambda c: c.get('usnews_rank'))}、"
              f"全額 {cnt(lambda c: best_funding(c) == 'full')}、查過學程 {cnt(lambda c: c.get('programs') is not None)}、實驗室網址 {cnt(lambda c: c.get('lab_url'))}")
        return
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
    out.mkdir(exist_ok=True)
    res = {"created": datetime.now().astimezone().isoformat(timespec="seconds"), "since": a.since, "interests": labels, "candidates": cands}
    if (out / "enrich.json").exists():  # 之前補過的學校與人照留
        res["candidates"] = merge_enrich(cands, json.loads((out / "enrich.json").read_text()))
        res["enriched"] = res["created"]
    (out / "latest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"DONE 查詢教授：{len(cands)} 位（{a.since} 年起、主導的論文標題或摘要寫到你的興趣）")


if __name__ == "__main__":
    main()
