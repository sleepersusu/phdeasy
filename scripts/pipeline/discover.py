"""查詢教授：依本人的研究興趣，找近幾年真的在主導這些研究的人。

「真的在做」的依據（不是只有主題標籤）：
- 論文的標題或摘要寫到這個興趣（OpenAlex title_and_abstract.search，不是 topics 標籤）
- 這個人是最後作者或通訊作者（通常是主持研究的人），中間作者不算
經費看論文上列的資助單位（OpenAlex awards）。
"""
import re


def interest_query(label):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", label or "")).strip().lower()


NOT_PERSON = re.compile(r"\b(lancet|journal|editor(ial)?s?|board|collaborat\w*|consortium|group|investigators|network|committee|team|society|association|study)\b", re.I)


def looks_like_person(name):
    """期刊、研究團隊、合作組織的署名不是人（例：The Lancet Healthy Longevity、GBD Collaborators）。"""
    return bool(name) and not NOT_PERSON.search(name)


def _aid(url):
    return (url or "").rsplit("/", 1)[-1]


def aggregate(results, exclude):
    """results：{興趣: [OpenAlex work]}。回傳候選人（依主導篇數、對到的興趣數、最近年份排序）。"""
    cands = {}
    for label, works in results.items():
        for w in works:
            for a in w.get("authorships") or []:
                if a.get("author_position") != "last" and not a.get("is_corresponding"):
                    continue
                aid = _aid((a.get("author") or {}).get("id"))
                if not aid or aid in exclude or not looks_like_person((a.get("author") or {}).get("display_name")):
                    continue
                c = cands.setdefault(aid, {"id": aid, "name": (a.get("author") or {}).get("display_name"), "papers": {}, "interests": [],
                                           "funders": [], "institution": None, "country": None, "_year": 0})
                inst = (a.get("institutions") or [{}])[0]
                y = w.get("publication_year") or 0
                if y >= c["_year"] and inst.get("display_name"):  # 機構取最近一篇的
                    c["institution"], c["country"], c["_year"] = inst.get("display_name"), inst.get("country_code"), y
                wid = _aid(w.get("id"))
                c["papers"][wid] = {"id": wid, "title": w.get("title"), "year": y, "doi": w.get("doi")}
                if label not in c["interests"]:
                    c["interests"].append(label)
                for aw in w.get("awards") or []:
                    f = aw.get("funder_display_name")
                    if f and f not in c["funders"]:
                        c["funders"].append(f)
    out = []
    for c in cands.values():
        papers = sorted(c.pop("papers").values(), key=lambda p: -(p["year"] or 0))
        c.pop("_year")
        out.append({**c, "papers": papers, "n_led": len(papers), "last_year": papers[0]["year"] if papers else None,
                    "interests": sorted(c["interests"], key=list(results).index)})
    return sorted(out, key=lambda c: (-c["n_led"], -len(c["interests"]), -(c["last_year"] or 0), c["name"] or ""))


def apply_filters(cands, funded=False, min_led=1, active_since=None, country=None, min_h=0, qs_max=None, usnews_max=None,
                  full_funding=False, has_lab=False):
    def within(rank, mx):
        return not mx or (rank is not None and rank <= mx)
    return [c for c in cands if (not funded or c.get("funders")) and c.get("n_led", 0) >= min_led and (c.get("h_index") or 0) >= min_h
            and (not active_since or (c.get("last_year") or 0) >= active_since) and (not country or c.get("country") == country)
            and within(c.get("qs_rank"), qs_max) and within(c.get("usnews_rank"), usnews_max)
            and (not full_funding or best_funding(c) == "full") and (not has_lab or c.get("lab_url"))]


def best_funding(c):
    """全額資助看教授本人掛名的博士學程（有查到就只看學程）；沒查到學程才退回學校層級。"""
    progs = c.get("programs") or []
    if progs:
        vals = [(p.get("funding") or {}).get("value") for p in progs]
        return next((v for v in FUNDING if v in vals), None)
    return c.get("phd_funding")


FUNDING = ("full", "partial", "none", "unknown")


def _src_ok(x):
    return isinstance(x, str) and x.startswith(("https://", "http://"))


