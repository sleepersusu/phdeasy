"""i18n：雙語翻譯核對。

  uv run python scripts/i18n.py check runs/<slug> [--ids W1,W2]   # 卡片翻譯：條數、數字、空白、關鍵詞
  uv run python scripts/i18n.py check-grants runs/<slug>          # 計畫翻譯：標題數字、摘要數字不得超出原始摘要
有錯 exit 1。
"""
import argparse
import json
import sys
from pathlib import Path

from pipeline.i18n import check_card_i18n, check_grants_i18n


def check(run, ids=None):
    works = json.loads((run / "work" / "works.json").read_text())
    total, missing = 0, []
    for w in works:
        if (ids and w["id"] not in ids) or w.get("kind") == "title":  # 只列標題的（不在必讀）沒有解析卡
            continue
        d = run / "work" / "cards" / w["id"]
        card = json.loads((d / "card.json").read_text())
        p = d / "i18n.json"
        if not p.exists():
            missing.append(w["id"])
            continue
        fails = check_card_i18n(card, json.loads(p.read_text()))
        for f in fails:
            print(f"FAIL {w['id']} {f['path']} {f['why']}")
        total += len(fails)
    if missing:
        print(f"FAIL 缺翻譯 {len(missing)} 篇：{','.join(missing)}")
    if total or missing:
        sys.exit(1)
    print("PASS 卡片翻譯全數通過（條數、數字、關鍵詞）")


def check_grants(run):
    grants = json.loads((run / "work" / "grants" / "grants_final.json").read_text())
    p = run / "work" / "grants" / "i18n.json"
    tr = json.loads(p.read_text()) if p.exists() else {}
    fails = check_grants_i18n(grants, tr)
    for f in fails:
        print(f"FAIL {f['key']} {f['why']}")
    if fails:
        sys.exit(1)
    print(f"PASS 計畫翻譯 {len(grants)} 筆全數通過")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "check-grants"])
    ap.add_argument("run")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()
    run = Path(a.run)
    if a.cmd == "check":
        check(run, set(a.ids.split(",")) if a.ids else None)
    else:
        check_grants(run)


if __name__ == "__main__":
    main()
