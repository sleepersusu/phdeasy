"""ingest：盤點與標準化。

  uv run python scripts/ingest.py runs/<slug>

1. 雜湊檢查：work/hashes.json 記錄的 pdfs/ 檔案必須沒變；inbox/ 新檔補記雜湊。有變 → 熔斷。
2. 每篇轉成帶位置標記的文字 work/text/<id>.txt（PDF `[p.N]`、XML `[§N]`、摘要 `[abs]`）。
3. 讀不出字（掃描檔）、標題對不上（拿錯檔案）→ 隔離成例外，改用摘要。
4. 完整卡沒有全文 → `abstract_only` 例外；連摘要都沒有 → `no_source` 例外。
5. 寫 work/ingest.json；檢查熔斷。

可接續：ingest.json 已有且來源雜湊相同的不重做。
"""
import argparse
import hashlib
import json
from pathlib import Path

from pipeline.exceptions import add_exception, check_circuit, open_exceptions, resolve_exception
from pipeline.fetch import is_preprint_url, sha256_file
from pipeline.index import load_index
from pipeline.state import append_progress, load_state, set_stage
from pipeline.textify import abstract_to_marked, has_text, looks_like_supplement, pdf_to_marked, title_matches, units, xml_to_marked


RULES_VERSION = 6  # 驗證規則改了就加一，舊結果會重驗（2：附錄／檢核表偵測；3：還原 \x02 負號；4：無內容短卡只列標題；5：還原編成 $ 的小數點；6：預印本全文標 preprint_text）


def needs_redo(prev, src_hash, text_exists):
    return not (prev and prev.get("source_sha256") == src_hash and prev.get("rules") == RULES_VERSION and text_exists)


def verify_hashes(run, hashes, library=False):
    """原始檔沒有被改。紀錄的路徑一律用 /（Windows 寫的反斜線也改掉，Mac、Windows 輪流用才對得上）。
    library＝Meeting：本人刪掉的文獻（PDF 移到 _已刪除／）不算被改，直接不再檢查；內容真的變了照樣擋。"""
    for rel in [k for k in hashes if "\\" in k]:
        hashes.setdefault(rel.replace("\\", "/"), hashes[rel])
        del hashes[rel]
    changed = []
    for rel, h in list(hashes.items()):
        p = run / rel
        if library and not p.exists():
            del hashes[rel]
            continue
        moved = run / "pdfs" / "_rejected" / p.name
        if not p.exists() and moved.exists() and sha256_file(moved) == h:  # setup_fulltext.py --reject 移走的：跟著改路徑
            del hashes[rel]
            hashes[moved.relative_to(run).as_posix()] = h
            continue
        if not p.exists() or sha256_file(p) != h:
            changed.append(rel)
    for p in sorted((run / "inbox").glob("**/*")):
        if p.is_file():
            rel = p.relative_to(run).as_posix()
            hashes.setdefault(rel, sha256_file(p))
    return changed


