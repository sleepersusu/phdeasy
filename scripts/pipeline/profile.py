"""教授總覽：事實由腳本彙整；撰寫 agent 只能引用事實與解析卡，每句附 refs，腳本核對 refs 存在、數字對得上。"""
import json
import re
from collections import Counter

from .cards import numbers_in

REF_PATH = re.compile(r"([A-Za-z_]+)|\[(\d+)\]")


def build_facts(professor, works, net, cards, grants):
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
        "n_full": sum(w.get("kind") == "full" for w in works),
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
