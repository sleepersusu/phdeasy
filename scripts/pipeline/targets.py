"""目標學校 → 系所 → 教授（本人 2026-10-26）。存在 runs/_me/targets.json（只在本機與本人的雲端硬碟）：
{"schools": [{"id", "name", "departments": [{"id", "name", "url", "members": [教授 slug], "faculty": {"fetched", "src", "people": [...]}}]}]}
本人新增學校與系所後，背景查那個系所的教員名單（每人要有官方個人頁），本人勾選後才開始建檔。
"""
import re
import unicodedata


def _id(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "x"


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def add_target(t, school, department, url=None):
    """新增（或找到已有的）學校與系所，回傳系所 id。"""
    if not (school or "").strip() or not (department or "").strip():
        raise ValueError("學校和系所都要填")
    schools = t.setdefault("schools", [])
    sc = next((s for s in schools if _norm(s["name"]) == _norm(school)), None)
    if not sc:
        sid = _id(school)
        while any(s["id"] == sid for s in schools):
            sid += "-x"
        sc = {"id": sid, "name": school.strip(), "departments": []}
        schools.append(sc)
    d = next((d for d in sc["departments"] if _norm(d["name"]) == _norm(department)), None)
    if not d:
        did = f"{sc['id']}--{_id(department)}"
        d = {"id": did, "name": department.strip(), "url": (url or "").strip() or None, "members": [], "faculty": None}
        sc["departments"].append(d)
    elif url and not d.get("url"):
        d["url"] = url.strip()
    return d["id"]


def find_dept(t, dept_id):
    for s in t.get("schools") or []:
        for d in s["departments"]:
            if d["id"] == dept_id:
                return s, d
    raise ValueError(f"沒有這個系所：{dept_id}")


def assign(t, dept_id, slug):
    """把教授放進系所（一位教授只在一個系所）。"""
    _, target = find_dept(t, dept_id)
    for s in t.get("schools") or []:
        for d in s["departments"]:
            if slug in d["members"] and d is not target:
                d["members"].remove(slug)
    if slug not in target["members"]:
        target["members"].append(slug)


def remove_target(t, dept_id):
    """拿掉系所（裡面的教授檔案都留著，只是回到「未分系所」）；學校沒有系所了也一起拿掉。"""
    s, d = find_dept(t, dept_id)
    s["departments"].remove(d)
    if not s["departments"]:
        t["schools"].remove(s)


def _src_ok(x):
    return isinstance(x, str) and x.startswith(("https://", "http://"))


def check_faculty(f):
    """查到的教員名單：名單頁出處；每人姓名與官方個人頁；不重複。"""
    fails = []
    if not _src_ok((f or {}).get("src")):
        fails.append({"where": "src", "why": "no_list_source"})
    people = (f or {}).get("people") or []
    if not people:
        fails.append({"where": "people", "why": "empty"})
    seen = set()
    for i, p in enumerate(people):
        w = f"people[{i}]"
        n = _norm(p.get("name"))
        if not n:
            fails.append({"where": w, "why": "no_name"})
            continue
        if n in seen:
            fails.append({"where": w, "why": "duplicate"})
        seen.add(n)
        if not _src_ok(p.get("profile_url")):
            fails.append({"where": w, "why": "no_profile_source"})
    return fails


def group(t, profs):
    """首頁「目標教授」：學校 → 系所 → 教授；沒放進任何系所的列在 unassigned。"""
    by = {p["slug"]: p for p in profs}
    used = set()
    schools = []
    for s in t.get("schools") or []:
        deps = []
        for d in s["departments"]:
            ps = [by[x] for x in d["members"] if x in by]
            used |= {p["slug"] for p in ps}
            deps.append({**d, "profs": ps})
        schools.append({"id": s["id"], "name": s["name"], "departments": deps})
    return {"schools": schools, "unassigned": [p for p in profs if p["slug"] not in used]}
