"""cards：每篇文章的解析卡。

  uv run python scripts/cards.py todo runs/<slug>              # 每篇還缺哪一步（可接續）
  uv run python scripts/cards.py check runs/<slug> [--ids W1,W2]  # 甲的 a.json：格式＋引句＋數字核對 → check.json；有錯 exit 1
  uv run python scripts/cards.py diff runs/<slug>              # 甲 vs 乙的固定事實 → diff.json，列出要裁決的
  uv run python scripts/cards.py assemble runs/<slug>          # a＋judge＋refute → card.json；被移除的寫 out/rejected.md

工作檔：work/cards/<id>/{a.json, b.json, check.json, diff.json, judge.json, refute.json, card.json}
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.cards import apply_judge, apply_refute, assemble, check_card, diff_fixed, missing_refute_paths, validate_card
from pipeline.exceptions import add_exception, check_circuit
from pipeline.state import append_progress


def _works(run):
    return json.loads((run / "work" / "works.json").read_text())


def _text(run, wid):
    p = run / "work" / "text" / f"{wid}.txt"
    return p.read_text() if p.exists() else ""


def _j(p):
    return json.loads(p.read_text()) if p.exists() else None


def _cd(run, wid):
    d = run / "work" / "cards" / wid
    d.mkdir(parents=True, exist_ok=True)
    return d


def todo(run):
    rows = []
    for w in _works(run):
        d = run / "work" / "cards" / w["id"]
        has = {n: (d / f"{n}.json").exists() for n in ("a", "b", "check", "diff", "judge", "refute", "card")}
        chk = _j(d / "check.json") if has["check"] else None
        dif = _j(d / "diff.json") if has["diff"] else None
        need = []
        if not has["a"]:
            need.append("甲")
        if w["kind"] == "full" and not has["b"]:
            need.append("乙")
        if has["a"] and (not chk or chk.get("fails")):
            need.append("check")
        if dif and dif.get("diffs") and not has["judge"]:
            need.append("裁決")
        if w["kind"] == "full" and has["a"] and not has["refute"]:
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


def diff(run):
    need = []
    for w in _works(run):
        if w["kind"] != "full":
            continue
        d = run / "work" / "cards" / w["id"]
        a, b = _j(d / "a.json"), _j(d / "b.json")
        if a is None or b is None:
            continue
        ds = diff_fixed(a, b)
        (d / "diff.json").write_text(json.dumps({"diffs": ds}, ensure_ascii=False, indent=2))
        if ds:
            need.append(w["id"])
            for x in ds:
                print(f"DIFF {w['id']} {x['field']}：甲 {x['a']} ／ 乙 {x['b']}")
    print(f"DONE 需要裁決 {len(need)} 篇：{','.join(need)}")


def check_refute(run, ids=None):
    miss_all = {}
    for w in _works(run):
        if ids and w["id"] not in ids:
            continue
        d = run / "work" / "cards" / w["id"]
        a, r = _j(d / "a.json"), _j(d / "refute.json")
        if w["kind"] != "full" or a is None:
            continue
        miss = missing_refute_paths(a, (r or {}).get("verdicts", [])) if r else ["(沒有 refute.json)"]
        if miss:
            miss_all[w["id"]] = miss
            print(f"FAIL {w['id']} 漏判：{', '.join(miss)}")
    if miss_all:
        sys.exit(1)
    print("PASS 每條都有推翻判決")


def _rejected(run, title, reason, evidence):
    p = run / "out" / "rejected.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# 被推翻或核對不過的內容\n\n只追加不刪。每筆附理由與證據。\n\n")
    with open(p, "a") as f:
        f.write(f"## [cards] {title}\n\n- 時間：{datetime.now().astimezone().isoformat(timespec='seconds')}\n- 理由：{reason}\n- 內容：{json.dumps(evidence, ensure_ascii=False)}\n\n")


def assemble_all(run, limit=0.3):
    works = _works(run)
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
    ap.add_argument("cmd", choices=["todo", "check", "diff", "check-refute", "assemble"])
    ap.add_argument("run")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()
    run = Path(a.run)
    if a.cmd == "todo":
        todo(run)
    elif a.cmd == "check":
        check(run, set(a.ids.split(",")) if a.ids else None)
    elif a.cmd == "diff":
        diff(run)
    elif a.cmd == "check-refute":
        check_refute(run, set(a.ids.split(",")) if a.ids else None)
    else:
        assemble_all(run)


if __name__ == "__main__":
    main()
