"""停 1 報告：寫 stop1-report.md 與 out/zotero/<slug>.ris，印出摘要。

  uv run python scripts/setup_report.py runs/<slug>
"""
import argparse
import csv
import json
from pathlib import Path

from pipeline.export import to_ris, unpaired_preprints


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    args = ap.parse_args()
    run = Path(args.run)
    wd = run / "work"
    works = json.loads((wd / "works.json").read_text())
    dropped = json.loads((wd / "dropped.json").read_text())
    cands = json.loads((wd / "candidates.json").read_text())
    xlog = json.loads((wd / "crosscheck_log.json").read_text())
    authors = json.loads((wd / "author_candidates.json").read_text())
    with open(run / "pdfs" / "index.csv", newline="") as f:
        index = {r["id"]: r for r in csv.DictReader(f)}

    full = [w for w in works if w["kind"] == "full"]
    ok = [w for w in full if index.get(w["id"], {}).get("status") == "ok"]
    miss = [w for w in full if index.get(w["id"], {}).get("status") == "no_free_fulltext"]
    pre = [p for p in unpaired_preprints(works) if p["score"] >= 0.5]

    L = [f"# 停 1 報告：{run.name}", ""]
    L += ["## 1. 身分", "", "| 作者 id | 姓名 | ORCID | 文章數 | 目前機構 | 主要主題 |", "|---|---|---|---|---|---|"]
    for a in authors:
        L.append(f"| {a['id']} | {a['name']} | {a['orcid'] or ''} | {a['works_count']} | {'; '.join(a['institutions'])} | {'; '.join(a['top_topics'][:3])} |")
    L += ["", "## 2. 數字", "",
          f"- 保留 {len(works)} 篇（完整卡 {len(full)}、短卡 {len(works) - len(full)}）；合併或排除 {len(dropped)} 篇",
          f"- 有免費全文 {len(ok)}／{len(full)}；找不到 {len(miss)}（見 `missing.md`）",
          f"- 外部平台有、OpenAlex 沒有的候選：{len(cands)} 篇",
          "- 交叉比對：" + "、".join(f"{x['source']} {x['result']}{'(' + str(x['records']) + ')' if 'records' in x else ''}" for x in xlog), ""]
    L += ["## 3. 需要你確認", ""]
    L += ["### 3a. 外部候選（要加入嗎？）", ""] + ([f"- {c['doi'] or ''} {c['title']}（{c.get('year')}；{', '.join(c['sources'])}）" for c in cands] or ["- 無"]) + [""]
    L += ["### 3b. 未合併的預印本（是同一篇的不同版本，還是不同文章？）", ""]
    L += [f"- {p['id']} {p['title']}\n  - 最像：{p['best_match']} {p['best_title']}（相似度 {p['score']}）" for p in pre] or ["- 無"]
    L += ["", "### 3c. 機構不符或疑似重複", ""]
    flags = [w for w in works if w.get("affiliation_flag") or w.get("possible_duplicate_of")]
    L += [f"- {w['id']} {w['title']}" + (f"（疑似重複 {w['possible_duplicate_of']}）" if w.get("possible_duplicate_of") else "（目標作者機構不符）") for w in flags] or ["- 無"]
    L += ["", "## 4. 文章清單", "", "| id | 年 | 類型 | 期刊 | 教授作者序 | 全文 | 標題 |", "|---|---|---|---|---|---|---|"]
    for w in sorted(works, key=lambda w: (w["year"], w["id"])):
        r = index.get(w["id"], {})
        st = {"ok": f"✓ {r.get('ext')}（{r.get('source')}）", "no_free_fulltext": "✗ 無免費全文", "not_needed": "短卡不需"}.get(r.get("status"), "?")
        pos = (w.get("target_position") or "") + ("＋通訊" if w.get("target_corresponding") else "")
        L.append(f"| {w['id']} | {w['year']} | {w['type']} | {w.get('venue') or ''} | {pos} | {st} | {w['title']} |")
    L += ["", "## 5. 合併或排除", ""] + [f"- {d['id']}：{d['reason']}" + (f" → {d['kept']}" if d.get("kept") else "") + f"｜{d['title']}" for d in dropped]
    (run / "stop1-report.md").write_text("\n".join(L) + "\n")

    zdir = run / "out" / "zotero"
    zdir.mkdir(parents=True, exist_ok=True)
    (zdir / f"{run.name}.ris").write_text(to_ris(works, index, run, tags=[f"phdeasy:{run.name}"]))
    print(f"DONE 報告 {run / 'stop1-report.md'}；RIS {zdir / (run.name + '.ris')}；{len(works)} 篇，全文 {len(ok)}/{len(full)}，候選 {len(cands)}，待確認預印本 {len(pre)}")


if __name__ == "__main__":
    main()
