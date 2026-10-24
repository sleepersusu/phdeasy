"""network：合作者、作者序角色、領域分佈、年度分佈。

  uv run python scripts/network.py build runs/<slug>
      → work/network.json、work/author_lists.md（給計數 agent）、out/data/{works,coauthors,topics}.csv
  uv run python scripts/network.py check runs/<slug>
      → 比對 work/count-check.json（計數 agent 產出），寫 work/count-diff.json；不一致時 exit 1
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from pipeline.index import load_index
from pipeline.exceptions import add_exception
from pipeline.network import author_lists_md, coauthor_stats, competition_ranks, compare_counts, possible_splits, role_summary, topic_counts, year_counts
from pipeline.state import load_state

TOP = 10
MIN_N = 2  # 計數 agent 只列出合作 ≥ 2 篇的人


def _csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)


def build(run):
    st = load_state(run)
    works = json.loads((run / "work" / "works.json").read_text())
    surname = st["professor"]["name"].split()[-1]
    stats = coauthor_stats(works, st["author_id"], surname)
    net = {
        "target": {"author_id": st["author_id"], "name": st["professor"]["name"]},
        "works_total": len(works),
        "roles": role_summary(works),
        "years": year_counts(works),
        "topics": topic_counts(works),
        "coauthors_total": len(stats),
        "coauthors_linked": sum(s["linked"] for s in stats),
        "possible_splits": possible_splits(stats),
        "coauthors": stats,
    }
    for g in net["possible_splits"]:
        add_exception(run, "split:" + "+".join(g["keys"]), "network", "possible_author_split",
                      f"可能同一人被拆成多個 id：{' / '.join(f'{n}（{k}，{c} 篇）' for n, k, c in zip(g['names'], g['keys'], g['counts']))}；合併後最多 {g['combined_n_max']} 篇，停 2 由本人決定")
    (run / "work" / "network.json").write_text(json.dumps(net, ensure_ascii=False, indent=2))
    (run / "work" / "author_lists.md").write_text(author_lists_md(works, st["author_id"], surname))

    ing = json.loads((run / "work" / "ingest.json").read_text()) if (run / "work" / "ingest.json").exists() else {}
    idx = load_index(run)
    d = run / "out" / "data"
    _csv(d / "works.csv", ["id", "year", "type", "kind", "venue", "doi", "target_position", "target_corresponding", "fulltext", "text_source", "n_authors", "topic", "field", "title"],
         [[w["id"], w["year"], w["type"], w["kind"], w.get("venue") or "", w.get("doi") or "", w.get("target_position") or "", w.get("target_corresponding"),
           idx.get(w["id"], {}).get("status", ""), ing.get(w["id"], {}).get("source_type", ""), len(w["authors"]),
           (w.get("topic") or {}).get("name") or "", (w.get("topic") or {}).get("field") or "", w["title"]] for w in sorted(works, key=lambda w: (w["year"], w["id"]))])
    _csv(d / "coauthors.csv", ["rank", "author_id", "name", "linked", "merged_names", "n_works", "as_first", "as_last", "as_corresponding", "years", "top_institution", "works"],
         [[i, s["key"], s["name"], s["linked"], "; ".join(s["merged_names"]), s["n"], s["as_first"], s["as_last"], s["as_corresponding"],
           " ".join(f"{y}:{c}" for y, c in s["years"].items()), s["institutions"][0][0] if s["institutions"] else "", " ".join(s["works"])]
          for i, s in zip(competition_ranks([s["n"] for s in stats]), stats)])
    for s in stats:
        if s["merged_names"]:
            add_exception(run, "merge:" + s["key"], "network", "name_merge",
                          f"{s['name']}（{s['key']}）併入沒有作者 id 的寫法：{'、'.join(s['merged_names'])}（姓氏＋名首字母唯一對應、ORCID 不衝突）")
    _csv(d / "topics.csv", ["level", "name", "n_works"], [[lvl, n, c] for lvl, items in net["topics"].items() for n, c in items])

    top = stats[:TOP]
    print(f"DONE {len(works)} 篇；合作者 {len(stats)} 人（有 id {net['coauthors_linked']}）；"
          f"本人第一作者 {net['roles']['first']}、最後作者 {net['roles']['last']}、通訊 {net['roles']['corresponding']}")
    for i, s in enumerate(top, 1):
        print(f"  {i}. {s['name']} ({s['key']}) {s['n']} 篇")
    for g in net["possible_splits"]:
        print(f"  可能同一人：{' / '.join(f'{n} {k} {c}篇' for n, k, c in zip(g['names'], g['keys'], g['counts']))}")


def check(run):
    net = json.loads((run / "work" / "network.json").read_text())
    cc = json.loads((run / "work" / "count-check.json").read_text())
    if cc.get("sections_read") != net["works_total"]:
        print(f"FAIL 覆蓋不足：計數者讀 {cc.get('sections_read')} 節，文章 {net['works_total']} 篇")
        sys.exit(1)
    agent = cc["counts"]
    diffs = compare_counts(net["coauthors"], agent, top=TOP, min_n=MIN_N)
    (run / "work" / "count-diff.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=2))
    if diffs:
        print(f"FAIL 不一致 {len(diffs)} 人：" + "; ".join(f"{d['key']} 腳本 {d['script']} / agent {d['agent']}" for d in diffs))
        sys.exit(1)
    print(f"PASS 計數一致（比對 {len(agent)} 人，門檻 ≥{MIN_N} 篇）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "check"])
    ap.add_argument("run")
    a = ap.parse_args()
    (build if a.cmd == "build" else check)(Path(a.run))


if __name__ == "__main__":
    main()
