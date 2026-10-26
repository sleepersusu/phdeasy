"""必讀前五篇：只有這幾篇走完整流程，其他文章只列標題。

  uv run python scripts/focus.py inputs runs/<slug> [--n 5]   # 寫 work/focus/inputs.json（本人的興趣與 CV＋每篇標題、摘要）給挑選者
  uv run python scripts/focus.py check  runs/<slug> [--n 5]   # 核對挑選者寫的 work/focus/draft.json
  uv run python scripts/focus.py apply  runs/<slug> [--ids W1,W2,...]   # 套用（不給 --ids 就用 draft.json）；停 1 本人換篇也用這個

套用後 work/focus.json 記下哪幾篇與理由；works.json 其他文章 kind 改成 "title"（原本的種類記在 kind_orig）。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.focus import apply_focus, check_picks

ME = Path(__file__).resolve().parent.parent / "runs" / "_me" / "me.json"


def _me():
    """本人的研究興趣與 CV（不含與教授共同討論的研究計畫）。"""
    m = json.loads(ME.read_text()) if ME.exists() else {}
    return {"interests": [i.get("en") or i.get("zh") for i in m.get("interests") or []],
            "capabilities": [{"area": c.get("area"), "items": c.get("items")} for c in m.get("capabilities") or []],
            "experience": [{"role": e.get("role"), "org": e.get("org"), "skills": e.get("skills"),
                            "bullets": [b.get("en") for b in e.get("bullets") or []]} for e in m.get("experience") or []],
            "summary": m.get("summary")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["inputs", "check", "apply"])
    ap.add_argument("run")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--ids", default="")
    a = ap.parse_args(argv)
    run = Path(a.run)
    wp = run / "work" / "works.json"
    works = json.loads(wp.read_text())
    fd = run / "work" / "focus"
    fd.mkdir(parents=True, exist_ok=True)
    if a.cmd == "inputs":
        rows = [{"id": w["id"], "year": w.get("year"), "type": w.get("type"), "venue": w.get("venue"), "title": w.get("title"),
                 "abstract": (w.get("abstract") or "")[:2000], "position": w.get("target_position")} for w in works]
        (fd / "inputs.json").write_text(json.dumps({"n": min(a.n, len(works)), "me": _me(), "works": rows}, ensure_ascii=False, indent=1))
        print(f"DONE 挑選輸入：{len(rows)} 篇，要挑 {min(a.n, len(works))} 篇")
        return 0
    if a.cmd == "check":
        picks = json.loads((fd / "draft.json").read_text()).get("picks") or []
        fails = check_picks(picks, works, a.n)
        for f in fails:
            print(f"FAIL {f['where']} {f['why']} {f.get('detail', '')}")
        print("PASS" if not fails else f"{len(fails)} 個問題")
        return 1 if fails else 0
    if a.ids:
        ids = [i.strip() for i in a.ids.split(",") if i.strip()]
        old = json.loads((run / "work" / "focus.json").read_text()) if (run / "work" / "focus.json").exists() else {}
        reasons = {p["id"]: p for p in (old.get("picks") or [])}
        draft = json.loads((fd / "draft.json").read_text()) if (fd / "draft.json").exists() else {}
        reasons.update({p["id"]: p for p in draft.get("picks") or []})
        picks = [reasons.get(i) or {"id": i, "reason": "本人在停 1 指定", "quote": None} for i in ids]
    else:
        picks = json.loads((fd / "draft.json").read_text()).get("picks") or []
        fails = check_picks(picks, works, a.n)
        if fails:
            print("FAIL 挑選沒過核對，先跑 check 修好")
            return 1
        ids = [p["id"] for p in picks]
    try:
        apply_focus(works, ids)
    except ValueError as e:
        print(f"FAIL {e}")
        return 1
    wp.write_text(json.dumps(works, ensure_ascii=False, indent=2))
    (run / "work" / "focus.json").write_text(json.dumps({"ids": ids, "picks": picks, "applied": datetime.now().astimezone().isoformat(timespec="seconds")},
                                                        ensure_ascii=False, indent=1))
    print(f"DONE 必讀 {len(ids)} 篇（{', '.join(ids)}）；其他 {len(works) - len(ids)} 篇只列標題")
    return 0


if __name__ == "__main__":
    sys.exit(main())
