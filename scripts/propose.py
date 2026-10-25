"""prof-propose：每位目標教授一份研究構想草稿（依本人 CV 與教授目前期間內的經費）。

  uv run python scripts/propose.py inputs runs/<slug>     # → work/proposal/inputs.json（擬稿者讀這個）
  uv run python scripts/propose.py check runs/<slug>      # 核對 work/proposal/draft.json；有錯 exit 1
  uv run python scripts/propose.py assemble runs/<slug>   # → out/proposal.json（教授頁「研究構想草稿」讀它）
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.export import paper_dir_name
from pipeline.propose import active_grants, check_proposal, fingerprint
from pipeline.state import append_progress


def _j(p, d=None):
    return json.loads(p.read_text()) if p.exists() else d


def load(run):
    me = _j(run.parent / "_me" / "me.json") or {}
    works = _j(run / "work" / "works.json", [])
    grants = _j(run / "work" / "grants" / "grants_final.json", []) or []
    act = active_grants(grants)
    return me, works, grants, act


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["inputs", "check", "assemble"])
    ap.add_argument("run")
    a = ap.parse_args()
    run = Path(a.run)
    pd = run / "work" / "proposal"
    pd.mkdir(parents=True, exist_ok=True)
    me, works, grants, act = load(run)
    if a.cmd == "inputs":
        match = _j(run / "out" / "match.json") or {}
        papers = []
        for w in sorted(works, key=lambda w: -(w.get("year") or 0)):
            dg = _j(run / "out" / "papers" / paper_dir_name(w) / "重點.json") or {}
            kp = [k.get("en") for k in dg.get("key_points") or []]
            papers.append({"id": w["id"], "year": w.get("year"), "title": w.get("title"), "role": w.get("target_position"),
                           "key_points": kp[:4] or [(w.get("abstract") or "")[:600]]})
        cv = {k: me.get(k) for k in ("name", "headline", "summary", "interests", "education", "publications", "projects", "capabilities")}
        (pd / "inputs.json").write_text(json.dumps({"today": datetime.now().date().isoformat(), "me_cv": cv,
                                                   "joint_proposal_with_this_professor": me.get("proposal") if me.get("proposal_with") == run.name else None,
                                                   "active_grants": act, "recommend": match, "papers": papers}, ensure_ascii=False, indent=1))
        print(f"DONE 目前期間內的經費 {len(act)} 筆；文章 {len(papers)} 篇" + ("" if act else "（沒有期間內的經費：構想要寫明經費來源不明）"))
        return
    d = _j(pd / "draft.json")
    if d is None:
        print("BLOCKED 沒有 work/proposal/draft.json")
        sys.exit(1)
    fails = check_proposal(d, {w["id"] for w in works}, {g["key"] for g in act})
    if a.cmd == "check":
        for f in fails:
            print(f"FAIL {f['path']} {f['why']}")
        if fails:
            sys.exit(1)
        print("PASS 構想各段中英齊全、引用的文章與經費都存在且在期間內")
        return
    if fails:
        print(f"FAIL 還有 {len(fails)} 項沒過，先修好再組裝")
        sys.exit(1)
    out = {**d, "fingerprint": fingerprint(me, act), "built": datetime.now().astimezone().isoformat(timespec="seconds"),
           "active_grants": [{k: g[k] for k in ("key", "title", "funder", "status", "period")} for g in act]}
    (run / "out" / "proposal.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    append_progress(run, "propose", f"研究構想草稿：{(d.get('title') or {}).get('zh')}；對應經費 {', '.join((d.get('funding') or {}).get('refs') or [])}")
    print("DONE out/proposal.json")


if __name__ == "__main__":
    main()
