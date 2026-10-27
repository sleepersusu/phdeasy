"""討論文獻（教授頁「討論文獻」）：教授丟給本人的文獻，跟她的文章走同一套處理。

  uv run python scripts/library.py add-doi runs/<slug> --doi 10.2196/xxx [--given-by Liliana] [--discussion 2026-11-03] [--note …] [--source zotero]
  uv run python scripts/library.py add-pdf runs/<slug> --pdf runs/<slug>/library/inbox/<上傳的檔> [--given-by …] [--discussion …]
  uv run python scripts/library.py process runs/<slug>      # 找全文 → 轉文字 → 抓圖表 → 列出待寫重點（AI 重點由 prof-library 派 agent）
  uv run python scripts/library.py zotero runs/<slug> [--collection KEY]   # 讀本機 Zotero（唯讀）：列資料夾或資料夾裡的文獻
  uv run python scripts/library.py ris runs/<slug>          # → library/out/zotero/library.ris（本人自己匯入 Zotero）
  uv run python scripts/library.py draft-inputs runs/<slug> --ids W1,L2   # 勾選擬初稿 → drafts/<id>/inputs.json
  uv run python scripts/library.py draft-check runs/<slug> --draft <id>
  uv run python scripts/library.py draft-assemble runs/<slug> --draft <id>

runs/<slug>/library/ 的結構跟教授批次一樣，所以 setup_fulltext.py、ingest.py、figures.py、digest.py 都直接對它跑。
"""
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pipeline.export import paper_dir_name
from pipeline.http import get_json, openalex_params
from pipeline.library import check_lib_draft, doi_from_text, parse_zotero_items, pick_title_hit, ris_export, tag_item, title_guess
from pipeline.propose import active_grants
from pipeline.state import append_progress, init_run, load_state
from pipeline.works import normalize_work

ZOTERO = "http://127.0.0.1:23119/api/users/0"
SCRIPTS = Path(__file__).resolve().parent


def _j(p, d=None):
    return json.loads(p.read_text()) if p.exists() else d


