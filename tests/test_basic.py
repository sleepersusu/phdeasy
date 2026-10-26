"""教授基本資訊：從 ORCID 公開紀錄抓職稱／系所／學校／經歷，從 OpenAlex 抓學術指標；只收來源有寫的，沒寫就留空。"""
from pipeline.basic import parse_openalex_author, parse_orcid


def aff(kind, role, dept, org, start=None, end=None, country="AU"):
    d = lambda y: {"year": {"value": y}} if y else None
    return {f"{kind}-summary": {"role-title": role, "department-name": dept, "start-date": d(start), "end-date": d(end),
                                "organization": {"name": org, "address": {"city": "Sydney", "country": country}}}}


RECORD = {"person": {"biography": {"content": "  Digital health researcher.  "},
                     "keywords": {"keyword": [{"content": "mHealth"}, {"content": "AI"}]},
                     "researcher-urls": {"researcher-url": [{"url-name": "Profile", "url": {"value": "https://example.edu/ll"}}]}},
          "activities-summary": {
              "employments": {"affiliation-group": [
                  {"summaries": [aff("employment", "Associate Professor", "WARC", "The University of Sydney", "2021")]},
                  {"summaries": [aff("employment", "Research Fellow", None, "Macquarie University", "2015", "2020")]}]},
              "educations": {"affiliation-group": [{"summaries": [aff("education", "PhD", None, "Universidade Nova de Lisboa", None, "2014", "PT")]}]}}}


def test_orcid_current_position_and_history():
    b = parse_orcid(RECORD)
    assert b["position"] == {"title": "Associate Professor", "department": "WARC", "institution": "The University of Sydney",
                             "country": "AU", "since": "2021"}
    assert [e["institution"] for e in b["employments"]] == ["The University of Sydney", "Macquarie University"]
    assert b["employments"][1]["until"] == "2020"
    assert b["educations"][0] == {"title": "PhD", "department": None, "institution": "Universidade Nova de Lisboa", "country": "PT",
                                  "since": None, "until": "2014"}
    assert b["bio"] == "Digital health researcher." and b["keywords"] == ["mHealth", "AI"]
    assert b["urls"] == [{"name": "Profile", "url": "https://example.edu/ll"}]


def test_orcid_empty_record_gives_blanks_not_guesses():
    b = parse_orcid({})
    assert b["position"] is None and b["employments"] == [] and b["bio"] is None and b["urls"] == []


def test_orcid_skips_non_http_urls():
    rec = {"person": {"researcher-urls": {"researcher-url": [{"url-name": "x", "url": {"value": "javascript:alert(1)"}}]}}}
    assert parse_orcid(rec)["urls"] == []


def test_openalex_metrics():
    a = {"works_count": 171, "cited_by_count": 6133, "summary_stats": {"h_index": 35, "i10_index": 80},
         "topics": [{"display_name": "Mobile Health"}, {"display_name": "Telemedicine"}],
         "last_known_institutions": [{"display_name": "The University of Sydney"}], "updated_date": "2026-10-20T01:02:03"}
    m = parse_openalex_author(a)
    assert m == {"works_count": 171, "cited_by_count": 6133, "h_index": 35, "i10_index": 80,
                 "topics": ["Mobile Health", "Telemedicine"], "as_of": "2026-10-20"}


def test_orcid_falls_back_to_openalex_author(tmp_path):
    """本人建檔時沒填 ORCID（例：從教員名單勾選）：用 OpenAlex 找到的那位作者的 ORCID，學歷、經歷才讀得到。"""
    import json
    from basic_info import professor_orcid
    r = tmp_path / "x"
    (r / "work").mkdir(parents=True)
    (r / "state.json").write_text(json.dumps({"professor": {"orcid": None}, "author_id": "A2"}))
    (r / "work" / "author_candidates.json").write_text(json.dumps([{"id": "A1", "orcid": "https://orcid.org/0000-0000-0000-0001"},
                                                                   {"id": "A2", "orcid": "https://orcid.org/0000-0002-1045-8459"}]))
    assert professor_orcid(r) == "0000-0002-1045-8459"
    (r / "state.json").write_text(json.dumps({"professor": {"orcid": "0000-0003-1020-3402"}, "author_id": "A2"}))
    assert professor_orcid(r) == "0000-0003-1020-3402"  # 本人填的優先
