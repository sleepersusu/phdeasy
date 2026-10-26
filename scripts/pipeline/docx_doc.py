"""計畫書 Word 檔（.docx）→ 依原檔順序的區塊：標題、段落、圖（原始圖檔）、表（真的表格）、參考文獻。

只用標準庫讀 docx 的 XML。圖的標題在圖的下一段、表的標題在表的上一段（Word 的慣例，Liliana 改過的那份也是）。
"""
import re
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

SECTION_KEYS = [(r"^synopsis$", "synopsis"), (r"^1\.\s*rationale", "rationale"), (r"^2\.\s*overall aim", "aims"),
                (r"^3\.\s*research programme", "programme"), (r"^4\.\s*expected contribution", "contribution"),
                (r"^5\.\s*timeline", "timeline"), (r"^6\.\s*resources", "resources"), (r"^references$", "references")]


def _text(el):
    return "".join(t.text or "" for t in el.iter(W + "t")).strip()


def _style(p):
    st = p.find(f"{W}pPr/{W}pStyle")
    return st.get(W + "val") if st is not None else ""


def _section_key(heading):
    h = heading.strip().lower()
    return next((k for rx, k in SECTION_KEYS if re.search(rx, h)), re.sub(r"\W+", "-", h).strip("-")[:40] or "section")


def parse_docx(path):
    z = zipfile.ZipFile(path)
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("word/_rels/document.xml.rels")).iter(PR + "Relationship")}
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    out = {"title": None, "subtitle": None, "meta": [], "sections": [], "media": {}}
    cur = None
    pending_caption = None  # 表的標題在表的上一段

    def add(block):
        nonlocal cur
        if cur is None:
            cur = {"key": "front", "heading_en": "", "blocks": []}
            out["sections"].append(cur)
        cur["blocks"].append(block)

    def start(heading):
        nonlocal cur
        cur = {"key": _section_key(heading), "heading_en": heading, "blocks": []}
        out["sections"].append(cur)

    for el in body:
        tag = el.tag.replace(W, "")
        if tag == "tbl":
            rows = [[_text(c) for c in tr.findall(W + "tc")] for tr in el.findall(W + "tr")]
            add({"type": "table", "caption_en": pending_caption, "rows": rows})
            pending_caption = None
            continue
        if tag != "p":
            continue
        style, text = _style(el), _text(el)
        blip = el.find(f".//{A}blip")
        if blip is not None:
            target = rels.get(blip.get(R + "embed")) or ""
            name = target.rsplit("/", 1)[-1]
            if name:
                out["media"][name] = z.read("word/" + target.lstrip("/").removeprefix("word/"))
                add({"type": "figure", "media": name, "caption_en": None})
            continue
        if not text:
            continue
        if style == "ProposalTitle":
            out["title"] = text
        elif style == "ProposalSubtitle":
            out["subtitle"] = text
        elif style == "ProposalAuthor":
            out["author"] = text
        elif style == "ProposalHeading1" or (cur is None and text.lower() == "synopsis"):
            start(text)
        elif cur is None:
            out["meta"].append(text)
        elif style == "ProposalHeading2":
            add({"type": "h2", "en": text})
        elif style == "ProposalCaption":
            last = cur["blocks"][-1] if cur["blocks"] else None
            if text.lower().startswith("figure") and last and last["type"] == "figure" and not last["caption_en"]:
                last["caption_en"] = text  # 圖的標題在圖的下一段
            else:
                pending_caption = text
        elif style == "ProposalReference":
            add({"type": "ref", "en": text})
        elif re.match(r"^\d+\.\d+\.\d+\s", text):
            add({"type": "h3", "en": text})
        else:
            add({"type": "p", "en": text})
    return out


def parse_statement(path):
    """Personal Statement／SOP：沒有標題樣式的短文。前兩行是姓名與標題，其餘每段一個區塊；
    整段包在 [方括號] 裡的是本人留的待填說明（例：依學校改寫的段落），標 note。"""
    z = zipfile.ZipFile(path)
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    paras = [_text(el) for el in body if el.tag == W + "p"]
    paras = [t for t in paras if t]
    author, title = (paras[:2] + [None, None])[:2]
    blocks = [{"type": "note" if t.startswith("[") and t.endswith("]") else "p", "en": t} for t in paras[2:]]
    return {"author": author, "title": title, "blocks": blocks}