def convert(run, w, row, library=False):
    """回傳 (文字, 來源類型, 例外清單[(kind, detail)])。
    library＝Meeting 文件：不一定是論文（指引、檢核表、報告）——表格留成表格，不檢查標題、不因為像附錄而隔離。"""
    exc = []
    if row.get("status") == "ok" and row.get("path"):
        src = run / row["path"]
        try:
            if row.get("ext") == "xml" or src.suffix == ".xml":
                text, _ = xml_to_marked(src.read_bytes())
                stype = "xml"
            else:
                text, _ = pdf_to_marked(src, tables=library, ocr=library)  # Meeting 文件：表格留成表格、掃描檔用 OCR 讀字
                stype = "pdf"
        except Exception as e:
            text, stype = "", None
            exc.append(("unreadable", f"{row['path']}：{type(e).__name__}: {e}"))
        if stype and not (has_text(text, min_chars=40) if library else has_text(text)):  # Meeting 文件可能只有一兩頁
            exc.append(("no_text", f"{row['path']} 抽不出文字（可能是掃描檔）"))
        elif stype and not library and looks_like_supplement(text):
            exc.append(("not_main_text", f"{row['path']} 看起來是附錄或檢核表，不是論文正文，已隔離"))
        elif stype and not library and not title_matches(text, w["title"]):
            exc.append(("title_mismatch", f"{row['path']} 前兩頁找不到文章標題，可能拿錯檔案，已隔離"))
        if not exc:
            if is_preprint_url(row.get("url")) and w.get("type") != "preprint":  # 判斷規則：正式版無全文時用預印本，標 preprint_text
                exc.append(("preprint_text", f"全文取自預印本（{row.get('url')}），可能與正式版不同"))
            return text, stype, exc
    if w.get("abstract"):
        if w["kind"] == "full":
            exc.append(("abstract_only", "沒有可用全文，只用摘要"))
        return abstract_to_marked(w["abstract"]), "abstract", exc
    if w["kind"] == "short":  # 會議摘要等無內容的短卡：只列標題，屬註記類（本人 2026-10-25 決定）
        exc.append(("title_only", "沒有全文也沒有摘要，只列標題"))
    else:
        exc.append(("no_source", "沒有全文也沒有摘要"))
    return "", "none", exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--limit", type=float, default=0.3)
    ap.add_argument("--library", action="store_true", help="Meeting 文件：不一定是論文，表格留成表格")
    args = ap.parse_args()
    run = Path(args.run)
    wd = run / "work"
    (wd / "text").mkdir(exist_ok=True)
    works = [w for w in json.loads((wd / "works.json").read_text()) if w.get("kind") != "title"]  # 只列標題的（不在必讀前五篇）不轉文字
    index = load_index(run)
    hashes_p = wd / "hashes.json"
    hashes = json.loads(hashes_p.read_text()) if hashes_p.exists() else {}

    changed = verify_hashes(run, hashes, library=args.library)
    hashes_p.write_text(json.dumps(hashes, ensure_ascii=False, indent=2))
    if changed:
        reason = f"原始檔雜湊改變：{', '.join(changed)}"
        set_stage(run, "halted", circuit={"tripped": True, "reason": reason})
        print(f"HALT {reason}")
        return
    st = load_state(run)
    if args.library and st.get("stage") == "halted" and str((st.get("circuit") or {}).get("reason") or "").startswith("原始檔雜湊改變"):
        st.update(stage="library", circuit={"tripped": False, "reason": None})  # 舊版因為刪檔誤停的：這次檢查過了，接著跑（library 不在流水線階段表）
        (run / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2))

    ing_p = wd / "ingest.json"
    ing = json.loads(ing_p.read_text()) if ing_p.exists() else {}
    counts = {}
    for w in works:
        row = index.get(w["id"], {})
        src_hash = row.get("sha256") or hashlib.sha256((w.get("abstract") or "").encode()).hexdigest()
        prev = ing.get(w["id"])
        if prev and prev.get("ocr") and (wd / "text" / f"{w['id']}.txt").exists():  # 掃描檔已由轉錄者轉好：不要蓋掉
            counts["pdf"] = counts.get("pdf", 0) + 1
            continue
        if not needs_redo(prev, src_hash, (wd / "text" / f"{w['id']}.txt").exists()):
            counts[prev["source_type"]] = counts.get(prev["source_type"], 0) + 1
            continue
        text, stype, exc = convert(run, w, row, library=args.library)
        header = f"# {w['id']} | {stype} | {w['title']}\n\n"
        (wd / "text" / f"{w['id']}.txt").write_text(header + text)
        now = {k for k, _ in exc}
        for e in open_exceptions(run):
            if e["id"] == w["id"] and e["stage"] == "ingest" and e["kind"] not in now:
                resolve_exception(run, w["id"], "ingest", e["kind"], f"重跑 ingest 後來源為 {stype}")
        for kind, detail in exc:
            add_exception(run, w["id"], "ingest", kind, detail)
        ing[w["id"]] = {
            "source_type": stype,
            "source_path": row.get("path") if stype in ("pdf", "xml") else None,
            "source_sha256": src_hash,
            "rules": RULES_VERSION,
            "units": units(text),
            "chars": len(text),
            "kind": w["kind"],
            "exceptions": [k for k, _ in exc],
        }
        counts[stype] = counts.get(stype, 0) + 1
        ing_p.write_text(json.dumps(ing, ensure_ascii=False, indent=2))
        print(f"  {w['id']} {stype} units={units(text)} {' '.join(k for k, _ in exc)}", flush=True)

    ing_p.write_text(json.dumps(ing, ensure_ascii=False, indent=2))
    missing = [w["id"] for w in works if w["id"] not in ing]
    summary = f"{len(works)} 篇 → 文字 {len(ing)}（{counts}）；覆蓋缺 {len(missing)}；未解決例外 {len(open_exceptions(run))} 筆"
    append_progress(run, "ingest", summary)
    tripped, reason = check_circuit(run, total=len(works), limit=args.limit)
    if tripped:
        print(f"HALT {reason}")
        return
    if missing:
        print(f"BLOCKED 覆蓋不足：{missing}")
        return
    print(f"DONE {summary}")


if __name__ == "__main__":
    main()