def lib_dir(run):
    lib = run / "library"
    if not (lib / "state.json").exists():
        st = load_state(run)
        init_run(lib, professor=st["professor"])
        s = load_state(lib)
        s.update({"stage": "library", "author_id": st.get("author_id")})
        (lib / "state.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
    (lib / "work").mkdir(exist_ok=True)
    (lib / "inbox").mkdir(exist_ok=True)
    if not (lib / "work" / "works.json").exists():
        (lib / "work" / "works.json").write_text("[]")
    return lib


@contextlib.contextmanager
def _works_lock(lib, timeout=120):
    """寫 works.json 時的跨程序鎖：很多篇同時加（各一個程序）時，查資料一起跑、寫清單輪流，一篇都不會被蓋掉。"""
    p = lib / "work" / ".works.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p, "a+")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("清單一直被別的加入佔著") from None
                time.sleep(0.05)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def _append(lib, w):
    """鎖住、重新讀清單、沒有同一篇（同 id 或同 DOI）才加；回傳清單裡那一篇。"""
    with _works_lock(lib):
        works = _load(lib)
        old = next((x for x in works if x["id"] == w["id"] or (w.get("doi") and x.get("doi") == w.get("doi"))), None)
        if old:
            return old
        _save(lib, works + [w])
        return w


def _load(lib):
    return json.loads((lib / "work" / "works.json").read_text())


def _save(lib, works):
    seen, out = set(), []
    for w in works:  # 同一篇只留一筆（舊版在 Windows 重試會重複加）
        if w["id"] not in seen:
            seen.add(w["id"])
            out.append(w)
    p = lib / "work" / "works.json"
    tmp = p.with_name(f".works.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    os.replace(tmp, p)  # 一次換掉：別人同時讀不會讀到寫一半的檔


def _meta(a):
    return dict(given_by=a.given_by, discussion=a.discussion, note=a.note, today=datetime.now().date().isoformat())


def add_doi(lib, doi, source, **meta):
    from setup_list_works import SELECT
    works = json.loads((lib / "work" / "works.json").read_text())
    doi = doi.strip().lower().removeprefix("https://doi.org/")
    if any(w.get("doi") == doi for w in works):
        print(f"SKIP {doi} 已在討論文獻")
        return None
    raw = get_json(f"https://api.openalex.org/works/doi:{quote(doi)}?select={SELECT}{openalex_params()}")
    w = _append(lib, tag_item(normalize_work(raw, load_state(lib).get("author_id")), source=source, **meta))
    print(f"ADD {w['id']} {w.get('year')} {w['title'][:70]}")
    return w


def _pdf_head(pdf):
    """PDF 前兩頁的字與檔案資訊的標題；讀完馬上關掉（Windows 不能改名還開著的檔案）。"""
    import pymupdf
    with pymupdf.open(pdf) as doc:
        return "\n".join(doc[i].get_text() for i in range(min(2, doc.page_count))), (doc.metadata or {}).get("title")


def _move_to(pdf, dest):
    """改成帶文章 id 的檔名；Windows 不准改名（檔案被別的程式開著，例如雲端硬碟正在同步）就複製一份。"""
    if pdf.resolve() == dest.resolve():
        return
    try:
        pdf.rename(dest)
    except OSError:
        import shutil
        shutil.copyfile(pdf, dest)


def _find(works, doi, h):
    return next((x for x in works if (doi and x.get("doi") == doi) or x["id"] == f"L{h}"), None)


def add_pdf(lib, pdf, **meta):
    pdf = Path(pdf)
    head, meta_title = _pdf_head(pdf)
    doi = doi_from_text(head)
    h = hashlib.sha256(pdf.read_bytes()).hexdigest()[:8]
    old = _find(_load(lib), doi, h)
    if old:  # 同一個檔（或同一個 DOI）重傳：不再多加一筆，只把檔案對上
        print(f"SKIP {old['id']} 已在 Meeting 文獻")
        _move_to(pdf, lib / "inbox" / f"{old['id']}_{pdf.name}")
        return old
    w = None
    if doi:
        try:
            w = add_doi(lib, doi, "pdf", **meta)
        except RuntimeError as e:
            print(f"WARN OpenAlex 查不到 {doi}（{e}），改用 PDF 本身的標題")
    guess = title_guess(meta_title, head, pdf.stem)
    if w is None and not doi and len(head.strip()) >= 200:  # 沒有 DOI：用 PDF 的標題查 OpenAlex，標題字詞對得上第一頁才採用；掃描檔沒字就不查
        try:
            hits = get_json(f"https://api.openalex.org/works?search={quote(guess[:200])}&per-page=3{openalex_params()}").get("results") or []
        except RuntimeError:
            hits = []
        hit = pick_title_hit(head, hits)
        if hit:
            w = add_doi(lib, hit["doi"], "pdf", **meta)
    if w is None:
        works = json.loads((lib / "work" / "works.json").read_text())
        if doi and any(x.get("doi") == doi for x in works):
            w = next(x for x in works if x.get("doi") == doi)
        else:
            title = guess
            w = _append(lib, tag_item({"id": f"L{h}", "title": title, "year": None, "type": "article", "doi": doi, "authors": [], "abstract": None,
                                       "venue": None}, source="pdf", **meta))
            print(f"ADD {w['id']}（沒有 DOI，標題取自 PDF）{title[:70]}")
    _move_to(pdf, lib / "inbox" / f"{w['id']}_{pdf.name}")  # 檔名帶文章 id，找全文時 inbox 一定對得上
    return w


def relink_uploads(lib):
    """舊版在 Windows 加進去了、但改名失敗留下的 _upload_*.pdf：用 DOI 或檔案雜湊對回文章，補上帶 id 的檔名。回傳對上幾個。"""
    works, n = _load(lib), 0
    for pdf in sorted((lib / "inbox").glob("_upload_*.pdf")):
        try:
            head, _ = _pdf_head(pdf)
        except Exception:
            continue
        w = _find(works, doi_from_text(head), hashlib.sha256(pdf.read_bytes()).hexdigest()[:8])
        if w and not any((lib / "inbox").glob(f"{w['id']}_*{pdf.name}")):
            try:
                _move_to(pdf, lib / "inbox" / f"{w['id']}_{pdf.name}")
                n += 1
            except OSError:  # 同時加的另一篇已經把它搬走
                pass
    if n:
        print(f"DONE 對回 {n} 個之前沒改到檔名的上傳檔")
    return n


def run_step(*args):
    r = subprocess.run([sys.executable, *map(str, args)], cwd=SCRIPTS.parent)
    if r.returncode:
        sys.exit(r.returncode)


def process(lib):
    relink_uploads(lib)
    with _works_lock(lib):
        _save(lib, _load(lib))  # 清掉舊版留下的重複
    run_step(SCRIPTS / "setup_fulltext.py", lib)
    run_step(SCRIPTS / "ingest.py", lib, "--library")
    todo = ocr_todo(lib)
    if todo:  # 掃描檔：交給轉錄者（skill A 段）
        print(f"OCR {len(todo)} 份掃描檔要轉錄：{','.join(t['id'] for t in todo)}")
    run_step(SCRIPTS / "figures.py", "extract", lib)
    run_step(SCRIPTS / "digest.py", "todo", lib)


def ocr_todo(lib):
    """抽不出字的 PDF（掃描檔）：列出來給轉錄者一頁一頁看圖轉成文字。已經轉好的不列。"""
    import pymupdf
    from pipeline.index import load_index
    ing = _j(lib / "work" / "ingest.json", {}) or {}
    idx = load_index(lib)
    out = []
    for w in _load(lib):
        e, row = ing.get(w["id"]) or {}, idx.get(w["id"]) or {}
        if e.get("ocr") or "no_text" not in (e.get("exceptions") or []) or row.get("status") != "ok" or not row.get("path"):
            continue
        pdf = lib / row["path"]
        if not pdf.exists():
            continue
        with pymupdf.open(pdf) as d:
            n = d.page_count
        out.append({"id": w["id"], "title": w.get("title"), "pdf": str(pdf), "pages": n, "out": str(lib / "work" / "ocr" / f"{w['id']}.txt")})
    (lib / "work" / "ocr").mkdir(parents=True, exist_ok=True)
    (lib / "work" / "ocr" / "todo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def ocr_apply(lib, wid):
    """核對轉錄者寫的 work/ocr/<id>.txt：每一頁 [p.N] 都要有、而且有字（空白頁寫「（空白頁）」）；過了才變成全文。"""
    import re
    from pipeline.index import load_index
    t = next((x for x in json.loads((lib / "work" / "ocr" / "todo.json").read_text()) if x["id"] == wid), None) if (lib / "work" / "ocr" / "todo.json").exists() else None
    if not t:
        raise ValueError(f"{wid} 不在轉錄清單")
    p = lib / "work" / "ocr" / f"{wid}.txt"
    if not p.exists():
        raise ValueError(f"轉錄者還沒寫 {p}")
    text = p.read_text()
    pages = re.split(r"^\[p\.(\d+)\]\s*$", text, flags=re.M)
    got = {int(pages[i]): pages[i + 1].strip() for i in range(1, len(pages) - 1, 2)}
    missing = [n for n in range(1, t["pages"] + 1) if not got.get(n)]
    if missing:
        raise ValueError("轉錄缺頁：" + "、".join(f"p.{n}" for n in missing))
    w = next(x for x in _load(lib) if x["id"] == wid)
    body = "\n".join(f"[p.{n}]\n{got[n]}\n" for n in range(1, t["pages"] + 1))
    (lib / "work" / "text" / f"{wid}.txt").write_text(f"# {wid} | pdf | {w.get('title') or ''}\n\n" + body)
    ing = _j(lib / "work" / "ingest.json", {}) or {}
    row = load_index(lib).get(wid) or {}
    ing[wid] = {**(ing.get(wid) or {}), "source_type": "pdf", "source_path": row.get("path"), "ocr": True, "chars": len(body),
                "exceptions": [k for k in (ing.get(wid) or {}).get("exceptions", []) if k != "no_text"]}
    (lib / "work" / "ingest.json").write_text(json.dumps(ing, ensure_ascii=False, indent=2))
    print(f"DONE {wid} 轉錄 {t['pages']} 頁")
    return ing[wid]


def zotero(collection=None):
    if collection:
        items = get_json(f"{ZOTERO}/collections/{collection}/items/top?limit=100", min_interval=0)
        return {"items": parse_zotero_items(items)}
    cols = get_json(f"{ZOTERO}/collections?limit=100", min_interval=0)
    return {"collections": [{"key": c["key"], "name": (c.get("data") or {}).get("name")} for c in cols]}


def ris(lib):
    works = json.loads((lib / "work" / "works.json").read_text())
    idx = {}
    if (lib / "pdfs" / "index.csv").exists():
        import csv
        idx = {r["id"]: r for r in csv.DictReader(open(lib / "pdfs" / "index.csv"))}
    digests = {w["id"]: _j(lib / "out" / "papers" / paper_dir_name(w) / "重點.json") or {} for w in works}
    pdfs = {i: str((lib / r["path"]).resolve()) for i, r in idx.items() if r.get("status") == "ok" and r.get("path")}
    out = lib / "out" / "zotero"
    out.mkdir(parents=True, exist_ok=True)
    (out / "library.ris").write_text(ris_export(works, digests, pdfs))
    print(f"DONE library/out/zotero/library.ris：{len(works)} 篇")


def draft_inputs(run, lib, ids):
    me = _j(run.parent / "_me" / "me.json") or {}
    lw = {w["id"]: w for w in json.loads((lib / "work" / "works.json").read_text())}
    pw = {w["id"]: w for w in _j(run / "work" / "works.json", [])}
    bad = [i for i in ids if i not in lw and i not in pw]
    if bad:
        print(f"BLOCKED 沒有這些文獻：{', '.join(bad)}")
        sys.exit(1)

    def brief(root, w):
        dg = _j(root / "out" / "papers" / paper_dir_name(w) / "重點.json") or {}
        return {"id": w["id"], "title": w.get("title"), "year": w.get("year"), "library": w.get("library"),
                "key_points": dg.get("key_points"), "design": dg.get("design"), "method": dg.get("method"),
                "abstract": None if dg else (w.get("abstract") or "")[:1500]}
    sel = [brief(lib, lw[i]) if i in lw else brief(run, pw[i]) for i in ids]
    act = active_grants(_j(run / "work" / "grants" / "grants_final.json", []) or [])
    did = datetime.now().strftime("%Y%m%d-%H%M%S")
    dd = run / "drafts" / did
    dd.mkdir(parents=True)
    joint = me.get("proposal") or {}
    (dd / "inputs.json").write_text(json.dumps({
        "selected": sel, "selected_ids": ids,
        "professor_papers": [{"id": w["id"], "year": w.get("year"), "title": w.get("title")} for w in pw.values()],
        "active_grants": act, "template_sections": joint.get("document") or [],
        "joint_proposal_with_this_professor": joint if me.get("proposal_with") == run.name else None,
        "me_cv": {k: me.get(k) for k in ("summary", "interests", "education", "publications", "projects", "capabilities")},
    }, ensure_ascii=False, indent=1))
    print(f"DONE drafts/{did}/inputs.json：勾選 {len(ids)} 篇")


def draft_check(run, lib, did, assemble=False):
    dd = run / "drafts" / did
    inp, d = _j(dd / "inputs.json"), _j(dd / "draft.json")
    if not inp or d is None:
        print(f"BLOCKED drafts/{did} 少了 inputs.json 或 draft.json")
        sys.exit(1)
    act = {g["key"]: g for g in inp["active_grants"]}
    fails = check_lib_draft(d, set(inp["selected_ids"]), {p["id"] for p in inp["professor_papers"]}, act)
    for f in fails:
        print(f"FAIL {f['path']} {f['why']}")
    if fails:
        sys.exit(1)
    if not assemble:
        print("PASS 初稿各段中英齊全、只引勾選的文獻與她的文章、每段說法都有出處")
        return
    out = {**d, "id": did, "selected_ids": inp["selected_ids"], "built": datetime.now().astimezone().isoformat(timespec="seconds")}
    (dd / "final.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    append_progress(run, "library", f"用勾選的 {len(inp['selected_ids'])} 篇擬初稿 drafts/{did}")
    print(f"DONE drafts/{did}/final.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add-doi", "add-pdf", "process", "ocr-todo", "ocr-apply", "zotero", "ris", "draft-inputs", "draft-check", "draft-assemble"])
    ap.add_argument("run")
    ap.add_argument("--doi")
    ap.add_argument("--pdf")
    ap.add_argument("--source", default="doi")
    ap.add_argument("--given-by")
    ap.add_argument("--discussion")
    ap.add_argument("--note")
    ap.add_argument("--collection")
    ap.add_argument("--ids")
    ap.add_argument("--draft")
    ap.add_argument("--id", help="ocr-apply：哪一份")
    a = ap.parse_args()
    run = Path(a.run)
    lib = lib_dir(run)
    if a.cmd == "add-doi":
        add_doi(lib, a.doi, a.source, **_meta(a))
    elif a.cmd == "add-pdf":
        add_pdf(lib, a.pdf, **_meta(a))
        relink_uploads(lib)
    elif a.cmd == "process":
        process(lib)
    elif a.cmd == "ocr-todo":
        print(json.dumps(ocr_todo(lib), ensure_ascii=False, indent=1))
    elif a.cmd == "ocr-apply":
        try:
            ocr_apply(lib, a.id)
        except ValueError as e:
            print(f"FAIL {e}")
            sys.exit(1)
    elif a.cmd == "zotero":
        print(json.dumps(zotero(a.collection), ensure_ascii=False, indent=1))
    elif a.cmd == "ris":
        ris(lib)
    elif a.cmd == "draft-inputs":
        draft_inputs(run, lib, [i.strip() for i in (a.ids or "").split(",") if i.strip()])
    else:
        draft_check(run, lib, a.draft, assemble=a.cmd == "draft-assemble")


if __name__ == "__main__":
    main()
