"""prof-propose：每位目標教授的研究計畫書草稿，2–3 個方向各一版、附信心程度（依她的方向與期間內經費、本人的興趣與做得到的事）。

  uv run python scripts/propose.py inputs runs/<slug>     # → work/proposal/inputs.json（擬稿者讀這個）
  uv run python scripts/propose.py check runs/<slug>      # 核對 work/proposal/draft.json；有錯 exit 1
  uv run python scripts/propose.py assemble runs/<slug>   # → out/proposal.json（教授頁「研究計畫書」讀它；沒過核對的版本不放）
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.export import paper_dir_name
from pipeline.propose import finalized_with, active_grants, check_draft, check_version, fingerprint
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
    if finalized_with(me, run.name):
        print("SKIP 跟這位教授的計畫書已定案，不再擬 AI 版本")
        return
    if a.cmd == "inputs":
        match = _j(run / "out" / "match.json") or {}
        papers = []
        for w in sorted(works, key=lambda w: -(w.get("year") or 0)):
            dg = _j(run / "out" / "papers" / paper_dir_name(w) / "重點.json") or {}
            kp = [k.get("en") for k in dg.get("key_points") or []]
            papers.append({"id": w["id"], "year": w.get("year"), "title": w.get("title"), "role": w.get("target_position"),
                           "key_points": kp[:4] or [(w.get("abstract") or "")[:600]]})
        cv = {k: me.get(k) for k in ("name", "headline", "summary", "interests", "education", "publications", "projects", "capabilities")}
        joint = me.get("proposal") or {}
        (pd / "inputs.json").write_text(json.dumps({"today": datetime.now().date().isoformat(), "me_cv": cv,
                                                   # 分段與寫法的範本：本人與 Liliana 討論、她改過的計畫書（內容不是本人獨立的，不要搬到別的教授）
                                                   "template_sections": joint.get("document") or [],
                                                   "joint_proposal_with_this_professor": joint if me.get("proposal_with") == run.name else None,
                                                   "active_grants": act, "recommend": match, "papers": papers}, ensure_ascii=False, indent=1))
        print(f"DONE 目前期間內的經費 {len(act)} 筆；文章 {len(papers)} 篇" + ("" if act else "（沒有期間內的經費：構想要寫明經費來源不明）"))
        return
    d = _j(pd / "draft.json")
    if d is None:
        print("BLOCKED 沒有 work/proposal/draft.json")
        sys.exit(1)
    ids, active = {w["id"] for w in works}, {g["key"]: g for g in act}
    fails = check_draft(d, ids, active)
    if a.cmd == "check":
        for f in fails:
            print(f"FAIL {f['path']} {f['why']}")
        if fails:
            sys.exit(1)
        print(f"PASS {len(d['versions'])} 個版本各段中英齊全、引用的文章與經費都存在且在期間內、沒有誇大用詞")
        return
    keep, rejected = [], []
    for v in d.get("versions") or []:
        vf = check_version(v, ids, active)
        (rejected if vf else keep).append({**v, "fails": vf} if vf else v)
    if not keep:
        print(f"FAIL 沒有任何版本通過核對（{len(fails)} 項），不組裝")
        sys.exit(1)
    (pd / "rejected.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=1))
    out = {"versions": keep, "fingerprint": fingerprint(me, act), "built": datetime.now().astimezone().isoformat(timespec="seconds"),
           "active_grants": [{k: g[k] for k in ("key", "title", "funder", "status", "period")} for g in act]}
    (run / "out" / "proposal.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    append_progress(run, "propose", f"研究計畫書草稿 {len(keep)} 版（" + "、".join(f"{v['id']} {v['confidence']['level']}" for v in keep)
                    + f"）；沒過核對 {len(rejected)} 版")
    print(f"DONE out/proposal.json：{len(keep)} 版，拿掉 {len(rejected)} 版")


if __name__ == "__main__":
    main()
