"""network：合作者、作者序角色、領域分佈、年度分佈。

  uv run python scripts/network.py build runs/<slug>
      → work/network.json、work/author_lists.md、out/data/{works,coauthors,topics}.csv
  uv run python scripts/network.py check runs/<slug>
      → network.json 自我核對（篇數、文章清單、年度加總、排序），寫 work/network-check.json；不過時 exit 1
        （本人 2026-10-26 拿掉獨立計數 agent：合作者由作者 id 機械計算，重數同一份資料抓不到新錯）
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
    owner = json.loads((run / "work" / "owner_decisions.json").read_text()) if (run / "work" / "owner_decisions.json").exists() else {}
    aliases = owner.get("author_aliases") or {}
    keep_sep = [set(g) for g in owner.get("keep_separate") or []]
    stats = coauthor_stats(works, st["author_id"], surname, aliases=aliases)
    net = {
        "target": {"author_id": st["author_id"], "name": st["professor"]["name"]},
        "works_total": len(works),
        "roles": role_summary(works),
        "years": year_counts(works),
        "topics": topic_counts(works),
        "coauthors_total": len(stats),
        "coauthors_linked": sum(s["linked"] for s in stats),
        "possible_splits": [g for g in possible_splits(stats) if set(g["keys"]) not in keep_sep],
        "owner_decisions": owner,
        "coauthors": stats,
    }
    cut = stats[TOP - 1]["n"] if len(stats) >= TOP else 0
    rank_relevant = [g for g in net["possible_splits"] if g["combined_n_max"] >= cut]
    net["possible_splits_minor"] = len(net["possible_splits"]) - len(rank_relevant)
    net["possible_splits"] = rank_relevant  # 只有會改變前 10 名的才請本人決定；其他只記數量
    (run / "work" / "network.json").write_text(json.dumps(net, ensure_ascii=False, indent=2))
    for g in rank_relevant:
        add_exception(run, "split:" + "+".join(g["keys"]), "network", "possible_author_split",
                      f"可能同一人被拆成多個 id：{' / '.join(f'{n}（{k}，{c} 篇）' for n, k, c in zip(g['names'], g['keys'], g['counts']))}；合併後最多 {g['combined_n_max']} 篇，停 2 由本人決定")
    (run / "work" / "network.json").write_text(json.dumps(net, ensure_ascii=False, indent=2))
    (run / "work" / "author_lists.md").write_text(author_lists_md(works, st["author_id"], surname, aliases=aliases))

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
    if net.get("possible_splits_minor"):
        print(f"  另有 {net['possible_splits_minor']} 組可能同一人不影響前 {TOP} 名，只記數量")
    for g in net["possible_splits"]:
        print(f"  可能同一人：{' / '.join(f'{n} {k} {c}篇' for n, k, c in zip(g['names'], g['keys'], g['counts']))}")


def check(run):
    from pipeline.network import check_consistency
    net = json.loads((run / "work" / "network.json").read_text())
    works = json.loads((run / "work" / "works.json").read_text())
    fails = check_consistency(net, works)
    (run / "work" / "network-check.json").write_text(json.dumps(fails, ensure_ascii=False, indent=2))
    for f in fails:
        print(f"FAIL {f['key']} {f['why']}")
    if fails:
        sys.exit(1)
    print(f"PASS network.json 自我核對：{len(net['coauthors'])} 位合作者的篇數、文章清單、年度加總都對得上")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "check"])
    ap.add_argument("run")
    a = ap.parse_args()
    (build if a.cmd == "build" else check)(Path(a.run))


if __name__ == "__main__":
    main()
