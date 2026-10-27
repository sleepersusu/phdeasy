"""標準化：PDF／JATS XML／摘要 → 帶位置標記的純文字。

位置標記：PDF 每頁開頭 `[p.N]`（N 為 PDF 第幾頁，不是期刊印的頁碼）；XML 每段開頭 `[§N]`；摘要 `[abs]`。
引句核對用 normalize_for_match 正規化後比對。
"""
import re
import unicodedata
import xml.etree.ElementTree as ET

MIN_CHARS = 1500
MARKER = re.compile(r"\[(p\.\d+|§\d+|abs)\]")
SKIP_TAGS = {"ref-list", "xref", "label", "object-id"}
BLOCK_TAGS = {"p", "title", "caption", "award-group", "funding-statement"}


def clean_pdf_text(s):
    """部分 PDF 字型把負號編成控制字元 \x02（例：W4392799619），還原成負號；
    把小數中點（94·7%）編成 $ 的（例：W4399408713），還原成小數點。"""
    s = re.sub(r"\x02(?=[\d.])", "−", s)
    return re.sub(r"(?<=\d)\$(?=\d)", ".", s)


def _cell(c):
    return re.sub(r"\s+", " ", clean_pdf_text(str(c or ""))).replace("|", "／").strip()


def _page_with_tables(page):
    """一頁的文字，表格留成 Markdown 表格（| a | b |）放在原本的位置；表格裡的字不在別處重複。
    給 Meeting 文件用（指引、檢核表常是表格）；找不到表格就是一般的文字。"""
    try:
        tabs = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    except Exception:
        tabs = []
    if not tabs:
        return clean_pdf_text(page.get_text()).strip()
    import pymupdf
    boxes = [pymupdf.Rect(t.bbox) for t in tabs]
    items = []
    for b in page.get_text("blocks"):
        r = pymupdf.Rect(b[:4])
        if b[6] == 0 and not any(r.intersects(x) and (r & x).get_area() > 0.5 * r.get_area() for x in boxes):
            items.append((r.y0, clean_pdf_text(b[4]).strip()))
    for t, x in zip(tabs, boxes):
        rows = [[_cell(c) for c in row] for row in t.extract()]
        rows = [r for r in rows if any(r)]
        if len(rows) < 2:
            continue
        md = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"] + ["| " + " | ".join(r) + " |" for r in rows[1:]]
        items.append((x.y0, "\n".join(md)))
    return "\n\n".join(t for _, t in sorted(items, key=lambda z: z[0]) if t)


_ENGINE = []


def _ocr_engine():
    """OCR 套件（rapidocr-onnxruntime：模型跟著套件來，不用另外裝程式、不用網路，Windows 也能用）；裝不起來就回 None。"""
    if not _ENGINE:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ENGINE.append(RapidOCR())
        except Exception:
            _ENGINE.append(None)
    return _ENGINE[0]


def fix_ocr_spacing(s):
    """OCR 讀英文常把字黏在一起（PeoplewhomeettheICMJE…）：很長一串沒有空白的英文字母拆回單字；標點後面補空白。"""
    s = re.sub(r"(?<=[a-z])([,;:])(?=[A-Za-z])", r"\1 ", s)
    try:
        import wordninja
    except ImportError:
        return s

    def split(m):
        parts = wordninja.split(m.group(0))
        out = []
        for p in parts:  # 拆成一個一個大寫字母的（縮寫）黏回去
            if out and p.isupper() and len(p) <= 2 and out[-1].isupper() and len(out[-1]) <= 6:
                out[-1] += p
            else:
                out.append(p)
        return " ".join(out)
    return re.sub(r"[A-Za-z]{10,}", split, s)


def _ocr_page(page, engine):
    """掃描頁：轉成圖片讀字，再依行距把一行一行接成段落。"""
    res, _ = engine(page.get_pixmap(dpi=200).tobytes("png"))
    lines = []
    for box, txt, _score in res or []:
        ys = [p[1] for p in box]
        lines.append((min(ys), max(ys), fix_ocr_spacing(str(txt).strip())))
    lines.sort(key=lambda x: x[0])
    paras, cur, last = [], [], None
    for y0, y1, t in lines:
        h = max(y1 - y0, 1)
        if cur and last is not None and y0 - last > 0.9 * h:  # 行距特別大：換段
            paras.append(" ".join(cur))
            cur = []
        cur.append(t)
        last = y1
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras)


