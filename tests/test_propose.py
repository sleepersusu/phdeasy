"""故意埋錯：引用已結束的經費、不存在的文章、關於本人卻沒引 CV、中英數字不一致，都要被抓到。"""
from pipeline.propose import SECTIONS, active_grants, check_proposal

GRANTS = [{"key": "NIH:OLD", "status": "other", "start": "2015-01-01", "end": "2020-12-31", "title": "old"},
          {"key": "NIH:NOW", "status": "confirmed", "start": "2023-01-01", "end": "2027-06-30", "title": "now", "target_role": "pi"},
          {"key": "ID:NHMRC1", "status": "confirmed", "announced": "2022-10-12", "title": "inv grant"},
          {"key": "FUNDER:x", "status": "acknowledged", "title": None, "funder": "x"}]


def test_active_grants_by_date_or_recent_announcement():
    a = {g["key"]: g for g in active_grants(GRANTS, today="2026-10-26")}
    assert set(a) == {"NIH:NOW", "ID:NHMRC1"} and "期間不明" in a["ID:NHMRC1"]["period"]


def good():
    d = {k: {"en": "Text.", "zh": "文字。", "refs": []} for k in SECTIONS}
    d["funding"]["refs"] = ["NIH:NOW"]
    d["background"]["refs"] = ["W1"]
    d["my_role"]["refs"] = ["cv:capabilities"]
    return d


def test_good_passes_and_errors_caught():
    assert check_proposal(good(), {"W1"}, {"NIH:NOW", "ID:NHMRC1"}) == []
    d = good()
    d["funding"]["refs"] = ["NIH:OLD"]
    d["background"]["refs"] = ["W9"]
    d["my_role"]["refs"] = []
    d["aims"] = {"en": "Recruit 120.", "zh": "收 100 人。", "refs": []}
    del d["risks"]
    whys = {f["why"] for f in check_proposal(d, {"W1"}, {"NIH:NOW"})}
    assert {"grant_not_active:NIH:OLD", "unknown_paper:W9", "needs_cv_ref", "numbers_differ", "missing_section", "funding_must_cite_active_grant"} <= whys
