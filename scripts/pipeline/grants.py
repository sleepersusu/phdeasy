"""研究計畫：編號正規化、身分比對（姓名＋機構）、NIH 資料整理、致謝段擷取、合併。全部是純函式。"""
import re

from .quotes import _sections

NIH_CORE = re.compile(r"^\d?(?:[A-Z][A-Z0-9]\d)?([A-Z]{2})(\d{6})$")
NIH_IN_TEXT = re.compile(r"\b\d?([A-Z][A-Z0-9]\d)\s?-?\s?([A-Z]{2})\s?-?\s?(\d{6})\b")
ACK_HEAD = re.compile(r"^\s*(#+\s*)?(acknowledg(e)?ments?|funding( information| sources?)?|financial (support|disclosure)|sources? of funding)\b", re.I)
STOP_HEAD = re.compile(r"^\s*(#+\s*)?(conflicts? of interest|declaration|references|author(s')? contributions?|abbreviations|data (availability|sharing)|competing interests|ethics|supplementary)\b", re.I)
FUND_WORDS = re.compile(r"(funded by|supported (in part )?by|grant (no|number|#)|award (no|number)|\bfunding\b)", re.I)
CONTEXT = 2  # 關鍵字行前後各帶幾行
STATUS_RANK = {"confirmed": 0, "pending": 1, "acknowledged": 2, "other": 3}


NHMRC_RE = re.compile(r"NHMRC|NATIONAL HEALTH AND MEDICAL RESEARCH COUNCIL", re.I)


def normalize_award(x, funder=None):
    if not x:
        return None
    up = x.strip().upper()
    m = re.fullmatch(r"(?:NHMRC\s*)?(?:APP|GNT|ID)?\s*#?\s*(\d{6,7})", up)
    if m and (up.startswith("NHMRC") or NHMRC_RE.search(funder or "")):
        return f"ID:NHMRC{m.group(1)}"
    raw = re.sub(r"[\u2010-\u2015\u2212]", "-", up)
    s = re.sub(r"-\d{2}([A-Z]\d+)?$", "", raw)
    s = re.sub(r"[\s\-_/#.]", "", s)
    m = NIH_CORE.match(s)
    if m:
        return f"NIH:{m.group(1)}{m.group(2)}"
    inside = nih_numbers(raw)  # 例 "UCSF CTSI Grant Number UL1 TR000004"
    if len(inside) == 1:
        return f"NIH:{inside[0][-8:]}"
    m = re.fullmatch(r"[A-Z]{2,5}(\d{7})", s)  # NSF 學門前綴，例 CMMI1450963 = 1450963
    if m:
        return f"ID:{m.group(1)}"
    return f"ID:{s}"


def funder_key(name):
    import unicodedata

    name = unicodedata.normalize("NFKC", name or "")  # ﬁ 連字 → fi
    return "FUNDER:" + " ".join(re.sub(r"[^\w]+", " ", name.lower()).split())


def nih_core(x):
    """完整 NIH 核心編號（活動代碼＋機構代碼＋序號），RePORTER 回查要用；缺活動代碼回 None。"""
    s = re.sub(r"-\d{2}([A-Z]\d+)?$", "", (x or "").strip().upper())
    s = re.sub(r"[\s\-_/]", "", s)
    m = re.match(r"^\d?([A-Z][A-Z0-9]\d)([A-Z]{2})(\d{6})$", s)
    return "".join(m.groups()) if m else None


def nih_numbers(text):
    out = []
    for m in NIH_IN_TEXT.finditer(text or ""):
        n = "".join(m.groups())
        if n not in out:
            out.append(n)
    return out


def _tokens(name):
    name = (name or "").replace(".", " ").replace(",", " , ")
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    return [t for t in name.lower().replace(",", " ").split()]


def name_match(api_name, target):
    a, t = _tokens(api_name), _tokens(target)
    if not a or not t or t[-1] not in a:
        return False
    first = t[0]
    rest = [x for x in a if x != t[-1]]
    return any(x == first or (len(x) == 1 and x == first[0]) for x in rest)


def _inst(s):
    return " ".join(re.sub(r"[^\w]+", " ", (s or "").lower()).split())


def inst_match(a, b):
    """b 可以是單一機構或機構清單（目標作者可能同時隸屬多個機構）。"""
    if isinstance(b, (list, tuple, set)):
        return any(inst_match(a, x) for x in b)
    a, b = _inst(a), _inst(b)
    return bool(a and b) and (a == b or a in b or b in a)


