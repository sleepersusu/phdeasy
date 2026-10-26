"""教授學歷（本人 2026-10-26：ORCID 很多人沒填）。
- UCSF：官方 Profiles API（https://api.profiles.ucsf.edu/json/v2/?ProfilesURLName=<名>）的 Education_Training，腳本直接讀
- 其他學校：博士學程查詢者打開官方個人頁時一起讀；個人頁沒寫再看本人放的 CV（PDF）、LinkedIn 公開頁（不登入）
每筆都要有出處網址。寫在 runs/<slug>/out/education.json：{"fetched", "source", "items": [{degree, institution, field, year, src}]}
"""
import re


def ucsf_name(url):
    m = re.match(r"https?://profiles\.ucsf\.edu/([A-Za-z0-9._-]+)/?$", url or "")
    return m.group(1) if m else None


def parse_ucsf(api, profile_url):
    p = ((api or {}).get("Profiles") or [{}])[0]
    out = []
    for e in p.get("Education_Training") or []:
        out.append({"degree": (e.get("degree") or "").strip(), "institution": (e.get("organization") or "").strip(),
                    "field": " ".join((e.get("department_or_school") or "").split()) or None, "year": (e.get("end_date") or None),
                    "src": profile_url})
    return [x for x in out if x["degree"] or x["institution"]]


def check_education(items):
    fails = []
    for i, e in enumerate(items or []):
        if not (e.get("degree") or "").strip() and not (e.get("institution") or "").strip():
            fails.append({"where": f"education[{i}]", "why": "empty"})
        elif not str(e.get("src") or "").startswith(("https://", "http://")):
            fails.append({"where": f"education[{i}]", "why": "no_source"})
    return fails
