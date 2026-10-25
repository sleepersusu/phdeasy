"""解析卡：格式驗證、引句與數字核對、雙軌比對、裁決與推翻套用、組裝。全部是純函式，不改輸入物件。

卡片格式（a.json／card.json）：
  fields.summary / design / sample：{"status", "text", "citations": [{"quote", "loc"}], ...}
    design 另有 "type"（DESIGN_TYPES 之一）；sample 另有 population、n_enrolled、n_analyzed、country、setting、period
  fields.gap / solves / findings：{"status", "claims": [{"text", "citations"}]}
  fields.limitations：{"status", "author_stated": [{"text", "citations"}], "inferred": [{"text", "basis", "citations"}]}
  status：ok／unresolved／not_in_source（來源未提及）／not_applicable（短卡不適用）
"""
import copy
import re

from .quotes import check_quote

FIELDS = ["summary", "design", "sample", "gap", "solves", "findings", "limitations"]
TEXT_FIELDS = ["summary", "design", "sample"]
CLAIM_FIELDS = ["gap", "solves", "findings"]
STATUSES = {"ok", "unresolved", "not_in_source", "not_applicable"}
DESIGN_TYPES = {
    "rct", "pilot-rct", "quasi-experimental", "single-arm", "cohort", "cross-sectional", "case-control", "qualitative",
    "mixed-methods", "systematic-review", "scoping-review", "meta-analysis", "secondary-analysis", "protocol",
    "modeling", "machine-learning", "text-mining", "other",
}
COUNTRY_ALIASES = {"usa": "united states", "us": "united states", "u.s.": "united states", "u.s.a.": "united states",
                   "united states of america": "united states", "美國": "united states", "uk": "united kingdom", "台灣": "taiwan"}
NUM = re.compile(r"\d*\.\d+|\d+")


# ---------- 格式 ----------

def validate_card(c, kind):
    errs = []
    f = c.get("fields") or {}
    need = FIELDS  # 完整卡與短卡都要 7 欄（驗收判準 3）；短卡用不到的寫 not_applicable
    for k in need:
        if k not in f:
            errs.append(f"{k}：缺欄位")
    for k, v in f.items():
        if k not in FIELDS:
            errs.append(f"{k}：不認得的欄位")
            continue
        st = v.get("status")
        if st not in STATUSES:
            errs.append(f"{k}.status 不合法：{st}")
            continue
        if st != "ok":
            continue
        if k in TEXT_FIELDS and not (v.get("text") or "").strip():
            errs.append(f"{k}：status=ok 但 text 是空的（沒有就寫 not_in_source）")
        if k == "design" and v.get("type") not in DESIGN_TYPES:
            errs.append(f"design.type 不合法：{v.get('type')}")
        if k in CLAIM_FIELDS and not v.get("claims"):
            errs.append(f"{k}：status=ok 但沒有 claims")
        if k == "limitations" and not (v.get("author_stated") or v.get("inferred")):
            errs.append("limitations：status=ok 但兩類都是空的")
    return errs


# ---------- 核對 ----------

def numbers_in(s):
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s or "")
    return NUM.findall(s)


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if i >= 2}
WORD_NUM = re.compile(r"\b(?:(" + "|".join(_TENS) + r")(?:[-\s](" + "|".join(k for k in _ONES if k != "zero") + r"))?|("
                      + "|".join(_ONES) + r"))\b", re.I)


def word_numbers(s):
    """英文拼出來的數字（摘要常寫 Twenty-four studies），只到 99。"""
    out = []
    for t, o, single in WORD_NUM.findall(s or ""):
        out.append(_TENS[t.lower()] + (_ONES[o.lower()] if o else 0) if t else _ONES[single.lower()])
    return out


def _num_set(quotes):
    out = set()
    for q in quotes:
        for n in numbers_in(q):
            out.add(float(n))
        out.update(float(n) for n in word_numbers(q))
    return out


def _items(c):
    """逐一列出卡片上每個帶出處的單位：(位置描述, 欄位, 類別, 索引, 物件)。"""
    f = c.get("fields") or {}
    for k in TEXT_FIELDS:
        v = f.get(k)
        if v and v.get("status") in ("ok", "unresolved"):
            yield (k, k, None, None, v)
    for k in CLAIM_FIELDS:
        v = f.get(k)
        if v and v.get("status") in ("ok", "unresolved"):
            for i, cl in enumerate(v.get("claims") or []):
                yield (f"{k}[{i}]", k, None, i, cl)
    v = f.get("limitations")
    if v and v.get("status") in ("ok", "unresolved"):
        for sub in ("author_stated", "inferred"):
            for i, cl in enumerate(v.get(sub) or []):
                yield (f"limitations.{sub}[{i}]", "limitations", sub, i, cl)


