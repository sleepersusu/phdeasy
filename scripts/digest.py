"""每篇的 AI 重點（中英）與圖表說明。

  uv run python scripts/digest.py todo runs/<slug>                 # 列出還沒寫重點的文章（有全文或摘要的）
  uv run python scripts/digest.py check runs/<slug> [--ids W1,W2]  # 核對 work/digest/<id>.json；有錯 exit 1
  uv run python scripts/digest.py assemble runs/<slug>             # → out/papers/<這篇的資料夾>/重點.json
  uv run python scripts/digest.py figures runs/<slug> [--ids W1]   # 每張圖表的圖檔絕對路徑與是否已有逐步解讀（給看圖解讀的 agent）
"""
import argparse
import json
import sys
from pathlib import Path

from pipeline.digest import assemble_digest, check_digest
from pipeline.export import paper_dir_name
from pipeline.state import append_progress


def _j(p, d=None):
    return json.loads(p.read_text()) if p.exists() else d


def _ctx(run):
    works = {w["id"]: w for w in _j(run / "work" / "works.json", []) if w.get("kind") != "title"}  # 只列標題的不整理
    ing = _j(run / "work" / "ingest.json", {})
    return works, ing


def _figs(run, wid):
    f = _j(run / "work" / "figures" / f"{wid}.json", {}) or {}
    return f.get("items") or []


def _text(run, wid):
    p = run / "work" / "text" / f"{wid}.txt"
    return p.read_text() if p.exists() else ""


def eligible(run):
    works, ing = _ctx(run)
    return [wid for wid in works if (ing.get(wid) or {}).get("source_type") in ("pdf", "xml", "abstract")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["todo", "check", "assemble", "figures"])
    ap.add_argument("run")
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()
    run = Path(a.run)
    dd = run / "work" / "digest"
    dd.mkdir(parents=True, exist_ok=True)
    ids = eligible(run)
    if a.cmd == "todo":
        left = [w for w in ids if not (dd / f"{w}.json").exists()]
        print(json.dumps([{"id": w, "figures": [f["label"] for f in _figs(run, w)]} for w in left], ensure_ascii=False))
        print(f"未完成 {len(left)}/{len(ids)}", file=sys.stderr)
        return
    if a.ids:
        ids = [w for w in ids if w in set(a.ids.split(","))]
    if a.cmd == "figures":
        rows = []
        for w in ids:
            dg = {f.get("label"): f for f in (_j(dd / f"{w}.json", {}) or {}).get("figures") or []}
            for f in _figs(run, w):
                img = (run / "out" / "site" / f["image"]).resolve() if f.get("image") else None
                rows.append({"id": w, "label": f["label"], "caption": f.get("caption"), "image": str(img) if img and img.exists() else None,
                             "table_html": bool(f.get("table_html")), "has_detail": bool((dg.get(f["label"]) or {}).get("detail"))})
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        left = [r for r in rows if not r["has_detail"] and (r["image"] or r["table_html"])]
        print(f"還沒有逐步解讀 {len(left)}/{len(rows)} 張（有圖檔或表格的）", file=sys.stderr)
        return
    if a.cmd == "check":
        total = 0
        for wid in ids:
            d = _j(dd / f"{wid}.json")
            if d is None:
                continue
            fails = check_digest(d, _text(run, wid), [f["label"] for f in _figs(run, wid)])
            for f in fails:
                print(f"FAIL {wid} {f['path']} {f['why']}" + (f"：\"{(f.get('quote') or '')[:60]}\" [{f.get('loc')}]" if f.get("quote") else ""))
            total += len(fails)
        if total:
            print(f"FAIL 共 {total} 項")
            sys.exit(1)
        print("PASS 重點與圖表說明都核對通過（圖表無遺漏、引句在原文、中英數字一致）")
        return
    works, _ = _ctx(run)
    n, n_fig, n_rej = 0, 0, 0
    for wid in ids:
        d = _j(dd / f"{wid}.json")
        if d is None:
            continue
        figs = _figs(run, wid)
        out, rej = assemble_digest(d, _text(run, wid), [f["label"] for f in figs], figs)
        folder = run / "out" / "papers" / paper_dir_name(works[wid])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "重點.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        n += 1
        n_fig += len(out["figures"])
        n_rej += len(rej)
    summary = f"重點 {n}/{len(ids)} 篇；圖表 {n_fig} 張；核對不過拿掉 {n_rej} 條"
    append_progress(run, "digest", summary)
    print(f"DONE {summary}")


if __name__ == "__main__":
    main()