def check_enrich(enr):
    """補資訊（AI 上網查的）：每個值都要有出處網址；排名是正整數；獎學金只能是 full／partial／none／unknown。"""
    fails = []
    for inst, d in (enr.get("institutions") or {}).items():
        for k in ("qs", "usnews"):
            v = d.get(k)
            if v is None:
                continue
            if v.get("rank") is not None and not (isinstance(v["rank"], int) and v["rank"] > 0):
                fails.append({"where": f"{inst}.{k}", "why": "bad_rank"})
            if v.get("rank") is not None and not _src_ok(v.get("src")):
                fails.append({"where": f"{inst}.{k}", "why": "no_source"})
        f = d.get("funding")
        if f:
            if f.get("value") not in FUNDING:
                fails.append({"where": f"{inst}.funding", "why": "bad_funding_value"})
            elif f["value"] != "unknown" and not _src_ok(f.get("src")):
                fails.append({"where": f"{inst}.funding", "why": "no_source"})
    for aid, d in (enr.get("people") or {}).items():
        fails += [{**f, "where": f"{aid}.{f['where']}"} for f in check_programs(d.get("programs") or [])]
        if d.get("lab_url") and (not _src_ok(d["lab_url"]) or not _src_ok(d.get("src"))):
            fails.append({"where": f"{aid}.lab_url", "why": "no_source"})
    return fails


def check_programs(progs):
    """教授掛名的博士學程：名稱、官方教員名單（看得到他名字的那頁）出處；資助值與出處。"""
    fails = []
    for i, p in enumerate(progs):
        w = f"programs[{i}]"
        if not (p.get("name") or "").strip():
            fails.append({"where": w, "why": "no_name"})
        elif not _src_ok(p.get("member_src")):
            fails.append({"where": w, "why": "no_member_source"})
        f = p.get("funding") or {"value": "unknown"}
        if f.get("value") not in FUNDING:
            fails.append({"where": w, "why": "bad_funding_value"})
        elif f["value"] != "unknown" and not _src_ok(f.get("src")):
            fails.append({"where": w, "why": "no_source"})
    return fails


def enrich_todo(cands, enr):
    """還沒補過的學校與人（重新查詢後只補新出現的）。"""
    insts, people = enr.get("institutions") or {}, enr.get("people") or {}
    return {"institutions": sorted({c["institution"] for c in cands if c.get("institution") and c["institution"] not in insts}),
            "people": [{"id": c["id"], "name": c["name"] if "name" in c else None, "institution": c.get("institution")}
                       for c in cands if "programs" not in (people.get(c["id"]) or {})]}  # programs 是空清單＝查過、沒有掛名的學程


def combine_enrich(old, new):
    """新補的併進舊的（同一所學校、同一個人：新的欄位蓋過舊的）。"""
    out = {"institutions": dict(old.get("institutions") or {}), "people": dict(old.get("people") or {})}
    for k in ("institutions", "people"):
        for key, v in (new.get(k) or {}).items():
            out[k][key] = {**(out[k].get(key) or {}), **v}
    return out


def merge_enrich(cands, enr):
    """把補到的排名、獎學金、實驗室網址併進候選人（沒查到的留空，篩選時當不符合）。"""
    insts, people = enr.get("institutions") or {}, enr.get("people") or {}
    out = []
    for c in cands:
        i, pz = insts.get(c.get("institution")) or {}, people.get(c["id"]) or {}
        out.append({**c, "qs_rank": (i.get("qs") or {}).get("rank"), "qs_src": (i.get("qs") or {}).get("src"),
                    "usnews_rank": (i.get("usnews") or {}).get("rank"), "usnews_src": (i.get("usnews") or {}).get("src"),
                    "phd_funding": (i.get("funding") or {}).get("value"), "funding_note": (i.get("funding") or {}).get("note"),
                    "funding_src": (i.get("funding") or {}).get("src"),
                    "lab_url": c.get("lab_url") or pz.get("lab_url"), "lab_src": c.get("lab_src") or pz.get("src"),
                    "programs": pz.get("programs")})
    return out