def pdf_to_marked(path, tables=False, ocr=False):
    """ocr＝True：沒有文字層的頁（掃描檔）用 OCR 讀字（Meeting 文件用）。"""
    import pymupdf

    parts = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            body = _page_with_tables(page) if tables else clean_pdf_text(page.get_text()).strip()
            if ocr and len(re.sub(r"\s+", "", body)) < 20:
                eng = _ocr_engine()
                if eng is not None:
                    try:
                        body = _ocr_page(page, eng)
                    except Exception:
                        pass
            parts.append(f"[p.{i}]\n{body}\n")
        n = len(doc)
    return "\n".join(parts), n


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el):
    """元素的完整文字，跳過參考文獻與交互參照標記。"""
    out = [el.text or ""]
    for ch in el:
        if _local(ch.tag) not in SKIP_TAGS:
            out.append(_text(ch))
        out.append(ch.tail or "")
    return " ".join("".join(out).split())


def xml_to_marked(data):
    root = ET.fromstring(data)
    lines, n = [], 0

    def para(s):
        nonlocal n
        if s:
            n += 1
            lines.append(f"[§{n}] {s}")

    def walk(el, depth):
        tag = _local(el.tag)
        if tag in SKIP_TAGS:
            return
        if tag == "article-title" and depth < 6:
            lines.append(f"# {_text(el)}")
            return
        if tag == "sec":
            t = el.find("{*}title") if el.find("{*}title") is not None else el.find("title")
            if t is not None:
                lines.append(f"## {_text(t)}")
            for ch in el:
                if _local(ch.tag) != "title":
                    walk(ch, depth + 1)
            return
        if tag == "abstract":
            lines.append("## Abstract")
        if tag == "ack":
            lines.append("## Acknowledgments")
        if tag == "award-group":
            para("Funding: " + "; ".join(_text(c) for c in el))
            return
        if tag in ("p", "funding-statement") or (tag == "caption"):
            if tag == "caption":
                para(" ".join(_text(c) for c in el) or _text(el))
            else:
                para(_text(el))
            return
        for ch in el:
            walk(ch, depth + 1)

    walk(root, 0)
    return "\n".join(lines) + "\n", n


def abstract_to_marked(abstract):
    return f"[abs]\n{' '.join((abstract or '').split())}\n"


def units(text):
    return len(MARKER.findall(text))


def has_text(text, min_chars=MIN_CHARS):
    return len(re.sub(r"\s+", "", MARKER.sub("", text))) >= min_chars


def normalize_for_match(text):
    t = unicodedata.normalize("NFKC", text or "")  # 看不見的軟連字號（BMJ 等 PDF 常見）
    t = re.sub(r"\u00ad\s*", "", t)  # 在斷行處時連同換行一起拿掉，字才接得回來
    t = re.sub(r"[‘’‚′`]", "'", t)
    t = re.sub(r"[“”„″]", '"', t)
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"-\s*\n\s*", "", t)  # 斷行連字號
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def title_matches(text, title, threshold=0.6, head_chars=4000):
    head = normalize_for_match(MARKER.sub(" ", text[: head_chars * 2]))[:head_chars]
    head_words = set(re.findall(r"\w+", head))
    words = [w for w in re.findall(r"\w+", normalize_for_match(title)) if len(w) > 3]
    if not words:
        return True
    return sum(1 for w in words if w in head_words) / len(words) >= threshold


SUPPL_HEAD = re.compile(r"(consort[- ]?ehealth|submission/publication form|^(multimedia )?appendix\b|supplementa(ry|l) (material|file|information|appendix|data)|^table s\d|reporting checklist|checklist for)", re.I)


def looks_like_supplement(text, head_lines=5):
    """第一頁開頭幾行像附錄、補充資料或報告檢核表，不是論文正文。"""
    lines = [l.strip() for l in MARKER.sub("\n", text[:3000]).split("\n") if l.strip()]
    return any(SUPPL_HEAD.search(l) for l in lines[:head_lines])