def nih_projects(resp, target_name, target_inst):
    groups = {}
    for r in resp.get("results", []):
        key = normalize_award(r["core_project_num"])
        g = groups.setdefault(key, {"rows": {}, "all": []})
        g["rows"].setdefault(r["project_num"], r)
        g["all"].append(r)
    out = []
    for key, g in groups.items():
        rows = list(g["rows"].values())
        parents = [x for x in g["all"] if not x.get("subproject_id")]
        if parents:  # 中心計畫：名稱、PI、金額以母計畫為準，子計畫不重複加
            rows = list({x["project_num"]: x for x in parents}.values())
        r = rows[0]
        pis = []
        for row in rows:
            for p in row.get("principal_investigators") or []:
                n = " ".join(p["full_name"].split())
                if n not in pis:
                    pis.append(n)
        is_target = any(name_match(p, target_name) for p in pis)
        inst_ok = any(inst_match((row.get("organization") or {}).get("org_name"), target_inst) for row in rows)
        if is_target:
            role, status = "pi", ("confirmed" if inst_ok else "pending")
        else:
            role, status = "other_pi", "other"
        out.append(
            {
                "key": key,
                "award_id": r["core_project_num"],
                "funder": ((r.get("agency_ic_admin") or {}).get("abbreviation")) or "NIH",
                "title": r.get("project_title"),
                "pi_names": pis,
                "org": (r.get("organization") or {}).get("org_name"),
                "target_role": role,
                "status": status,
                "start": (min(x.get("project_start_date") or "" for x in rows) or "")[:10] or None,
                "end": (max(x.get("project_end_date") or "" for x in rows) or "")[:10] or None,
                "fiscal_years": sorted({x["fiscal_year"] for x in rows}),
                "total_award": sum(x.get("award_amount") or 0 for x in rows),
                "abstract": r.get("abstract_text"),
            }
        )
    return out


