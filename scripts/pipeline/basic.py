"""教授基本資訊（教授首頁頂端）：ORCID 公開紀錄的職稱、系所、學校、經歷、學歷、網址；OpenAlex 的學術指標。
只收來源有寫的欄位，沒寫就留空，不推測。"""


def _year(d):
    return ((d or {}).get("year") or {}).get("value")


def _affs(acts, kind):
    out = []
    for g in ((acts or {}).get(f"{kind}s") or {}).get("affiliation-group") or []:
        for s in g.get("summaries") or []:
            x = s.get(f"{kind}-summary") or {}
            org = x.get("organization") or {}
            out.append({"title": (x.get("role-title") or "").strip() or None, "department": (x.get("department-name") or "").strip() or None,
                        "institution": org.get("name"), "country": (org.get("address") or {}).get("country"),
                        "since": _year(x.get("start-date")), "until": _year(x.get("end-date"))})
    return out


def parse_orcid(record):
    p = (record or {}).get("person") or {}
    acts = (record or {}).get("activities-summary") or {}
    emps = _affs(acts, "employment")
    current = next((e for e in emps if not e["until"]), None)
    pos = {k: current[k] for k in ("title", "department", "institution", "country", "since")} if current else None
    urls = [{"name": u.get("url-name"), "url": (u.get("url") or {}).get("value")}
            for u in (p.get("researcher-urls") or {}).get("researcher-url") or []]
    return {"position": pos, "employments": emps, "educations": _affs(acts, "education"),
            "bio": ((p.get("biography") or {}).get("content") or "").strip() or None,
            "keywords": [k.get("content") for k in (p.get("keywords") or {}).get("keyword") or [] if k.get("content")],
            "urls": [u for u in urls if (u["url"] or "").startswith(("https://", "http://"))]}


def parse_openalex_author(a):
    a = a or {}
    st = a.get("summary_stats") or {}
    return {"works_count": a.get("works_count"), "cited_by_count": a.get("cited_by_count"),
            "h_index": st.get("h_index"), "i10_index": st.get("i10_index"),
            "topics": [t.get("display_name") for t in (a.get("topics") or [])[:8] if t.get("display_name")],
            "as_of": (a.get("updated_date") or "")[:10] or None}
