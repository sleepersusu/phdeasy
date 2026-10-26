"""教授學歷：ORCID 常沒填（本人 2026-10-26）。UCSF 用官方 Profiles API（腳本）；其他學校由查詢者從官方個人頁、CV、LinkedIn 公開頁讀，每筆要有出處。"""
import json

from pipeline.education import check_education, parse_ucsf, ucsf_name

API = {"Profiles": [{"Education_Training": [
    {"department_or_school": "School of  Nursing", "end_date": None, "organization": "University of California, San Francisco", "degree": "Ph.D."},
    {"department_or_school": "", "end_date": "1995", "organization": "Tokyo University", "degree": "B.S."}]}]}


def test_ucsf_name_and_parse():
    assert ucsf_name("https://profiles.ucsf.edu/yoshimi.fukuoka") == "yoshimi.fukuoka"
    assert ucsf_name("https://profiles.ucsf.edu/yoshimi.fukuoka/") == "yoshimi.fukuoka"
    assert ucsf_name("https://www.sydney.edu.au/x") is None
    items = parse_ucsf(API, "https://profiles.ucsf.edu/yoshimi.fukuoka")
    assert items[0] == {"degree": "Ph.D.", "institution": "University of California, San Francisco", "field": "School of Nursing", "year": None,
                        "src": "https://profiles.ucsf.edu/yoshimi.fukuoka"}
    assert items[1]["year"] == "1995"


def test_education_needs_sources():
    ok = [{"degree": "PhD", "institution": "Harvard", "src": "https://x"}]
    assert check_education(ok) == []
    assert {f["why"] for f in check_education([{"degree": "PhD", "institution": "Harvard"}])} == {"no_source"}
    assert {f["why"] for f in check_education([{"degree": "", "institution": "", "src": "https://x"}])} == {"empty"}


def test_programs_lookup_saves_education(tmp_path):
    import programs
    r = tmp_path / "runs" / "x"
    (r / "work").mkdir(parents=True)
    (r / "state.json").write_text(json.dumps({"professor": {"name": "A B"}}))
    prog = {"name": "PhD X", "url": "https://p", "member_src": "https://m", "funding": {"value": "unknown"}}
    (r / "work" / "programs.json").write_text(json.dumps({"programs": [prog], "education": [{"degree": "PhD", "institution": "Harvard", "year": "2010", "src": "https://cv.pdf"}]}))
    assert programs.main([str(r), "--no-site"]) == 0
    e = json.loads((r / "out" / "education.json").read_text())
    assert e["items"][0]["institution"] == "Harvard" and e["source"] == "lookup"