def check_card(c, text):
    fails = []
    for path, field, sub, idx, obj in _items(c):
        cites = obj.get("citations") or []
        field_ok = (c["fields"][field].get("status") == "ok")
        if not field_ok and not cites:
            continue  # 判不出來的欄位允許沒有出處
        if not cites and sub != "inferred":
            fails.append({"path": path, "field": field, "sub": sub, "idx": idx, "cite": None, "why": "no_citation"})
        for j, ct in enumerate(cites):
            ok, why = check_quote(text, ct.get("quote"), ct.get("loc"))
            if not ok:
                fails.append({"path": f"{path}.citations[{j}]", "field": field, "sub": sub, "idx": idx, "cite": j, "why": why,
                              "quote": ct.get("quote"), "loc": ct.get("loc")})
        quotes = [ct.get("quote") or "" for ct in cites]
        nums = []
        if field == "sample":
            nums = [str(obj[k]) for k in ("n_enrolled", "n_analyzed") if isinstance(obj.get(k), (int, float))] + numbers_in(obj.get("text"))
        elif field == "findings":
            nums = numbers_in(obj.get("text"))
        have = _num_set(quotes)
        for n in dict.fromkeys(nums):
            if float(n) not in have:
                fails.append({"path": path, "field": field, "sub": sub, "idx": idx, "cite": None, "why": f"number_not_in_quotes:{n}"})
    return fails


# ---------- 雙軌 ----------

def _country(x):
    x = (x or "").strip().lower()
    if "," in x or " and " in x or "、" in x:
        return "multiple"
    return COUNTRY_ALIASES.get(x, x) or None


def diff_fixed(a, b):
    af = a.get("fields") or {}
    pairs = [
        ("design.type", (af.get("design") or {}).get("type"), (b.get("design") or {}).get("type")),
        ("sample.n_enrolled", (af.get("sample") or {}).get("n_enrolled"), (b.get("sample") or {}).get("n_enrolled")),
        ("sample.n_analyzed", (af.get("sample") or {}).get("n_analyzed"), (b.get("sample") or {}).get("n_analyzed")),
        ("sample.country", _country((af.get("sample") or {}).get("country")), _country((b.get("sample") or {}).get("country"))),
    ]
    return [{"field": f, "a": x, "b": y} for f, x, y in pairs if x != y]


def apply_judge(c, judgments):
    out = copy.deepcopy(c)
    unresolved = []
    for j in judgments:
        field, key = j["field"].split(".", 1)
        fv = out["fields"].setdefault(field, {"status": "unresolved"})
        if j["verdict"] == "unresolved":
            fv["status"] = "unresolved"
            unresolved.append(j["field"])
        elif j["verdict"] in ("b", "value"):
            fv[key] = j.get("value")
        ev = j.get("evidence")
        if ev and ev.get("quote") and j["verdict"] != "unresolved" and ev not in fv.setdefault("citations", []):
            fv["citations"].append({"quote": ev["quote"], "loc": ev.get("loc")})
        fv.setdefault("judged", []).append({"key": key, "verdict": j["verdict"], "reason": j.get("reason")})
    return out, unresolved


# ---------- 推翻 ----------

PATH = re.compile(r"^(gap|solves|findings|limitations\.author_stated|limitations\.inferred)\[(\d+)\]$")


def _claims_list(fields, head):
    if head.startswith("limitations."):
        return fields["limitations"].setdefault(head.split(".")[1], [])
    return fields[head].setdefault("claims", [])


def _refresh_status(fields):
    for k in CLAIM_FIELDS:
        if k in fields and fields[k].get("status") == "ok" and not fields[k].get("claims"):
            fields[k]["status"] = "not_in_source"
    lim = fields.get("limitations")
    if lim and lim.get("status") == "ok" and not (lim.get("author_stated") or lim.get("inferred")):
        lim["status"] = "not_in_source"


