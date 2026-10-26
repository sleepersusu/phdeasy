"""Notion「博士申請追蹤」資料庫（做法參考 ieltsgod）：本人建一個 Notion 整合、貼上金鑰與一個頁面網址，
應用程式在那個頁面建資料庫並放進已建檔的教授；之後本人在 Notion 填，應用程式匯入（Notion 為主）。
金鑰放 runs/_me/secrets.env（NOTION_TOKEN），程式不顯示金鑰內容。
"""
import json
import re
import time
import urllib.error
import urllib.request

VERSION = "2022-06-28"
STATUS = ["想申請", "聯絡中", "已寄信", "已面談", "已申請", "錄取", "未錄取", "放棄"]
TEXT_COLS = {"學校": "institution", "ORCID": "orcid", "學程": "program", "備註": "note"}
SCHEMA = {"教授": {"title": {}}, "學校": {"rich_text": {}}, "ORCID": {"rich_text": {}}, "學程": {"rich_text": {}},
          "截止日": {"date": {}}, "狀態": {"select": {"options": [{"name": n} for n in STATUS]}}, "會議": {"date": {}},
          "網址": {"url": {}}, "備註": {"rich_text": {}}}


def request(method, path, token, body=None):
    req = urllib.request.Request("https://api.notion.com/v1" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Notion-Version": VERSION, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message", "")
        except ValueError:
            msg = ""
        if e.code == 401:
            raise ValueError("Notion 金鑰不對：請重新複製整合的「Internal Integration Secret」") from None
        if e.code == 404:
            raise ValueError("找不到這個 Notion 頁面：請在那個頁面右上角「…」→「連線」（Connections）加入你建的整合") from None
        raise ValueError(f"Notion 回應 {e.code}：{msg}") from None


def page_id_from(link):
    """Notion 頁面網址 → 頁面 id（32 個十六進位字元，可能有連字號）。"""
    seg = (link or "").split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[-1].lower()
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", seg) or re.search(r"([0-9a-f]{32})$", seg)
    if "notion" not in (link or "") or not m:
        raise ValueError("看不懂這個網址：請貼 Notion 頁面的網址（在頁面右上角「分享」→「複製連結」）")
    h = m.group(1).replace("-", "")
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _rt(t):
    return [{"type": "text", "text": {"content": str(t)[:1900]}}] if t else []


def row_props(r):
    """應用程式的一筆（教授、申請）→ Notion 欄位；空的欄位不送。"""
    props = {"教授": {"title": _rt(r.get("name"))}}
    for col, k in TEXT_COLS.items():
        if r.get(k):
            props[col] = {"rich_text": _rt(r[k])}
    if r.get("deadline"):
        props["截止日"] = {"date": {"start": r["deadline"]}}
    if r.get("meeting"):
        props["會議"] = {"date": {"start": r["meeting"]}}
    if r.get("status") in STATUS:
        props["狀態"] = {"select": {"name": r["status"]}}
    if r.get("url"):
        props["網址"] = {"url": r["url"]}
    return props


def _plain(p):
    t = p.get("type")
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in p.get(t) or []).strip()
    if t == "select":
        return (p.get("select") or {}).get("name")
    if t == "date":
        return (p.get("date") or {}).get("start")
    if t == "url":
        return p.get("url")
    return None


def parse_page(page):
    """Notion 的一列 → {name, institution, orcid, program, deadline, status, meeting, url, note, page_id, notion_url}。"""
    P = page.get("properties") or {}
    g = lambda col: _plain(P[col]) if col in P else None
    return {"page_id": page.get("id"), "notion_url": page.get("url"), "name": g("教授") or "",
            **{k: g(col) or None for col, k in TEXT_COLS.items() if k != "note"},
            "deadline": g("截止日"), "status": g("狀態"), "meeting": g("會議"), "url": g("網址"), "note": g("備註") or None}


def _norm(name):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (name or "").lower())).strip()


def match_professors(rows, profs):
    """每一列對到已建檔的哪位教授（ORCID 優先，其次姓名）；對不到的 slug 是 None（待建檔）。"""
    by_orcid = {p.get("orcid"): p["slug"] for p in profs if p.get("orcid")}
    by_name = {_norm(p.get("name")): p["slug"] for p in profs}
    return [{**r, "slug": by_orcid.get(r.get("orcid")) or by_name.get(_norm(r.get("name")))} for r in rows]


def setup(token, link, seed):
    """在本人指定的頁面建「博士申請追蹤」資料庫，放進已建檔的教授。回傳設定（不含金鑰）。"""
    pid = page_id_from(link)
    request("GET", f"/pages/{pid}", token)
    db = request("POST", "/databases", token, {"parent": {"type": "page_id", "page_id": pid},
                                                "title": _rt("博士申請追蹤"), "properties": SCHEMA})
    for r in seed:
        request("POST", "/pages", token, {"parent": {"database_id": db["id"]}, "properties": row_props(r)})
        time.sleep(0.34)  # Notion 每秒最多 3 次
    return {"page_id": pid, "db_id": db["id"], "db_url": db.get("url")}


def fetch_rows(token, db_id):
    rows, cursor = [], None
    while True:
        body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        r = request("POST", f"/databases/{db_id}/query", token, body)
        rows += [parse_page(p) for p in r.get("results") or [] if not p.get("archived")]
        if not r.get("has_more"):
            return rows
        cursor = r.get("next_cursor")
