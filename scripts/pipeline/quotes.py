"""引句核對：引句正規化後必須逐字出現在標準化文字的指定位置（或緊接的下一個位置，容許跨頁）。"""
import re

from .textify import MARKER, normalize_for_match

MIN_QUOTE_CHARS = 12
CITATION = re.compile(r"[\"“]([^\"”]+)[\"”]\s*\[(W\d+),\s*(p\.\d+|§\d+|abs)\]")


def _sections(text):
    """[(loc, 內容)]，依出現順序。"""
    out = []
    matches = list(MARKER.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[m.end():end]))
    return out


def section_at(text, loc):
    for l, body in _sections(text):
        if l == loc:
            return body
    return None


def _norm(s):
    s = re.sub(r"[\[\]]", " ", s or "")  # 參考文獻方括號只拿掉括號本身（引句可能在 [15, 16] 中間切斷）
    s = normalize_for_match(s)
    s = re.sub(r"(?<=[a-z])- (?=[a-z])", "", s)  # 斷行連字號被抄成「computa- tional」
    s = re.sub(r"(?<=[a-z])-$", "", s)  # 引句停在行尾連字號
    s = re.sub(r"\s+([.,;:)])", r"\1", s)  # XML 去掉交互參照後標點前多出的空白
    s = re.sub(r"([.,;:])(?:\s*[.,;:])+", r"\1", s)  # "[,]." 這類殘留的連續標點
    return s


def check_quote(text, quote, loc):
    q = _norm(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return False, "too_short"
    secs = _sections(text)
    idx = next((i for i, (l, _) in enumerate(secs) if l == loc), None)
    if idx is None:
        return False, "no_such_loc"
    here = _norm(secs[idx][1])
    if q in here:
        return True, "ok"
    if idx + 1 < len(secs):
        nxt_only = _norm(secs[idx + 1][1])
        # 只有真正跨越分界（整句不在下一節裡）才算這個位置
        if q not in nxt_only and q in _norm(secs[idx][1] + " " + secs[idx + 1][1]):
            return True, "ok"
    for l, body in secs:
        if q in _norm(body):
            return False, f"wrong_loc:{l}"
    return False, "not_found"


def parse_citations(s):
    return [(m.group(1), m.group(2), m.group(3)) for m in CITATION.finditer(s or "")]
