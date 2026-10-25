"""每篇的圖與表：腳本從全文抓出所有「Figure N／Table N」的標題（caption）與所在頁，PDF 另存該頁的圖片，
一個都不漏；AI 再依標題與內文說明每張圖表在講什麼（digest），腳本核對。"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

CAPTION = re.compile(r"^\s*((?:Supplementary\s+|Supplemental\s+|Extended\s+Data\s+)?(?:Figure|Fig\.?|Table|Box|Chart|Graph)\s*S?\d+[A-Za-z]?)\s*[.:|\-–—]?\s*(.*)", re.I | re.S)


def norm_label(label):
    l = re.sub(r"\s+", " ", label.strip())
    l = re.sub(r"^Fig\.?\s*(?=S?\d)", "Figure ", l, flags=re.I).rstrip(".:")
    return l[:1].upper() + l[1:]


def _looks_like_caption(label, rest):
    """「Table 1. Baseline characteristics」是標題；「Table 1 shows that…」「Figure 2), and…」是內文提到，不算。"""
    rest = rest.strip()
    if not rest:
        return True
    if re.match(r"^(shows?|presents?|summari[sz]es|lists?|illustrates?|depicts?|and|or|in|of|for|was|were|is|are|\)|,|;)\b", rest, re.I):
        return False
    return True


def captions_from_blocks(blocks):
    """blocks: [(頁碼, 文字)]，依閱讀順序。回傳 [{label, caption, page}]，同一個 label 只留第一個像標題的。"""
    out, seen = [], set()
    for page, text in blocks:
        m = CAPTION.match(text or "")
        if not m:
            continue
        label, rest = norm_label(m.group(1)), m.group(2)
        if label.lower() in seen or not _looks_like_caption(label, rest):
            continue
        seen.add(label.lower())
        cap = re.sub(r"\s+", " ", f"{m.group(1)} {rest}").strip()
        out.append({"label": label, "caption": cap[:800], "page": page})
    return out


def from_pdf(path, out_dir, zoom=1.4, max_pages=60):
    import pymupdf
    blocks = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            if i > max_pages:
                break
            for b in page.get_text("blocks"):
                blocks.append((i, b[4]))
        items = captions_from_blocks(blocks)
        out_dir = Path(out_dir)
        for it in items:
            png = out_dir / f"p{it['page']}.png"
            if not png.exists():
                out_dir.mkdir(parents=True, exist_ok=True)
                doc[it["page"] - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(str(png))
            it["image"] = png.name
            it["loc"] = f"p.{it['page']}"
    return items


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def from_jats(data):
    """JATS XML：<fig> 與 <table-wrap> 本來就標好了，直接取 label＋caption（沒有圖片檔，畫面上請開全文看圖）。"""
    root = ET.fromstring(data)
    out, n = [], 0
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("fig", "table-wrap"):
            continue
        n += 1
        label = _text(el.find("./label")) or ("Figure" if tag == "fig" else "Table") + f" {n}"
        cap = _text(el.find("./caption"))
        full = cap if cap.lower().startswith(label.lower().rstrip(".:")) else f"{label} {cap}"
        out.append({"label": norm_label(label), "caption": full.strip()[:800], "page": None, "loc": None, "image": None})
    return out
