"""每篇的圖與表：腳本從全文抓出所有「Figure N／Table N」的標題（caption）與所在頁，PDF 另存該頁的圖片，
一個都不漏；AI 再依標題與內文說明每張圖表在講什麼（digest），腳本核對。"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

CAPTION = re.compile(r"^\s*((?:Supplementary\s+|Supplemental\s+|Extended\s+Data\s+)?(?:Figure|Fig\.?|Table|Box|Chart|Graph|Encadr[ée]|Tableau|Figura|Tabla|Tabelle|Abbildung|Quadro)\s*S?\d+[A-Za-z]?)\s*[.:|\-–—]?\s*(.*)", re.I | re.S)


def norm_label(label):
    l = re.sub(r"\s+", " ", label.strip())
    l = re.sub(r"^Fig\.?\s*(?=S?\d)", "Figure ", l, flags=re.I).rstrip(".:")
    return l[:1].upper() + l[1:]


def _looks_like_caption(label, rest):
    """「Table 1. Baseline characteristics」是標題；「Table 1 shows that…」「Figure 2), and…」是內文提到，不算。"""
    rest = rest.strip()
    if not rest:
        return True
    # 內文提到圖表時後面接小寫的動詞或連接詞（Table 1 shows…、Figure 2 and…）；標題後面通常是大寫開頭（Table 2  OR of…）
    if re.match(r"^(shows?|presents?|summari[sz]es|lists?|illustrates?|depicts?|displays?|and|or|in|of|for|was|were|is|are)\b", rest) or re.match(r"^[),;]", rest):
        return False
    return True


def _caption_score(text, rest):
    """同一個 label 出現好幾次時挑最像標題的：短、後面有說明、不像一整段內文。"""
    score = 0
    if len(text) < 400:
        score += 2
    if re.match(r"^(An?\s+)?(overview|flow|summary|characteristics|results?|schematic|map|framework|diagram|timeline|baseline|comparison|distribution|association|proportion)", rest.strip(), re.I):
        score += 1
    if re.search(r"\b(was|were|is|are|we|our)\b", rest[:120]):
        score -= 1
    return score


def captions_from_blocks(blocks):
    """blocks: [(頁碼, 文字)]，依閱讀順序。回傳 [{label, caption, page}]，同一個 label 留最像標題的那一個，依頁序排。"""
    best = {}
    order = 0
    for page, text in blocks:
        lines = (text or "").split("\n")
        for i in range(len(lines)):  # 標題不一定在區塊開頭（PDF 常把上一段和表題併成一塊）
            chunk = "\n".join(lines[i:])
            m = CAPTION.match(chunk)
            if not m:
                continue
            label, rest = norm_label(m.group(1)), m.group(2)
            if not _looks_like_caption(label, rest):
                continue
            cap = re.sub(r"\s+", " ", f"{m.group(1)} {rest}").strip()
            sc = _caption_score(chunk, rest)
            key = label.lower()
            if key not in best or sc > best[key][0]:
                best[key] = (sc, order if key not in best else best[key][1], {"label": label, "caption": cap[:800], "page": page, "raw": m.group(1).strip()})
            order += 1
            break
    items = [v[2] for v in best.values()]
    return sorted(items, key=lambda x: (x["page"] or 0, [v[1] for v in best.values() if v[2] is x][0]))


def figure_clip(page, label, caption_head):
    """在這一頁找出這張圖表本身的範圍（不要整頁）：
    圖：標題附近的圖片與向量圖形聯集，加上標題；表：從表題往下，直到下一個大空白或其他圖表標題。找不到就回 None（用整頁）。"""
    import pymupdf
    pr = page.rect
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    head = re.sub(r"\s+", " ", caption_head).lower()
    starts = lambda t: any(re.sub(r"\s+", " ", ln).strip().lower().startswith(head) for ln in t.split("\n"))
    cap = next((b for b in blocks if starts(b[4])), None)
    if cap is None:
        return None
    cap_r = pymupdf.Rect(cap[:4])
    is_table = label.lower().startswith(("table", "tableau", "tabla", "tabelle"))
    if not is_table:
        rects = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info() if pymupdf.Rect(i["bbox"]).get_area() > pr.get_area() * 0.01]
        try:
            rects += [d["rect"] for d in page.get_drawings() if d["rect"].get_area() > pr.get_area() * 0.002]
        except Exception:
            pass
        rects = [r for r in rects if r.width < pr.width * 0.98 or r.height < pr.height * 0.98]  # 整頁背景框不算
        if not rects:
            return None
        u = pymupdf.Rect(rects[0])
        for r in rects[1:]:
            u |= r
        u |= cap_r
        return (u + (-8, -8, 8, 8)) & pr
    # 表：表題往下接續的區塊
    below = sorted([pymupdf.Rect(b[:4]) for b in blocks if b[1] >= cap_r.y0 - 2], key=lambda r: r.y0)
    u, last = pymupdf.Rect(cap_r), cap_r.y1
    for r in below:
        if r.y0 - last > 36:  # 大空白：表格結束
            break
        txt = next((b[4] for b in blocks if abs(b[1] - r.y0) < 0.5 and abs(b[0] - r.x0) < 0.5), "")
        if r != cap_r and CAPTION.match(txt or "") and not starts(txt):
            break
        u |= r
        last = max(last, r.y1)
    if u.height < 40:
        return None
    return (u + (-8, -8, 8, 8)) & pr


def from_pdf(path, out_dir, zoom=2.0, max_pages=60):
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
            page = doc[it["page"] - 1]
            slug = re.sub(r"[^A-Za-z0-9]+", "-", it["label"]).strip("-").lower()
            clip = None
            try:
                clip = figure_clip(page, it["label"], it.get("raw") or it["label"])
            except Exception:
                clip = None
            png = out_dir / (f"{slug}.png" if clip else f"p{it['page']}.png")
            if not png.exists():
                out_dir.mkdir(parents=True, exist_ok=True)
                page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).save(str(png))
            it["image"] = png.name
            it["cropped"] = bool(clip)
            it["loc"] = f"p.{it['page']}"
    return items


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


SAFE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "b", "bold", "i", "italic", "sup", "sub", "br", "caption"}
TAG_MAP = {"bold": "b", "italic": "i"}


def _table_html(el):
    """JATS 的 <table> 轉成安全的 HTML 表格（只留表格結構與粗斜體、上下標；合併儲存格保留 colspan/rowspan）。"""
    import html as _h
    def walk(node):
        tag = node.tag.split("}")[-1]
        inner = _h.escape(node.text or "") + "".join(walk(c) + _h.escape(c.tail or "") for c in node)
        if tag not in SAFE_TAGS:
            return inner
        t = TAG_MAP.get(tag, tag)
        attrs = "".join(f' {a}="{int(node.get(a))}"' for a in ("colspan", "rowspan") if (node.get(a) or "").isdigit())
        return f"<{t}{attrs}>{inner}</{t}>"
    tbl = next((c for c in el.iter() if c.tag.split("}")[-1] == "table"), None)
    return walk(tbl) if tbl is not None else None


def from_jats(data):
    """JATS XML：<fig> 與 <table-wrap> 本來就標好了。回傳 label、caption、graphic（圖檔名，之後從 PMC 開放取用資料集下載）、
    table_html（表格本身，前端直接畫成表格）。"""
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
        g = next((c for c in el.iter() if c.tag.split("}")[-1] == "graphic"), None)
        href = None
        if g is not None:
            href = next((v for k, v in g.attrib.items() if k.endswith("href")), None)
        out.append({"label": norm_label(label), "caption": full.strip()[:800], "page": None, "loc": None, "image": None,
                    "graphic": href, "table_html": _table_html(el) if tag == "table-wrap" else None})
    return out


def pmc_files(list_xml):
    """PMC 開放取用資料集（AWS 公開資料，美國國家醫學圖書館提供）的檔案清單 XML → 檔名列表。"""
    return re.findall(r"<Key>([^<]+)</Key>", list_xml.decode("utf-8", "ignore") if isinstance(list_xml, bytes) else list_xml)


def match_graphic(href, keys):
    """XML 裡的圖檔名（可能沒有副檔名）對到資料集裡的檔案。"""
    if not href:
        return None
    base = href.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    for k in keys:
        name = k.rsplit("/", 1)[-1]
        if name == base or name.rsplit(".", 1)[0] == stem and name.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            return k
    return None
