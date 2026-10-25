"""每位目標教授一份「研究構想草稿」：依本人的 CV（做過、會的）與這位教授目前期間內的經費，擬一個小型、可執行的研究構想。

作者界線（本人 2026-10-26 同意改）：這是 AI 擬的素材，畫面上標「草稿」；寄給教授的版本由本人自己改寫。
擬稿者（LLM）寫各段；腳本核對：
- 每段中英都有、數字一致
- 「對應的經費」只能引用這位教授目前期間內（或期間不明、近 5 年公告）的計畫 key
- 關於教授的說法要引她的文章 id 或計畫 key；關於本人的說法要引 me.json 的段落（cv:…）
"""
import hashlib
import json
from datetime import date

from .i18n import numbers_match

SECTIONS = ["title", "funding", "background", "aims", "methods", "sample", "contribution", "my_role", "timeline", "risks"]
NEED_PROF_REF = {"funding", "background"}
NEED_ME_REF = {"my_role"}
ME_REFS = {"cv:summary", "cv:interests", "cv:education", "cv:publications", "cv:projects", "cv:capabilities"}


def active_grants(grants, today=None, recent_years=5):
    """目前期間內的經費：有起訖日的看迄日是否還沒到；沒有起訖日的看公告／申請年度是否在近 5 年（標「期間不明」）。
    只算本人主持（confirmed）、待確認（pending）、合作者主持（other）；論文致謝提及的不算她的經費。"""
    today = today or date.today().isoformat()
    out = []
    for g in grants:
        if g.get("status") not in ("confirmed", "pending", "other"):
            continue
        end = (g.get("end") or "")[:10]
        year = (g.get("announced") or g.get("round") or g.get("start") or "")[:4]
        if end:
            if end < today:
                continue
            period = f"{(g.get('start') or '')[:10]} – {end}"
        elif year.isdigit() and int(year) >= int(today[:4]) - recent_years:
            period = f"期間不明（{year} 年公告或申請）"
        else:
            continue
        out.append({"key": g["key"], "title": g.get("title") or g.get("funder"), "funder": g.get("funder"), "status": g.get("status"),
                    "role": g.get("target_role"), "period": period, "scheme": g.get("scheme"), "abstract": (g.get("abstract") or "")[:1500],
                    "works": g.get("works") or []})
    return out


def fingerprint(me, grants_active):
    key = json.dumps({"cv": {k: (me or {}).get(k) for k in ("summary", "interests", "capabilities", "publications", "projects", "education")},
                      "grants": [g["key"] for g in grants_active]}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def check_proposal(d, work_ids, active_keys):
    fails = []
    for k in SECTIONS:
        it = (d or {}).get(k)
        if not it:
            fails.append({"path": k, "why": "missing_section"})
            continue
        en, zh = (it.get("en") or "").strip(), (it.get("zh") or "").strip()
        if not en or not zh:
            fails.append({"path": k, "why": "need_en_and_zh"})
            continue
        if not numbers_match(zh, en):
            fails.append({"path": k, "why": "numbers_differ"})
        refs = it.get("refs") or []
        for r in refs:
            if r.startswith("cv:"):
                if r not in ME_REFS:
                    fails.append({"path": k, "why": f"unknown_cv_ref:{r}"})
            elif r.startswith("W"):
                if r not in work_ids:
                    fails.append({"path": k, "why": f"unknown_paper:{r}"})
            elif r not in active_keys:
                fails.append({"path": k, "why": f"grant_not_active:{r}"})
        if k in NEED_PROF_REF and not any(not r.startswith("cv:") for r in refs):
            fails.append({"path": k, "why": "needs_professor_ref"})
        if k in NEED_ME_REF and not any(r.startswith("cv:") for r in refs):
            fails.append({"path": k, "why": "needs_cv_ref"})
    if active_keys and not any(r in active_keys for r in ((d or {}).get("funding") or {}).get("refs") or []):
        fails.append({"path": "funding", "why": "funding_must_cite_active_grant"})
    return fails
