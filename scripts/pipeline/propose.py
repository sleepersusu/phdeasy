"""每位目標教授的「研究計畫書草稿」：依這位教授的研究方向與目前期間內的經費、本人的興趣與做得到（或可能做得到）的事，
擬 2–3 個不同方向的版本，每版附信心程度；分段照本人與 Liliana 討論、她改過的計畫書。

作者界線（本人 2026-10-26 同意改）：這是 AI 擬的素材，畫面上標「草稿」；寄給教授的版本由本人自己改寫。
擬稿者（LLM）寫各段；腳本核對：
- 2–3 個版本、方向不重複；每段中英都有、數字一致；不能用誇大的字
- 「資源與經費」只能引用這位教授目前期間內（或期間不明、近 5 年公告）的計畫 key；信心「高」要有她本人主持的期間內經費
- 背景與缺口要引她的文章 id 或計畫 key；「我做得到／可能做得到」要引 me.json 的段落（cv:…）
"""
import hashlib
import json
from datetime import date

from .i18n import numbers_match

ME_REFS = {"cv:summary", "cv:interests", "cv:education", "cv:publications", "cv:projects", "cv:capabilities"}
LEVELS = ("high", "medium", "low")
# 每個版本照 Liliana 改過的計畫書分段：題目、摘要、1 背景與缺口、2 目的、3 研究與方法、4 貢獻、5 時程、6 資源與經費；
# 另加：方向、信心程度、我做得到／可能做得到的、風險
TEXT_KEYS = ["direction", "title", "subtitle", "synopsis", "rationale", "aim", "contribution", "timeline", "resources", "risks"]
NEED_PROF_REF = {"rationale"}
# 本人要求不要寫得太誇張：這些字一出現就擋下
OVERCLAIM = ["groundbreaking", "revolutionary", "first-ever", "unprecedented", "game-changing", "transformative", "guarantee",
             "首創", "革命性", "前所未有", "顛覆", "保證", "劃時代"]

def finalized_with(me, slug):
    """本人跟這位教授討論出來的計畫書已定案（本人 2026-10-26）：只放定案版，不再擬 AI 版本。"""
    return bool(me) and bool(me.get("proposal")) and me.get("proposal_with") == slug


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


def _bi(path, it, work_ids, active, fails, need_prof=False, need_cv=False):
    if not isinstance(it, dict):
        fails.append({"path": path, "why": "missing_section"})
        return
    en, zh = (it.get("en") or "").strip(), (it.get("zh") or "").strip()
    if not en or not zh:
        fails.append({"path": path, "why": "need_en_and_zh"})
        return
    if not numbers_match(zh, en):
        fails.append({"path": path, "why": "numbers_differ"})
    low = en.lower()
    for w in OVERCLAIM:
        if w in low or w in zh:
            fails.append({"path": path, "why": f"overclaim:{w}"})
    refs = it.get("refs") or []
    for r in refs:
        if r.startswith("cv:"):
            if r not in ME_REFS:
                fails.append({"path": path, "why": f"unknown_cv_ref:{r}"})
        elif r.startswith("W"):
            if r not in work_ids:
                fails.append({"path": path, "why": f"unknown_paper:{r}"})
        elif r not in active:
            fails.append({"path": path, "why": f"grant_not_active:{r}"})
    if need_prof and not any(not r.startswith("cv:") for r in refs):
        fails.append({"path": path, "why": "needs_professor_ref"})
    if need_cv and not any(r.startswith("cv:") for r in refs):
        fails.append({"path": path, "why": "needs_cv_ref"})


def check_version(v, work_ids, active):
    """一個版本；active 是 {key: 期間內的經費}。"""
    fails = []
    v = v or {}
    for k in TEXT_KEYS:
        _bi(k, v.get(k), work_ids, active, fails, need_prof=k in NEED_PROF_REF)
    conf = v.get("confidence") or {}
    if conf.get("level") not in LEVELS:
        fails.append({"path": "confidence.level", "why": "bad_confidence_level"})
    _bi("confidence", conf, work_ids, active, fails)
    gaps = v.get("gaps") or []
    if not 1 <= len(gaps) <= 3:
        fails.append({"path": "gaps", "why": "need_1_to_3_gaps"})
    for i, g in enumerate(gaps):
        _bi(f"gaps[{i}]", g, work_ids, active, fails, need_prof=True)
    objs = v.get("objectives") or []
    if not objs:
        fails.append({"path": "objectives", "why": "missing_section"})
    for i, o in enumerate(objs):
        _bi(f"objectives[{i}]", o, work_ids, active, fails)
    studies = v.get("studies") or []
    if not 1 <= len(studies) <= 3:
        fails.append({"path": "studies", "why": "need_1_to_3_studies"})
    for i, st in enumerate(studies):
        for k in ("name", "aim", "methods", "analysis"):
            _bi(f"studies[{i}].{k}", (st or {}).get(k), work_ids, active, fails)
    fit = v.get("fit") or {}
    for k, why in (("can_do", "need_can_do"), ("could_do", "need_could_do")):
        items = fit.get(k) or []
        if not items:
            fails.append({"path": f"fit.{k}", "why": why})
        for i, it in enumerate(items):
            _bi(f"fit.{k}[{i}]", it, work_ids, active, fails, need_cv=True)
    res = [r for r in ((v.get("resources") or {}).get("refs") or []) if r in active]
    no_fit = bool((v.get("resources") or {}).get("no_fitting_grant"))  # 期間內的經費都不對題：照實寫，不硬套
    if no_fit and res:
        fails.append({"path": "resources", "why": "no_fitting_grant_but_cites_grant"})
    if active and not res and not no_fit:
        fails.append({"path": "resources", "why": "resources_must_cite_active_grant"})
    if conf.get("level") == "high" and not any(active[r].get("status") == "confirmed" for r in res):
        fails.append({"path": "confidence.level", "why": "high_confidence_without_her_grant"})
    return fails


def check_draft(d, work_ids, active):
    vs = (d or {}).get("versions") or []
    fails = []
    if not 2 <= len(vs) <= 3:
        fails.append({"path": "versions", "why": "need_2_to_3_versions"})
    ids = [v.get("id") for v in vs]
    if len(ids) != len(set(ids)):
        fails.append({"path": "versions", "why": "version_id_duplicate"})
    dirs = [((v.get("direction") or {}).get("zh") or "").strip() for v in vs]
    if len(dirs) != len(set(dirs)):
        fails.append({"path": "versions", "why": "direction_duplicate"})
    for i, v in enumerate(vs):
        fails += [{**f, "path": f"versions[{i}].{f['path']}"} for f in check_version(v, work_ids, active)]
    return fails
