"""雙語：解析卡與計畫的翻譯核對。翻譯由 agent 做，這裡只做可機械判定的檢查。

卡片翻譯 work/cards/<id>/i18n.json：
  {"id", "title_zh", "en": {"summary", "design", "sample", "gap": [...], "solves": [...], "findings": [...],
   "limitations": {"author_stated": [...], "inferred": [...]}}, "keywords_zh": [...], "keywords_en": [...]}
  en 的每一條對應 card.json 同位置的中文說法（依 card_items 的順序與索引）。
計畫翻譯 work/grants/i18n.json：{key: {"title_zh", "summary_en", "summary_zh"} 或 {"funder_zh"}}
"""
import re

from .cards import numbers_in

ZH_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
EN_NUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
EN_ORD = {w: i + 1 for i, w in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth".split())}
MIN_KEYWORDS = 5


def _zh_numeral(tok):
    """一、十二、二十、四十五、一百 → 整數。"""
    if "百" in tok:
        a, _, b = tok.partition("百")
        return (ZH_DIGIT.get(a, 1) if a else 1) * 100 + (_zh_numeral(b) if b else 0)
    if "十" in tok:
        a, _, b = tok.partition("十")
        return (ZH_DIGIT.get(a, 1) if a else 1) * 10 + (ZH_DIGIT.get(b, 0) if b else 0)
    return ZH_DIGIT.get(tok, 0)


def _digits(text):
    return {float(n) for n in numbers_in(text or "")}


def _zh_words(text):
    out = set()
    for m in re.finditer(r"[零〇一二兩三四五六七八九十百]+", text or ""):
        n = _zh_numeral(m.group(0))
        out.add(float(n))
        if (text or "")[m.end():m.end() + 1] == "成":  # 四成 = 40%
            out.add(float(n * 10))
    return out


def _en_all(text, ordinals=True):
    t = text or ""
    out = _digits(re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t))
    words = list(EN_NUM) + (list(EN_ORD) if ordinals else [])
    for m in re.finditer(r"\b(" + "|".join(words) + r")\b", t, flags=re.I):
        w = m.group(1).lower()
        out.add(float(EN_NUM.get(w, EN_ORD.get(w))))
    if re.search(r"\btwice\b", t, re.I):
        out.add(2.0)
    for m in re.finditer(r"\btype (I{1,3}|IV)\b", t):
        out.add(float({"I": 1, "II": 2, "III": 3, "IV": 4}[m.group(1)]))
    return out


EN_TENS = {w: (i + 2) * 10 for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
MONTHS = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}


def _en_words(text):
    """英文數字詞、序數詞、twenty-six、月份名（May = 5）→ 數值，只用來滿足「中文的數字不能少」。"""
    t = (text or "").lower()
    out = _en_all(text)
    for m in re.finditer(r"\b(" + "|".join(EN_TENS) + r")(?:[- ](" + "|".join(list(EN_NUM)[1:10]) + r"))?\b", t):
        out.add(float(EN_TENS[m.group(1)] + (EN_NUM[m.group(2)] if m.group(2) else 0)))
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\b", t):
        out.add(float(MONTHS[m.group(1)]))
    return out


def numbers_match(zh, en):
    """中文的阿拉伯數字一個都不能少；英文的每個數字都要能在中文（阿拉伯數字或中文數字、X成、第X）找到。"""
    zh_digits = _digits(zh)
    # 中文的阿拉伯數字要在英文出現（英文序數詞也算）；英文的數字要在中文找到（英文序數詞 first/second 不強制）
    # 中文的阿拉伯數字一個都不能少（英文寫成數字詞、twenty-six、月份名也算）；英文多出來的「阿拉伯數字」必須在中文找得到
    return zh_digits <= _en_words(en) and _digits(en) <= (zh_digits | _zh_words(zh))