def apply_refute(c, verdicts):
    out = copy.deepcopy(c)
    f = out["fields"]
    rejected, drop_claims, drop_cites = [], [], []
    for v in verdicts:
        m = PATH.match(v["path"])
        if not m:
            continue
        head, i = m.group(1), int(m.group(2))
        lst = _claims_list(f, head)
        if i >= len(lst):
            continue
        if v["verdict"] == "reject":
            drop_claims.append((head, i))
            rejected.append({"path": v["path"], "reason": v.get("reason"), "item": copy.deepcopy(lst[i])})
        elif v["verdict"] == "partial":
            drops = set(v.get("drop_citations") or [])
            if drops >= set(range(len(lst[i].get("citations") or []))):
                drop_claims.append((head, i))
                rejected.append({"path": v["path"], "reason": v.get("reason"), "item": copy.deepcopy(lst[i])})
            else:
                drop_cites.append((head, i, drops, v))
    for head, i, drops, v in drop_cites:
        cl = _claims_list(f, head)[i]
        for j in sorted(drops):
            rejected.append({"path": f"{v['path']}.citations[{j}]", "reason": v.get("reason"), "item": cl["citations"][j]})
        cl["citations"] = [x for j, x in enumerate(cl["citations"]) if j not in drops]
    for head, i in sorted(drop_claims, key=lambda x: -x[1]):
        del _claims_list(f, head)[i]
    _refresh_status(f)
    return out, rejected


# ---------- 組裝 ----------

def assemble(c, text):
    """去掉核對不過的出處與說法，保證輸出的卡片 check_card 全數通過。回傳 (卡片, 被移除清單)。"""
    out = copy.deepcopy(c)
    rejected = []
    for _ in range(5):
        fails = check_card(out, text)
        if not fails:
            break
        f = out["fields"]
        # 先移除失敗的出處（由後往前）
        cite_fails = sorted([x for x in fails if x["cite"] is not None], key=lambda x: -x["cite"])
        for x in cite_fails:
            obj = f[x["field"]] if x["idx"] is None else (_claims_list(f, x["field"] if not x["sub"] else f"limitations.{x['sub']}")[x["idx"]])
            rejected.append({"path": x["path"], "why": x["why"], "item": obj["citations"][x["cite"]]})
            del obj["citations"][x["cite"]]
        if cite_fails:
            continue
        # 再處理沒有出處或數字對不上的說法
        claim_drops = []
        for x in fails:
            v = f[x["field"]] if x["idx"] is None else None
            num = x["why"].split(":", 1)[1] if x["why"].startswith("number_not_in_quotes:") else None
            hit = [k for k in ("n_enrolled", "n_analyzed") if v is not None and num is not None
                   and isinstance(v.get(k), (int, float)) and float(v[k]) == float(num)]
            if hit:  # 只是人數欄沒有原文支持：清掉該人數，不整欄作廢
                for k in hit:
                    rejected.append({"path": f"{x['path']}.{k}", "why": x["why"], "item": {k: v[k]}})
                    v[k] = None
                continue
            if x["idx"] is None:
                rejected.append({"path": x["path"], "why": x["why"], "item": {"text": v.get("text")}})
                v.update({"status": "unresolved", "text": "出處核對未通過，見 rejected.md", "citations": []})
                for k in ("n_enrolled", "n_analyzed"):
                    v.pop(k, None)
            else:
                claim_drops.append(x)
        seen = set()
        for x in sorted(claim_drops, key=lambda x: -x["idx"]):
            head = x["field"] if not x["sub"] else f"limitations.{x['sub']}"
            if (head, x["idx"]) in seen:
                continue
            seen.add((head, x["idx"]))
            lst = _claims_list(f, head)
            rejected.append({"path": x["path"], "why": x["why"], "item": lst[x["idx"]]})
            del lst[x["idx"]]
        _refresh_status(f)
    # unresolved 的文字欄位沒有出處是允許的（顯示為判不出來）
    return out, rejected


def missing_refute_paths(c, verdicts):
    """推翻者該判卻沒判（或 verdict 不合法）的 claim 路徑。"""
    ok = {v["path"] for v in verdicts if v.get("verdict") in ("keep", "reject", "partial")}
    paths = [p for p, field, sub, idx, _ in _items(c) if field in CLAIM_FIELDS or field == "limitations"]
    return [p for p in paths if p not in ok]


def title_only_card(work_id):
    """沒有任何內容可解析的短卡（會議摘要等）：只列標題，由腳本產生，不派 agent。"""
    return {"id": work_id, "basis": "title_only", "fields": {k: {"status": "not_in_source", "citations": []} for k in FIELDS}}
