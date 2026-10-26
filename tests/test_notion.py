"""Notion「博士申請追蹤」資料庫：網址解析、一列轉成應用程式的資料、跟已建檔的教授對起來。"""
import pytest

from pipeline.notion import match_professors, page_id_from, parse_page, row_props


def test_page_id_from_links():
    assert page_id_from("https://www.notion.so/My-PhD-2f1c3d4e5a6b7c8d9e0f1a2b3c4d5e6f?pvs=4") == "2f1c3d4e-5a6b-7c8d-9e0f-1a2b3c4d5e6f"
    assert page_id_from("https://notion.so/ws/2f1c3d4e-5a6b-7c8d-9e0f-1a2b3c4d5e6f") == "2f1c3d4e-5a6b-7c8d-9e0f-1a2b3c4d5e6f"
    with pytest.raises(ValueError):
        page_id_from("https://example.com/not-notion")


def page(props, pid="p1"):
    return {"id": pid, "url": "https://notion.so/p1", "properties": props}


def test_parse_page_reads_every_column():
    p = page({"教授": {"type": "title", "title": [{"plain_text": "Liliana Laranjo"}]},
              "學校": {"type": "rich_text", "rich_text": [{"plain_text": "The University of Sydney"}]},
              "ORCID": {"type": "rich_text", "rich_text": [{"plain_text": "0000-0003-1020-3402"}]},
              "學程": {"type": "rich_text", "rich_text": [{"plain_text": "PhD (Medicine and Health)"}]},
              "截止日": {"type": "date", "date": {"start": "2026-12-01"}},
              "狀態": {"type": "select", "select": {"name": "已面談"}},
              "會議": {"type": "date", "date": {"start": "2026-11-03T10:00:00+08:00"}},
              "網址": {"type": "url", "url": "https://profiles.sydney.edu.au/liliana.laranjo"},
              "備註": {"type": "rich_text", "rich_text": [{"plain_text": "想做 CHAT-AF 延伸"}]}})
    r = parse_page(p)
    assert r == {"page_id": "p1", "notion_url": "https://notion.so/p1", "name": "Liliana Laranjo", "institution": "The University of Sydney",
                 "orcid": "0000-0003-1020-3402", "program": "PhD (Medicine and Health)", "deadline": "2026-12-01", "status": "已面談",
                 "meeting": "2026-11-03T10:00:00+08:00", "url": "https://profiles.sydney.edu.au/liliana.laranjo", "note": "想做 CHAT-AF 延伸"}
    empty = parse_page(page({"教授": {"type": "title", "title": []}}))
    assert empty["name"] == "" and empty["deadline"] is None


def test_row_props_roundtrip():
    r = {"name": "Yoshimi Fukuoka", "institution": "UCSF", "status": "想申請", "deadline": "2027-01-15", "orcid": None}
    props = row_props(r)
    assert props["教授"]["title"][0]["text"]["content"] == "Yoshimi Fukuoka" and props["狀態"]["select"]["name"] == "想申請"
    assert props["截止日"]["date"]["start"] == "2027-01-15" and "ORCID" not in props


def test_match_professors_by_name_or_orcid():
    rows = [{"name": "liliana  laranjo", "orcid": None}, {"name": "Someone New", "orcid": "0000-0002-2245-9264"}, {"name": "Unknown", "orcid": None}]
    profs = [{"slug": "laranjo-liliana", "name": "Liliana Laranjo", "orcid": "0000-0003-1020-3402"},
             {"slug": "fukuoka-yoshimi", "name": "Yoshimi Fukuoka", "orcid": "0000-0002-2245-9264"}]
    assert [r["slug"] for r in match_professors(rows, profs)] == ["laranjo-liliana", "fukuoka-yoshimi", None]