def card_items(card):
    f = card.get("fields") or {}
    out = []
    for k in ("summary", "design", "sample"):
        v = f.get(k) or {}
        if v.get("status") in ("ok", "unresolved") and (v.get("text") or "").strip():
            out.append((k, v["text"]))
    for k in ("gap", "solves", "findings"):
        v = f.get(k) or {}
        if v.get("status") in ("ok", "unresolved"):
            out += [(f"{k}[{i}]", c["text"]) for i, c in enumerate(v.get("claims") or [])]
    lim = f.get("limitations") or {}
    if lim.get("status") in ("ok", "unresolved"):
        for sub in ("author_stated", "inferred"):
            out += [(f"limitations.{sub}[{i}]", c["text"]) for i, c in enumerate(lim.get(sub) or [])]
    return out


def _en_at(en, path):
    m = re.match(r"^(\w+)(?:\.(\w+))?(?:\[(\d+)\])?$", path)
    head, sub, idx = m.group(1), m.group(2), m.group(3)
    v = en.get(head)
    if sub:
        v = (v or {}).get(sub)
    if idx is not None:
        v = v[int(idx)] if isinstance(v, list) and int(idx) < len(v) else None
    return v


def i18n_from_card(card, a):
    """合併閱讀者（本人 2026-10-26：一篇只讀一次全文）把英文寫在每一句旁邊（text_en）；
    組裝後從最終卡留下的說法取英文，title_zh／關鍵詞取自 a.json。漏寫的英文留空，check_card_i18n 會抓到。"""
    f = card.get("fields") or {}
    en = {}
    for k in ("summary", "design", "sample"):
        if (f.get(k) or {}).get("text_en"):
            en[k] = f[k]["text_en"]
    for k in ("gap", "solves", "findings"):
        cl = (f.get(k) or {}).get("claims") or []
        if cl:
            en[k] = [c.get("text_en") for c in cl]
    lim = f.get("limitations") or {}
    en["limitations"] = {sub: [c.get("text_en") for c in lim.get(sub) or []] for sub in ("author_stated", "inferred")}
    return {"id": card.get("id") or a.get("id"), "title_zh": a.get("title_zh"), "en": en,
            "keywords_zh": a.get("keywords_zh") or [], "keywords_en": a.get("keywords_en") or []}


def check_card_i18n(card, tr):
    fails = []
    if not (tr.get("title_zh") or "").strip():
        fails.append({"path": "title_zh", "why": "empty"})
    for k in ("keywords_zh", "keywords_en"):
        kws = [x for x in tr.get(k) or [] if str(x).strip()]
        if len(kws) < MIN_KEYWORDS:
            fails.append({"path": k, "why": f"too_few:{len(kws)}<{MIN_KEYWORDS}"})
    en = tr.get("en") or {}
    for path, zh in card_items(card):
        v = _en_at(en, path)
        if v is None:
            fails.append({"path": path, "why": "missing"})
        elif not str(v).strip():
            fails.append({"path": path, "why": "empty"})
        elif not numbers_match(zh, v):
            fails.append({"path": path, "why": f"numbers_differ:zh={sorted(_digits(zh) | _zh_words(zh))} en={sorted(_en_all(v))}"})
    return fails


def check_grants_i18n(grants, tr):
    fails = []
    for g in grants:
        t = tr.get(g["key"])
        if t is None:
            fails.append({"key": g["key"], "why": "missing"})
            continue
        if g.get("title"):
            if not (t.get("title_zh") or "").strip():
                fails.append({"key": g["key"], "why": "title_zh_empty"})
            elif not numbers_match(t["title_zh"], g["title"]):
                fails.append({"key": g["key"], "why": "numbers_differ:title"})
        elif g.get("funder") and not (t.get("funder_zh") or "").strip():
            fails.append({"key": g["key"], "why": "funder_zh_empty"})
        if g.get("abstract"):
            se, sz = t.get("summary_en") or "", t.get("summary_zh") or ""
            if not se.strip() or not sz.strip():
                fails.append({"key": g["key"], "why": "summary_empty"})
                continue
            extra = _en_all(se) - _en_all(g["abstract"])
            if extra:
                fails.append({"key": g["key"], "why": f"number_not_in_abstract:{sorted(extra)}"})
            if not numbers_match(sz, se):
                fails.append({"key": g["key"], "why": "numbers_differ:summary"})
    return fails
