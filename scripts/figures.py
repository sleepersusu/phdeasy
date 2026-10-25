"""每篇的圖與表：從全文抓出所有 Figure／Table 標題，PDF 另存該頁圖片。

  uv run python scripts/figures.py extract runs/<slug>    # → work/figures/<id>.json、out/papers/<這篇的資料夾>/figures/p<N>.png
"""
import argparse
import json
from pathlib import Path

from pipeline.export import paper_dir_name
from pipeline.figures import from_jats, from_pdf
from pipeline.state import append_progress


def merge_xml_pdf(jats, pdf_items):
    """XML 標好的圖表清單為準（不會漏）；PDF 抓到同一個圖號的，補上頁碼與頁面截圖。XML 沒標任何圖表才用 PDF 的。"""
    if not jats:
        return pdf_items
    by = {it["label"].lower(): it for it in pdf_items}
    out = []
    for it in jats:
        p = by.get(it["label"].lower())
        out.append({**it, **({"page": p["page"], "loc": p["loc"], "image": p["image"]} if p else {})})
    return out


def figure_pdf(run, w):
    """XML 全文的文章：試 OpenAlex 與期刊落地頁的免費 PDF，存在 work/figures/_pdf/（只用來截圖表）。"""
    from pipeline.fetch import is_pdf
    from pipeline.http import get
    from setup_fulltext import r_landing, r_openalex
    dst = run / "work" / "figures" / "_pdf" / f"{w['id']}.pdf"
    if dst.exists():
        return dst
    for resolver in (r_openalex, r_landing):
        try:
            urls = resolver(w)
        except Exception:
            continue
        for u in urls:
            data, status = get(u, accept="application/pdf")
            if data and is_pdf(data):
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                return dst
    return None


def extract(run):
    ing = json.loads((run / "work" / "ingest.json").read_text())
    wmap = {w["id"]: w for w in json.loads((run / "work" / "works.json").read_text())}
    works = set(wmap)
    fd = run / "work" / "figures"
    fd.mkdir(parents=True, exist_ok=True)
    n_papers, n_items, n_img = 0, 0, 0
    for wid, e in ing.items():
        if wid not in works or e.get("source_type") not in ("pdf", "xml") or not e.get("source_path"):
            continue
        src = run / e["source_path"]
        folder = paper_dir_name(wmap[wid])
        figdir = run / "out" / "papers" / folder / "figures"
        try:
            if e["source_type"] == "xml":
                pdf = figure_pdf(run, wmap[wid])  # XML 沒有圖片：另外抓出版社的 PDF 只拿來截圖表頁（不放進 pdfs/，不改原檔）
                items = merge_xml_pdf(from_jats(src.read_bytes()), from_pdf(pdf, figdir) if pdf else [])
            else:
                items = from_pdf(src, figdir)
        except Exception as ex:
            print(f"  {wid} 讀不出圖表：{type(ex).__name__}: {ex}")
            continue
        for it in items:
            if it.get("image"):
                it["image"] = f"../papers/{folder}/figures/{it['image']}"  # 相對於 out/site/
        (fd / f"{wid}.json").write_text(json.dumps({"id": wid, "source": e["source_type"], "folder": folder, "items": items}, ensure_ascii=False, indent=1))
        n_papers += 1
        n_items += len(items)
        n_img += sum(1 for it in items if it.get("image"))
    summary = f"圖表：{n_papers} 篇全文，共 {n_items} 張圖／表（存頁面圖片 {n_img}）"
    append_progress(run, "figures", summary)
    print(f"DONE {summary}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract"])
    ap.add_argument("run")
    a = ap.parse_args()
    extract(Path(a.run))


if __name__ == "__main__":
    main()
