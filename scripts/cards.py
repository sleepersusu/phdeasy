"""cards：每篇文章的解析卡。

  uv run python scripts/cards.py todo runs/<slug>              # 每篇還缺哪一步（可接續）
  uv run python scripts/cards.py check runs/<slug> [--ids W1,W2]  # 甲的 a.json：格式＋引句＋數字核對 → check.json；有錯 exit 1
  uv run python scripts/cards.py check-refute runs/<slug>      # 推翻者有沒有把推論類（研究缺口、推論的限制）逐條判完
  uv run python scripts/cards.py assemble runs/<slug>          # a＋refute（舊批次有 judge 也套用）→ card.json；被移除的寫 out/rejected.md

工作檔：work/cards/<id>/{a.json, check.json, refute.json, card.json}
本人 2026-10-26 精簡：拿掉乙（雙軌固定事實）與裁決者——設計與樣本數改由研究方法十部分逐字引句、腳本核對；
推翻只做全文完整卡的推論類欄位。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.cards import apply_judge, apply_refute, assemble, check_card, missing_refute_paths, needs_refute, refute_paths, title_only_card, validate_card
from pipeline.exceptions import add_exception, check_circuit
from pipeline.state import append_progress


def _works(run):
    """要寫解析卡的文章：只列標題的（不在必讀前五篇）不寫。"""
    return [w for w in json.loads((run / "work" / "works.json").read_text()) if w.get("kind") != "title"]


def _text(run, wid):
    p = run / "work" / "text" / f"{wid}.txt"
    return p.read_text() if p.exists() else ""


def _j(p):
    return json.loads(p.read_text()) if p.exists() else None


def _cd(run, wid):
    d = run / "work" / "cards" / wid
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_title_only(run):
    """ingest 判為無內容（title_only）的短卡由腳本產生，不派 agent。"""
    ing = _j(run / "work" / "ingest.json") or {}
    n = 0
    for w in _works(run):
        e = ing.get(w["id"]) or {}
        d = run / "work" / "cards" / w["id"]
        if "title_only" in (e.get("exceptions") or []) and not (d / "a.json").exists():
            _cd(run, w["id"])
            (d / "a.json").write_text(json.dumps(title_only_card(w["id"]), ensure_ascii=False, indent=2))
            n += 1
    return n


def todo(run):
    write_title_only(run)
    src = {k: v.get("source_type") for k, v in (_j(run / "work" / "ingest.json") or {}).items()}
    rows = []
    for w in _works(run):
        d = run / "work" / "cards" / w["id"]
        has = {n: (d / f"{n}.json").exists() for n in ("a", "check", "refute", "card")}
        chk = _j(d / "check.json") if has["check"] else None
        need = []
        if not has["a"]:
            need.append("甲")
        if has["a"] and (not chk or chk.get("fails")):
            need.append("check")
        if has["a"] and not has["refute"] and needs_refute(w, src.get(w["id"])) and refute_paths(_j(d / "a.json")):
            need.append("推翻")
        if not has["card"]:
            need.append("組裝")
        rows.append({"id": w["id"], "kind": w["kind"], "need": need})
    print(json.dumps(rows, ensure_ascii=False))
    left = [r for r in rows if r["need"]]
    print(f"未完成 {len(left)}/{len(rows)}", file=sys.stderr)


def check(run, ids=None):
    kinds = {w["id"]: w["kind"] for w in _works(run)}
    total_fail, n = 0, 0
    for wid, kind in kinds.items():
        if ids and wid not in ids:
            continue
        d = run / "work" / "cards" / wid
        a = _j(d / "a.json")
        if a is None:
            continue
        n += 1
        errs = validate_card(a, kind)
        fails = [] if errs else check_card(a, _text(run, wid))
        if errs:
            fails = [{"path": "schema", "why": e} for e in errs]
        out = {"schema_errors": errs, "fails": [{k: v for k, v in f.items() if k in ("path", "why", "quote", "loc")} for f in fails]}
        (d / "check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
        for f in out["fails"]:
            print(f"FAIL {wid} {f['path']} {f['why']}" + (f"：\"{(f.get('quote') or '')[:70]}\" [{f.get('loc')}]" if f.get("quote") else ""))
        total_fail += len(out["fails"])
    if total_fail:
        print(f"FAIL 共 {total_fail} 項（{n} 篇）")
        sys.exit(1)
    print(f"PASS {n} 篇全數通過（格式、引句、數字）")


def check_refute(run, ids=None):
    miss_all = {}
    src = {k: v.get("source_type") for k, v in (_j(run / "work" / "ingest.json") or {}).items()}
    for w in _works(run):
        if ids and w["id"] not in ids:
            continue
        d = run / "work" / "cards" / w["id"]
        a, r = _j(d / "a.json"), _j(d / "refute.json")
        if a is None or not needs_refute(w, src.get(w["id"])) or not refute_paths(a):
            continue
        miss = missing_refute_paths(a, (r or {}).get("verdicts", [])) if r else ["(沒有 refute.json)"]
        if miss:
            miss_all[w["id"]] = miss
            print(f"FAIL {w['id']} 漏判：{', '.join(miss)}")
    if miss_all:
        sys.exit(1)
    print("PASS 推論類（研究缺口、推論的限制）每條都有推翻判決")


def _rejected(run, title, reason, evidence):
    p = run / "out" / "rejected.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# 被推翻或核對不過的內容\n\n只追加不刪。每筆附理由與證據。\n\n")
    with open(p, "a") as f:
        f.write(f"## [cards] {title}\n\n- 時間：{datetime.now().astimezone().isoformat(timespec='seconds')}\n- 理由：{reason}\n- 內容：{json.dumps(evidence, ensure_ascii=False)}\n\n")


def assemble_all(run, limit=0.3):
    works = _works(run)
    ing = _j(run / "work" / "ingest.json") or {}
    done, missing, n_rej, n_unres = 0, [], 0, 0
    for w in works:
        d = run / "work" / "cards" / w["id"]
        a = _j(d / "a.json")
        if a is None:
            missing.append(w["id"])
            continue
        card = a
        unresolved = []
        judge = _j(d / "judge.json")
        if judge:
            card, unresolved = apply_judge(card, judge.get("judgments", []))
        rej_refute = []
        ref = _j(d / "refute.json")
        if ref:
            card, rej_refute = apply_refute(card, ref.get("verdicts", []))
        card, rej_check = assemble(card, _text(run, w["id"]))
        card["preprint_text"] = "preprint_text" in ((ing.get(w["id"]) or {}).get("exceptions") or [])
        card["kind"], card["verified"] = w["kind"], {"judged": bool(judge), "refuted": bool(ref), "dual_track": (d / "b.json").exists()}
        (d / "card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2))
        stamp = d / ".rejected_logged"
        if not stamp.exists():
            for r in rej_refute:
                _rejected(run, f"{w['id']} {r['path']}", f"推翻者：{r.get('reason')}", r.get("item"))
            for r in rej_check:
                _rejected(run, f"{w['id']} {r['path']}", f"核對不過：{r['why']}", r.get("item"))
            stamp.write_text("")
        n_rej += len(rej_refute) + len(rej_check)
        for f in unresolved:
            add_exception(run, w["id"], "cards", "dual_track_unresolved", f"{f}：雙軌不一致，裁決者也判不出來")
            n_unres += 1
        for f in [k for k, v in card["fields"].items() if v.get("status") == "unresolved" and k not in [u.split(".")[0] for u in unresolved]]:
            add_exception(run, w["id"], "cards", "field_unresolved", f"{f}：出處核對未通過，欄位改為判不出來")
            n_unres += 1
        done += 1
    for wid in missing:
        add_exception(run, wid, "cards", "no_card", "沒有產出解析卡")
    summary = f"解析卡 {done}/{len(works)}；移除說法或出處 {n_rej}；判不出來 {n_unres}"
    append_progress(run, "cards", summary)
    tripped, reason = check_circuit(run, total=len(works), limit=limit)
    if tripped:
        print(f"HALT {reason}")
        sys.exit(2)
    if missing:
        print(f"BLOCKED 缺卡：{missing}")
        sys.exit(1)
    print(f"DONE {summary}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["todo", "check", "check-refute", "assemble"])
    ap.add_argument("run")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()
    run = Path(a.run)
    if a.cmd == "todo":
        todo(run)
    elif a.cmd == "check":
        check(run, set(a.ids.split(",")) if a.ids else None)
    elif a.cmd == "check-refute":
        check_refute(run, set(a.ids.split(",")) if a.ids else None)
    else:
        assemble_all(run)


if __name__ == "__main__":
    main()
