"""教授總覽：事實由腳本彙整；撰寫 agent 只能引用事實與解析卡，每句附 refs，腳本核對 refs 存在、數字對得上。"""
import json
import re
from collections import Counter

from .cards import numbers_in

REF_PATH = re.compile(r"([A-Za-z_]+)|\[(\d+)\]")


def build_facts(professor, works, net, cards, grants, fulltext_ok=None):
    design, countries = Counter(), Counter()
    for c in cards.values():
        f = c.get("fields") or {}
        d, s = f.get("design") or {}, f.get("sample") or {}
        if d.get("status") == "ok" and d.get("type"):
            design[d["type"]] += 1
        if s.get("status") == "ok" and s.get("country"):
            countries[s["country"]] += 1
    by_year = {}
    for w in sorted(works, key=lambda w: (w["year"], w["id"])):
        by_year.setdefault(str(w["year"]), []).append(w["id"])
    pi = [g for g in grants if g.get("status") == "confirmed" and g.get("target_role") in ("pi", "co_pi")]
    return {
        "professor": professor.get("name"),
        "n_works": len(works),
        "n_full_cards": sum(w.get("kind") == "full" for w in works),  # 完整解析卡篇數（不是有全文的篇數）
        "n_fulltext": fulltext_ok,  # 取得免費全文的篇數
        "years": net.get("years") or {},
        "by_year": by_year,
        "roles": net.get("roles") or {},
        "fields": (net.get("topics") or {}).get("field", [])[:8],
        "subfields": (net.get("topics") or {}).get("subfield", [])[:10],
        "topics": (net.get("topics") or {}).get("topic", [])[:12],
        "coauthors_total": net.get("coauthors_total", 0),
        "top_coauthors": [{"name": s["name"], "n": s["n"], "works": s["works"], "years": s.get("years")} for s in (net.get("coauthors") or [])[:10]],
        "design_types": dict(sorted(design.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sample_countries": dict(sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))),
        "grants_pi": [{"award_id": g.get("award_id"), "title": g.get("title"), "funder": g.get("funder"), "start": g.get("start"),
                       "end": g.get("end"), "active_2026": (g.get("end") or "") >= "2026", "works": g.get("works", [])} for g in pi],
        "grants_other_n": sum(g.get("status") == "other" for g in grants),
        "grants_ack_funders": sorted({g.get("funder") for g in grants if g.get("status") == "acknowledged" and g.get("funder")}),
    }


def fact_lookup(facts, path):
    cur = facts
    for name, idx in REF_PATH.findall(path):
        try:
            cur = cur[name] if name else cur[int(idx)]
        except (KeyError, IndexError, TypeError):
            return None
    return cur


def _nums(obj):
    return {float(n) for n in numbers_in(json.dumps(obj, ensure_ascii=False))}


def check_draft(draft, facts, work_ids, cards=None, works=None):
    fails = []
    for s in draft.get("sections", []):
        for i, cl in enumerate(s.get("claims", [])):
            path = f"{s.get('key')}[{i}]"
            refs = cl.get("refs") or []
            if not refs:
                fails.append({"path": path, "why": "no_refs", "text": cl.get("text")})
                continue
            backing = set()
            for r in refs:
                if r.startswith("fact:"):
                    v = fact_lookup(facts, r[5:])
                    if v is None:
                        fails.append({"path": path, "why": f"unknown_ref:{r}", "text": cl.get("text")})
                    else:
                        backing |= _nums(v)
                        if isinstance(v, dict) and v.get("name") and v["name"].split()[-1] not in (cl.get("text") or ""):
                            fails.append({"path": path, "why": f"ref_name_mismatch:{v['name']}", "text": cl.get("text")})
                elif r in work_ids:
                    if cards and r in cards:
                        backing |= _nums(cards[r])
                    if works and r in works:
                        backing |= _nums({"year": works[r].get("year")})
                else:
                    fails.append({"path": path, "why": f"unknown_ref:{r}", "text": cl.get("text")})
            for n in dict.fromkeys(numbers_in(cl.get("text"))):
                if float(n) not in backing:
                    fails.append({"path": path, "why": f"number_not_in_refs:{n}", "text": cl.get("text")})
    return fails


def render_profile_md(professor, facts, draft):
    lines = [f"# {professor.get('name')} 研究檔案（2022–2026）", "",
             "每句後的〔〕是出處：W 開頭為文章 id（見 `out/papers/`），fact: 為腳本彙整的數字（見 `work/profile/facts.json`）。", ""]
    for s in draft.get("sections", []):
        lines += [f"## {s.get('title')}", ""]
        for cl in s.get("claims", []):
            lines.append(f"- {cl.get('text')} 〔{'、'.join(cl.get('refs') or [])}〕")
        lines.append("")
    return "\n".join(lines)


# ---- 數字類章節由腳本套固定句型（本人 2026-10-26：不用 AI 寫、也不用推翻）----
SECTION_ORDER = ("snapshot", "focus", "evolution", "methods", "collaboration", "grants", "gaps_next", "questions")
TEMPLATE_KEYS = ("snapshot", "methods", "collaboration", "grants")
TITLES = {"snapshot": "一頁速覽", "focus": "研究主線", "evolution": "近五年的演變", "methods": "常用研究設計與樣本",
          "collaboration": "合作網絡", "grants": "研究計畫", "gaps_next": "文章自己指出的下一步", "questions": "可以問教授的問題"}
DESIGN_ZH = {"rct": "隨機對照試驗", "pilot-rct": "前導隨機對照試驗", "quasi-experimental": "準實驗", "single-arm": "單組介入",
             "cohort": "世代研究", "cross-sectional": "橫斷研究", "case-control": "病例對照", "qualitative": "質性研究",
             "mixed-methods": "混合方法", "systematic-review": "系統性回顧", "scoping-review": "範域回顧", "meta-analysis": "統合分析",
             "secondary-analysis": "次級分析", "protocol": "研究計畫書", "modeling": "建模", "machine-learning": "機器學習",
             "text-mining": "文字探勘", "other": "其他"}


def _c(text, *refs):
    return {"text": text, "refs": list(refs), "auto": True}


def template_sections(f, today=None):
    from datetime import date
    today = today or date.today().isoformat()
    live = lambda g: (g.get("end") or "")[:10] >= today  # 迄日還沒到才算仍在期間內
    yrs = sorted((f.get("years") or {}).items())
    r = f.get("roles") or {}
    snap = [_c(f"2022–2026 年共 {f.get('n_works', 0)} 篇" + (f"，年度篇數為 {'、'.join(f'{y} 年 {n} 篇' for y, n in yrs)}。" if yrs else "。"), "fact:n_works", "fact:years"),
            _c(f"擔任第一作者 {r.get('first', 0)} 篇、最後作者 {r.get('last', 0)} 篇、中間作者 {r.get('middle', 0)} 篇，另有 {r.get('corresponding', 0)} 篇標為通訊作者。", "fact:roles")]
    if f.get("fields"):
        snap.append(_c("主要領域：" + "、".join(f"{n}（{c} 篇）" for n, c in f["fields"][:3]) + "。", "fact:fields"))
    act = [g for g in f.get("grants_pi") or [] if live(g)]
    snap.append(_c(("資料庫確認她主持、目前仍在期間內的計畫：" + "、".join(g.get("award_id") or g.get("title") or "" for g in act) + "。") if act
                   else "資料庫查不到她主持、目前仍在期間內的計畫。", "fact:grants_pi"))
    meth = []
    if f.get("design_types"):
        meth.append(_c("必讀文章的研究設計：" + "、".join(f"{DESIGN_ZH.get(k, k)} {v} 篇" for k, v in f["design_types"].items()) + "。", "fact:design_types"))
    if f.get("sample_countries"):
        meth.append(_c("樣本國家：" + "、".join(f"{k}（{v} 篇）" for k, v in f["sample_countries"].items()) + "。", "fact:sample_countries"))
    if not meth:
        meth.append(_c(f"必讀文章 {f.get('n_full_cards', 0)} 篇，研究設計與樣本見各篇解析。", "fact:n_full_cards"))
    collab = [_c(f"近五年共有 {f.get('coauthors_total', 0)} 位合作者。", "fact:coauthors_total")]
    for i, c in enumerate((f.get("top_coauthors") or [])[:6]):
        ys = sorted((c.get("years") or {}).keys())
        collab.append(_c(f"{c['name']}：合著 {c['n']} 篇" + (f"（{ys[0]}–{ys[-1]}）" if ys else "") + "。", f"fact:top_coauthors[{i}]"))
    grants = []
    for i, g in enumerate(f.get("grants_pi") or []):
        period = f"{(g.get('start') or '?')[:10]} 至 {(g.get('end') or '?')[:10]}"
        grants.append(_c(f"{g.get('award_id') or ''}（{g.get('funder') or '資助單位未提及'}，{period}）：{g.get('title') or ''}" + ("，仍在期間內。" if live(g) else "，已結束。"),
                         f"fact:grants_pi[{i}]"))
    if not grants:
        grants.append(_c("資料庫查不到她主持的計畫。", "fact:grants_pi"))
    if f.get("grants_other_n"):
        grants.append(_c(f"另有 {f['grants_other_n']} 筆是合作者主持、她參與的計畫。", "fact:grants_other_n"))
    return [{"key": k, "title": TITLES[k], "claims": v} for k, v in (("snapshot", snap), ("methods", meth), ("collaboration", collab), ("grants", grants))]


def merge_sections(template, draft):
    """腳本章節＋撰寫者章節（撰寫者寫了腳本章節的 key 也不用），照固定順序。"""
    by = {s["key"]: s for s in (draft or {}).get("sections", []) if s.get("key") not in TEMPLATE_KEYS}
    by.update({s["key"]: s for s in template})
    return [by[k] for k in SECTION_ORDER if k in by] + [s for k, s in by.items() if k not in SECTION_ORDER]
