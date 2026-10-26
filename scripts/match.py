"""prof-match：依本人的研究興趣與研究計畫，推薦該先看教授的哪幾篇文章、哪個計畫。

  uv run python scripts/match.py inputs runs/<slug>        # 寫 work/match/inputs.json（比對者讀這個）
  uv run python scripts/match.py check runs/<slug>         # 核對 work/match/draft.json；有錯 exit 1
  uv run python scripts/match.py check-refute runs/<slug>  # 推翻者每筆都判了沒
  uv run python scripts/match.py assemble runs/<slug>      # 套用推翻 → out/match.json（前端首頁讀它）
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.match import prefill_from_focus, assemble, build_inputs, check_draft, me_fingerprint, missing_verdicts
from pipeline.state import append_progress


def _j(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _load(run):
    wd = run / "work"
    me = _j(run.parent / "_me" / "me.json")
    if not me:
        print("BLOCKED 沒有本人資料 runs/_me/me.json")
        sys.exit(1)
    works = _j(wd / "works.json", [])
    cards = {w["id"]: _j(wd / "cards" / w["id"] / "card.json") for w in works}
    grants = _j(wd / "grants" / "grants_final.json", []) or _j(wd / "grants" / "grants.json", [])
    return me, build_inputs(me, works, {k: v for k, v in cards.items() if v}, grants)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["inputs", "check", "check-refute", "assemble"])
    ap.add_argument("run")
    a = ap.parse_args()
    run = Path(a.run)
    md = run / "work" / "match"
    md.mkdir(parents=True, exist_ok=True)
    me, inputs = _load(run)
    focus = _j(run / "work" / "focus.json")
    prefill = prefill_from_focus(focus, inputs)  # 必讀五篇已標對到哪些興趣：文章由腳本帶入，比對者只判經費與適合度，不派推翻者
    if a.cmd == "inputs":
        (md / "inputs.json").write_text(json.dumps({**inputs, "me_summary": me.get("summary"),
                                                     "papers_from_focus": prefill}, ensure_ascii=False, indent=1))
        print(f"DONE 比對對象 {len(inputs['targets'])}（興趣＋CV）；文章 {len(inputs['papers'])}；計畫 {len(inputs['grants'])}")
        return
    draft = _j(md / "draft.json")
    if draft is None:
        print("BLOCKED 沒有 work/match/draft.json")
        sys.exit(1)
    if a.cmd == "check":
        fails = check_draft(draft, inputs, prefill=prefill)
        (md / "check.json").write_text(json.dumps(fails, ensure_ascii=False, indent=2))
        for f in fails:
            print(f"FAIL {f['path']} {f['why']}")
        if fails:
            sys.exit(1)
        print(f"PASS 推薦 {sum(len(t.get('papers') or []) + len(t.get('grants') or []) for t in draft['targets'])} 筆都指到真的文章／計畫，理由都引得到原文")
        return
    verdicts = (_j(md / "refute.json") or {}).get("verdicts", [])
    miss = [] if prefill is not None else missing_verdicts(draft, verdicts)  # 新流程沒有推翻者
    if a.cmd == "check-refute":
        if miss:
            print("FAIL 推翻者漏判：" + ", ".join(miss))
            sys.exit(1)
        print("PASS 每筆推薦都有推翻判決")
        return
    if miss:
        print("FAIL 推翻者漏判：" + ", ".join(miss))
        sys.exit(1)
    final, rejected = assemble(draft, verdicts, inputs, fp=me_fingerprint(me), prefill=prefill,
                               read_first=(focus or {}).get("ids") if prefill is not None else None)
    final["built"] = datetime.now().astimezone().isoformat(timespec="seconds")
    (run / "out").mkdir(exist_ok=True)
    (run / "out" / "match.json").write_text(json.dumps(final, ensure_ascii=False, indent=1))
    if rejected:
        with open(run / "out" / "rejected.md", "a") as f:
            for r in rejected:
                f.write(f"## [match] {r['path']}\n\n- 理由：{r['reason']}\n- 內容：{json.dumps(r['item'], ensure_ascii=False)}\n\n")
    n = sum(len(t["papers"]) + len(t["grants"]) for t in final["targets"])
    fit = {k: sum(t["fit"] == k for t in final["targets"]) for k in ("strong", "partial", "none")}
    summary = f"比對 {len(final['targets'])} 項（強 {fit['strong']}／部分 {fit['partial']}／無 {fit['none']}）；推薦 {n} 筆，推翻 {len(rejected)}；先看 {len(final['read_first'])} 篇"
    append_progress(run, "match", summary)
    print(f"DONE {summary}")


if __name__ == "__main__":
    main()
