"""停 1 本人決定範圍後套用到 work/works.json。

  uv run python scripts/apply_scope.py runs/<slug> --lead   # 只有本人主導（第一／最後／通訊作者）的做完整卡
"""
import argparse
import json
from pathlib import Path

from pipeline.works import apply_lead_scope


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--lead", action="store_true")
    a = ap.parse_args()
    p = Path(a.run) / "work" / "works.json"
    works = json.loads(p.read_text())
    if a.lead:
        apply_lead_scope(works)
    p.write_text(json.dumps(works, ensure_ascii=False, indent=2))
    full = sum(w["kind"] == "full" for w in works)
    not_led = sum(w.get("short_reason") == "not_led" for w in works)
    print(f"DONE {len(works)} 篇：完整卡 {full}、短卡 {len(works) - full}（其中非主導 {not_led}）")


if __name__ == "__main__":
    main()
