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


def apply_filters(cands, funded=False, min_led=1, active_since=None, country=None, min_h=0):
    return [c for c in cands if (not funded or c.get("funders")) and c.get("n_led", 0) >= min_led and (c.get("h_index") or 0) >= min_h
            and (not active_since or (c.get("last_year") or 0) >= active_since) and (not country or c.get("country") == country)]
