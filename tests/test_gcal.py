"""Google 日曆：OAuth 網址（PKCE）、讀用戶端檔、會議對到哪位教授、建會議的內容。"""
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.gcal import auth_url, client_from, event_body, match_events, pkce


def test_pkce_and_auth_url():
    v, c = pkce()
    assert 43 <= len(v) <= 128
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    u = urlparse(auth_url("cid.apps.googleusercontent.com", "http://127.0.0.1:8790/", "st8", c))
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert u.netloc == "accounts.google.com"
    assert q["client_id"] == "cid.apps.googleusercontent.com" and q["redirect_uri"] == "http://127.0.0.1:8790/"
    assert q["code_challenge"] == c and q["code_challenge_method"] == "S256" and q["state"] == "st8"
    assert q["access_type"] == "offline" and "calendar.events" in q["scope"]


def test_client_from_desktop_json_only():
    assert client_from('{"installed": {"client_id": "a", "client_secret": "b"}}') == {"client_id": "a", "client_secret": "b"}
    with pytest.raises(ValueError):  # 網頁應用程式類型的不能用 127.0.0.1 回來
        client_from('{"web": {"client_id": "a", "client_secret": "b"}}')
    with pytest.raises(ValueError):
        client_from("not json")


PROFS = [{"slug": "laranjo-liliana", "name": "Liliana Laranjo", "email": "liliana.laranjo@sydney.edu.au"},
         {"slug": "fukuoka-yoshimi", "name": "Yoshimi Fukuoka"}]


def ev(summary, **kw):
    return {"id": kw.pop("id", summary), "summary": summary, "start": {"dateTime": "2026-11-03T10:00:00+08:00"},
            "end": {"dateTime": "2026-11-03T11:00:00+08:00"}, **kw}


def test_match_events_by_tag_email_or_full_name():
    events = [ev("PhD chat", extendedProperties={"private": {"phdeasy_slug": "fukuoka-yoshimi"}}),
              ev("Weekly", attendees=[{"email": "Liliana.Laranjo@sydney.edu.au"}]),
              ev("Meeting with Yoshimi Fukuoka"),
              ev("Dentist"),
              ev("Liliana's birthday")]  # 只有名字、沒有姓：不算
    got = {e["summary"]: e["slug"] for e in match_events(events, PROFS)}
    assert got == {"PhD chat": "fukuoka-yoshimi", "Weekly": "laranjo-liliana", "Meeting with Yoshimi Fukuoka": "fukuoka-yoshimi"}


def test_event_body():
    b = event_body("PhD 討論", "2026-11-03T10:00", 45, "Asia/Taipei", ["a@x.org", " ", "b@y.org"], meet=True, slug="laranjo-liliana", note="帶計畫書")
    assert b["start"] == {"dateTime": "2026-11-03T10:00:00", "timeZone": "Asia/Taipei"}
    assert b["end"] == {"dateTime": "2026-11-03T10:45:00", "timeZone": "Asia/Taipei"}
    assert b["attendees"] == [{"email": "a@x.org"}, {"email": "b@y.org"}] and b["description"] == "帶計畫書"
    assert b["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    assert b["extendedProperties"]["private"]["phdeasy_slug"] == "laranjo-liliana"
    with pytest.raises(ValueError):
        event_body("", "2026-11-03T10:00", 45, "Asia/Taipei", [])
    with pytest.raises(ValueError):
        event_body("x", "2026-11-03T10:00", 45, "Asia/Taipei", ["not-an-email"])
    assert "conferenceData" not in event_body("x", "2026-11-03T10:00", 30, "UTC", [])