def ack_snippets(text, max_chars=1500):
    """每個位置最多一段：致謝／補助標題之後到下一個停止標題，或含補助字眼／NIH 編號的段落。"""
    out = []
    in_ack = False
    for loc, body in _sections(text):
        lines = body.strip("\n").split("\n")
        keep_idx, capturing = set(), in_ack and loc.startswith("§")
        for i, line in enumerate(lines):
            m = ACK_HEAD.match(line)
            if m:
                capturing, in_ack = True, True
                if len(line[m.end():].strip(" :.-")) > 3:  # 標題後同一行接著內文（例 "Funding: This work…"）
                    keep_idx.add(i)
                continue
            if STOP_HEAD.match(line) or (line.startswith("## ") and not ACK_HEAD.match(line)):
                capturing, in_ack = False, False
                continue
            if capturing:
                keep_idx.add(i)
            elif FUND_WORDS.search(line) or nih_numbers(line):
                keep_idx.update(j for j in range(i - CONTEXT, i + CONTEXT + 1)
                                if 0 <= j < len(lines) and not ACK_HEAD.match(lines[j]) and not STOP_HEAD.match(lines[j]))
        keep = [lines[i].strip() for i in sorted(keep_idx)]
        keep = [re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", " ".join(keep))] if keep else []  # 斷行連字號接回
        # XML：標題行在 marker 前（## Acknowledgments 後接 [§N]）
        if not keep and loc.startswith("§") and in_ack:
            keep = [body.strip()]
        if keep:
            out.append({"loc": loc, "text": " ".join(" ".join(keep).split())[:max_chars]})
        if loc.startswith("§"):
            tail = body.rstrip().split("\n")[-1] if body.strip() else ""
            if ACK_HEAD.match(tail):
                in_ack = True
            elif tail.startswith("## "):
                in_ack = False
    return out


def _add(acc, key, base):
    if key not in acc:
        acc[key] = {**base, "works": [], "evidence": []}
    return acc[key]


def merge_grants(projects, openalex_awards, mentions):
    acc = {}
    for p in projects:
        g = _add(acc, p["key"], dict(p))
        g["evidence"].append({"type": p.get("source", "api")})
    for a in openalex_awards:
        key = normalize_award(a.get("award_id"), a.get("funder")) or funder_key(a.get("funder"))
        g = _add(acc, key, {"key": key, "award_id": a.get("award_id"), "funder": a.get("funder"), "title": None,
                            "target_role": "acknowledged", "status": "acknowledged", "pi_names": []})
        g["works"].append(a["work_id"])
        g["evidence"].append({"type": "openalex", "work_id": a["work_id"]})
    for m in mentions:
        if m.get("check") != "ok":
            continue
        ids = [x.strip() for x in re.split(r"[,;]|\band\b", m.get("award_id") or "") if x.strip()] or [None]
        for aid in ids:  # 一句致謝列多個編號時拆成多筆
            key = normalize_award(aid, m.get("funder")) if aid else funder_key(m.get("funder"))
            g = _add(acc, key, {"key": key, "award_id": aid, "funder": m.get("funder"), "title": None,
                                "target_role": "acknowledged", "status": "acknowledged", "pi_names": []})
            g["works"].append(m["work_id"])
            g["evidence"].append({"type": "ack", "work_id": m["work_id"], "quote": m["quote"], "loc": m["loc"]})
    for g in acc.values():
        g["works"] = sorted(set(g["works"]))
    return sorted(acc.values(), key=lambda g: (STATUS_RANK.get(g["status"], 9), g["key"]))


def _us_date(s):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def nsf_projects(resp, target_name, target_inst):
    out = []
    for a in (resp.get("response") or {}).get("award", []):
        pi = f"{a.get('piFirstName', '')} {a.get('piLastName', '')}".strip()
        copis = [" ".join(re.sub(r"~\d+", "", c).split()) for c in a.get("coPDPI") or []]
        if name_match(pi, target_name):
            role = "pi"
        elif any(name_match(c, target_name) for c in copis):
            role = "co_pi"
        else:
            role = "other_pi"
        inst_ok = inst_match(a.get("awardeeName", "").replace("-", " "), target_inst)
        status = "other" if role == "other_pi" else ("confirmed" if inst_ok or role == "co_pi" else "pending")
        out.append({"key": f"ID:NSF{a['id']}", "award_id": f"NSF {a['id']}", "funder": "NSF", "title": a.get("title"),
                    "pi_names": [pi] + copis, "org": a.get("awardeeName"), "target_role": role, "status": status,
                    "start": _us_date(a.get("startDate")), "end": _us_date(a.get("expDate")),
                    "total_award": float(a.get("fundsObligatedAmt") or 0), "abstract": a.get("abstractText")})
    return out


def check_mention(text, m):
    from .quotes import check_quote

    ok, why = check_quote(text, m.get("quote"), m.get("loc"))
    if not ok:
        return why
    if m.get("award_id"):
        q = re.sub(r"[\s\-]", "", m["quote"].upper())
        core = re.sub(r"[\s\-]", "", m["award_id"].upper())
        if core not in q and normalize_award(m["award_id"]).split(":", 1)[1] not in q:
            return "award_id_not_in_quote"
    return "ok"


VERDICTS = {"keep", "reject", "unresolved"}


def apply_verdicts(grants, verdicts):
    """回傳 (保留, 推翻, 待確認, 漏判 keys)。沒有 API 證據的不能被改成 pi／co_pi，改判待確認。"""
    ref = {v["key"]: v for v in verdicts if v.get("verdict") in VERDICTS}
    missing = [g["key"] for g in grants if g["key"] not in ref]
    final, rejected, unresolved = [], [], []
    for g in grants:
        v = ref.get(g["key"])
        if v is None:
            continue
        g = {**g, "refute": {"verdict": v["verdict"], "reason": v.get("reason"), "evidence": v.get("evidence")}}
        if v["verdict"] == "reject":
            rejected.append(g)
            continue
        fix = v.get("role_fix")
        if fix:
            if fix in ("pi", "co_pi") and g["status"] in ("acknowledged",):
                g["status"] = "pending"
                g["refute"]["reason"] = f"{v.get('reason') or ''}（推翻者建議改為 {fix}，但沒有 API 證據，改列待確認）"
                unresolved.append(g)
                final.append(g)
                continue
            g["target_role"] = fix
            if fix == "other_pi" and g["status"] == "confirmed":
                g["status"] = "other"
        if v["verdict"] == "unresolved":
            g["status"] = "pending"
            unresolved.append(g)
        final.append(g)
    return final, rejected, unresolved, missing


def _col(row, *keys, exclude=()):
    for h, v in row.items():
        hl = str(h).lower()
        if any(k in hl for k in keys) and not any(x in hl for x in exclude):
            return v
    return None


def _money(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def currency(g):
    """金額幣別：NIH／NSF 是美元，NHMRC／ARC 是澳幣；其他來源不知道就不寫。"""
    src = (g.get("source") or "").lower()
    if src in ("nhmrc", "arc"):
        return "AUD"
    if src in ("nih", "nih_lookup", "nsf") or (g.get("key") or "").startswith(("NIH:", "NSF:")):
        return "USD"
    return None


def nhmrc_projects(rows, target_name, target_inst, round_year):
    """NHMRC 各年度 Summary of results（欄名每年不同，以關鍵字找欄）。CIA 吻合＝pi；其他 CI 欄吻合＝co_pi。"""
    out = []
    for r in rows:
        cia = str(_col(r, "cia", "chief investigator a") or "")
        others = [str(v) for h, v in r.items() if v and "investigator" in str(h).lower()
                  and not any(k in str(h).lower() for k in ("cia", "chief investigator a"))]
        others_names = [x.strip() for v in others for x in re.split(r"[;,]", v) if x.strip()]
        if name_match(cia, target_name):
            role = "pi"
        elif any(name_match(x, target_name) for x in others_names):
            role = "co_pi"
        else:
            continue
        inst = str(_col(r, "admin") or "")
        app = str(_col(r, "app id", "application id", "app_id", "grant id") or "").split(".")[0]
        start = _col(r, "start")
        ann = _col(r, "announced")
        scheme = " – ".join(str(x).strip() for x in (_col(r, "scheme", "grant type"), _col(r, "sub type")) if x and str(x).strip()) or None
        out.append({"key": f"ID:NHMRC{app}", "award_id": f"NHMRC {app}", "funder": "NHMRC",
                    "title": _col(r, "title"), "pi_names": [cia] + [x for x in others_names if x != cia][:8], "org": inst,
                    "target_role": role, "status": "confirmed" if inst_match(inst, target_inst) else "pending",
                    "scheme": scheme, "announced": str(ann)[:10] if ann else None,
                    "start": str(start).split(".")[0] if start else None,
                    "end": None, "round": str(round_year), "total_award": _money(_col(r, "total", "budget", "amount")),
                    "abstract": _col(r, "summary", "plain", "abstract")})
    return out
