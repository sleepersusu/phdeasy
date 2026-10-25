"""故意埋錯：引用已結束的經費、不存在的文章、關於本人卻沒引 CV、中英數字不一致、只有一個版本、
信心「高」卻沒有她主持的期間內經費、誇大用詞，都要被抓到。"""
import copy

from pipeline.propose import active_grants, check_draft, check_version

GRANTS = [{"key": "NIH:OLD", "status": "other", "start": "2015-01-01", "end": "2020-12-31", "title": "old"},
          {"key": "NIH:NOW", "status": "confirmed", "start": "2023-01-01", "end": "2027-06-30", "title": "now", "target_role": "pi"},
          {"key": "ID:NHMRC1", "status": "other", "announced": "2022-10-12", "title": "inv grant"},
          {"key": "FUNDER:x", "status": "acknowledged", "title": None, "funder": "x"}]
ACT = {g["key"]: g for g in active_grants(GRANTS, today="2026-10-26")}
WORKS = {"W1", "W2"}


def test_active_grants_by_date_or_recent_announcement():
    assert set(ACT) == {"NIH:NOW", "ID:NHMRC1"} and "期間不明" in ACT["ID:NHMRC1"]["period"]


def t(en="Text.", zh="文字。", refs=None):
    return {"en": en, "zh": zh, "refs": refs or []}


def version(vid="v1", direction="方向一"):
    return {"id": vid, "direction": t("Direction " + vid, direction),
            "confidence": {"level": "medium", **t("Fits her grant; I would need to learn X.", "對得上她的計畫；X 要另外學。", ["NIH:NOW", "cv:capabilities"])},
            "title": t(), "subtitle": t(),
            "synopsis": t(refs=["W1"]), "rationale": t(refs=["W1"]), "gaps": [t(refs=["W2"])],
            "aim": t(), "objectives": [t()],
            "studies": [{"name": t(), "aim": t(), "methods": t(refs=["W1"]), "analysis": t()}],
            "contribution": t(), "timeline": t(), "resources": t(refs=["NIH:NOW"]),
            "fit": {"can_do": [t(refs=["cv:capabilities"])], "could_do": [t(refs=["cv:projects"])]},
            "risks": t()}


def good():
    return {"versions": [version("v1", "方向一"), version("v2", "方向二")]}


def whys(fails):
    return {f["why"] for f in fails}


def test_good_draft_passes():
    assert check_draft(good(), WORKS, ACT) == []


def test_needs_two_to_three_distinct_versions():
    assert "need_2_to_3_versions" in whys(check_draft({"versions": [version()]}, WORKS, ACT))
    d = good()
    d["versions"][1]["direction"] = copy.deepcopy(d["versions"][0]["direction"])
    d["versions"][1]["id"] = "v1"
    assert {"version_id_duplicate", "direction_duplicate"} <= whys(check_draft(d, WORKS, ACT))


def test_refs_numbers_and_cv_are_checked():
    v = version()
    v["resources"]["refs"] = ["NIH:OLD"]
    v["rationale"]["refs"] = ["W9"]
    v["gaps"][0]["refs"] = []
    v["fit"]["can_do"][0]["refs"] = []
    v["aim"] = t("Recruit 120.", "收 100 人。")
    del v["risks"]
    w = whys(check_version(v, WORKS, ACT))
    assert {"grant_not_active:NIH:OLD", "unknown_paper:W9", "needs_professor_ref", "needs_cv_ref", "numbers_differ",
            "missing_section", "resources_must_cite_active_grant"} <= w


def test_can_do_and_could_do_both_required():
    v = version()
    v["fit"]["could_do"] = []
    assert "need_could_do" in whys(check_version(v, WORKS, ACT))


def test_high_confidence_needs_her_own_active_grant():
    v = version()
    v["confidence"]["level"] = "high"
    assert check_version(v, WORKS, ACT) == []  # NIH:NOW 是她主持（confirmed）
    v["resources"]["refs"] = ["ID:NHMRC1"]  # 合作者主持
    assert "high_confidence_without_her_grant" in whys(check_version(v, WORKS, ACT))
    v["confidence"]["level"] = "sure"
    assert "bad_confidence_level" in whys(check_version(v, WORKS, ACT))


def test_overclaiming_words_are_caught():
    v = version()
    v["contribution"] = t("A groundbreaking, first-ever system.", "首創的系統。")
    w = whys(check_version(v, WORKS, ACT))
    assert "overclaim:groundbreaking" in w and "overclaim:首創" in w


def test_version_may_say_no_grant_fits_instead_of_forcing_one():
    # 期間內有經費但都不對題時，不能硬套：標 no_fitting_grant，且信心不能是「高」
    v = version()
    v["resources"] = {**t("No current grant covers this; funding to be discussed.", "目前期間內的經費都不涵蓋這個方向，經費要跟她討論。"), "no_fitting_grant": True}
    assert check_version(v, WORKS, ACT) == []
    v["confidence"]["level"] = "high"
    assert "high_confidence_without_her_grant" in whys(check_version(v, WORKS, ACT))
    v["confidence"]["level"] = "medium"
    v["resources"]["refs"] = ["NIH:NOW"]  # 說不對題又引經費：自相矛盾
    assert "no_fitting_grant_but_cites_grant" in whys(check_version(v, WORKS, ACT))
