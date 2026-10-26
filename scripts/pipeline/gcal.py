"""Google 日曆：本人自己在 Google Cloud 建一個「電腦版應用程式」OAuth 用戶端，把 JSON 交給應用程式；
應用程式用 127.0.0.1 回呼＋PKCE 登入，只要「日曆活動」權限（讀、建會議）。
用戶端與權杖放 runs/_me/（經本人的雲端硬碟同步，不進 git）；會議放 runs/_me/calendar.json，對到教授的記 slug。
"""
import base64
import hashlib
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def pkce():
    v = secrets.token_urlsafe(64)[:96]
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    return v, c


def auth_url(client_id, redirect, state, challenge):
    return AUTH + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})


def client_from(text):
    """Google Cloud 下載的用戶端 JSON → {client_id, client_secret}；只收「電腦版應用程式」（installed）。"""
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("看不懂這個檔：請上傳 Google Cloud「憑證」頁下載的 JSON") from None
    c = d.get("installed") if isinstance(d, dict) else None
    if not c or not c.get("client_id") or not c.get("client_secret"):
        raise ValueError("這個用戶端不是「電腦版應用程式」（Desktop app）：請重建一個電腦版的 OAuth 用戶端")
    return {"client_id": c["client_id"], "client_secret": c["client_secret"]}


def _post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Google 登入失敗（{e.code}）：{e.read().decode()[:200]}") from None


def exchange(client, code, verifier, redirect):
    t = _post_form(TOKEN, {**client, "code": code, "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code"})
    return _stamp(t)


def refresh(client, token):
    t = _post_form(TOKEN, {**client, "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
    return _stamp({**token, **t})


def _stamp(t):
    t["expires_at"] = (datetime.now().astimezone() + timedelta(seconds=int(t.get("expires_in", 3600)) - 60)).isoformat(timespec="seconds")
    return t


def expired(token):
    return datetime.fromisoformat(token["expires_at"]) <= datetime.now().astimezone()


def _call(method, url, access, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + access, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError("Google 日曆的登入過期了：到設定重新登入") from None
        raise ValueError(f"Google 日曆回應 {e.code}：{e.read().decode()[:200]}") from None


def list_events(access, days_back=60, days_ahead=180):
    now = datetime.now().astimezone()
    out, page = [], None
    while True:
        q = {"timeMin": (now - timedelta(days=days_back)).isoformat(), "timeMax": (now + timedelta(days=days_ahead)).isoformat(),
             "singleEvents": "true", "orderBy": "startTime", "maxResults": 250, **({"pageToken": page} if page else {})}
        r = _call("GET", API + "?" + urllib.parse.urlencode(q), access)
        out += [e for e in r.get("items") or [] if e.get("status") != "cancelled"]
        page = r.get("nextPageToken")
        if not page:
            return out


def create_event(access, body, notify=False):
    q = {"conferenceDataVersion": 1, "sendUpdates": "all" if notify else "none"}
    return _call("POST", API + "?" + urllib.parse.urlencode(q), access, body)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s@.]", " ", (s or "").lower())).strip()


def match_events(events, profs):
    """會議對到哪位教授：應用程式建的（標了 slug）→ 與會者 email → 標題或說明寫了全名。對不到的不列。"""
    by_slug = {p["slug"] for p in profs}
    out = []
    for e in events:
        slug = ((e.get("extendedProperties") or {}).get("private") or {}).get("phdeasy_slug")
        if slug not in by_slug:
            mails = {(a.get("email") or "").lower() for a in e.get("attendees") or []}
            text = f" {_norm(e.get('summary'))} {_norm(e.get('description'))} "
            slug = next((p["slug"] for p in profs if p.get("email") and p["email"].lower() in mails), None) or \
                next((p["slug"] for p in profs if p.get("name") and f" {_norm(p['name'])} " in text), None)
        if slug:
            st, en = e.get("start") or {}, e.get("end") or {}
            out.append({"id": e.get("id"), "slug": slug, "summary": e.get("summary") or "", "start": st.get("dateTime") or st.get("date"),
                        "end": en.get("dateTime") or en.get("date"), "link": e.get("htmlLink"), "meet": e.get("hangoutLink"),
                        "attendees": [a.get("email") for a in e.get("attendees") or [] if a.get("email")]})
    return out


def event_body(summary, start, minutes, tz, attendees, meet=False, slug=None, note=None):
    """建會議的內容。start 是當地時間 YYYY-MM-DDTHH:MM，tz 是 IANA 時區（例 Asia/Taipei）。"""
    if not (summary or "").strip():
        raise ValueError("會議要有標題")
    s = datetime.fromisoformat(start)
    mails = [a.strip() for a in attendees or [] if a and a.strip()]
    bad = [a for a in mails if not EMAIL.fullmatch(a)]
    if bad:
        raise ValueError(f"這不是 email：{'、'.join(bad)}")
    b = {"summary": summary.strip(), "start": {"dateTime": s.isoformat(timespec="seconds"), "timeZone": tz},
         "end": {"dateTime": (s + timedelta(minutes=int(minutes))).isoformat(timespec="seconds"), "timeZone": tz}}
    if mails:
        b["attendees"] = [{"email": a} for a in mails]
    if note:
        b["description"] = note
    if meet:
        b["conferenceData"] = {"createRequest": {"requestId": secrets.token_hex(8), "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    if slug:
        b["extendedProperties"] = {"private": {"phdeasy_slug": slug}}
    return b
