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


def pdf_to_marked(path):
    import pymupdf

    parts = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            parts.append(f"[p.{i}]\n{page.get_text().strip()}\n")
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
    t = unicodedata.normalize("NFKC", text or "")
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
