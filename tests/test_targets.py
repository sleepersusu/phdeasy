"""目標學校 → 系所 → 教授：新增系所、把教授放進系所、查到的教員名單要有出處、依學校系所分組。"""
import pytest

from pipeline.targets import add_target, assign, check_faculty, group, remove_target

PEOPLE = [{"name": "Yoshimi Fukuoka", "title": "Professor", "profile_url": "https://profiles.ucsf.edu/yoshimi.fukuoka", "research": "digital health"},
          {"name": "Julian Hong", "title": "Associate Professor", "profile_url": "https://profiles.ucsf.edu/julian.hong"}]


def test_add_assign_group_remove():
    t = {}
    d1 = add_target(t, "University of California, San Francisco", "Computational Precision Health", "https://computationalhealth.ucsf.edu/")
    d2 = add_target(t, "University of California, San Francisco", "School of Nursing")
    assert add_target(t, "University of California, San Francisco", "computational precision health") == d1  # 同名不重複
    assert len(t["schools"]) == 1 and len(t["schools"][0]["departments"]) == 2
    assign(t, d1, "fukuoka-yoshimi")
    assign(t, d2, "fukuoka-yoshimi")  # 換系所：只會在一個系所裡
    profs = [{"slug": "fukuoka-yoshimi"}, {"slug": "doe-jane"}]
    g = group(t, profs)
    assert [p["slug"] for p in g["schools"][0]["departments"][1]["profs"]] == ["fukuoka-yoshimi"]
    assert g["schools"][0]["departments"][0]["profs"] == [] and [p["slug"] for p in g["unassigned"]] == ["doe-jane"]
    remove_target(t, d2)
    remove_target(t, d1)
    assert t["schools"] == []
    with pytest.raises(ValueError):
        add_target(t, "", "X")


def test_faculty_list_must_have_sources():
    assert check_faculty({"src": "https://computationalhealth.ucsf.edu/people", "people": PEOPLE}) == []
    whys = lambda f: {x["why"] for x in check_faculty(f)}
    assert "no_list_source" in whys({"src": None, "people": PEOPLE})
    assert "no_profile_source" in whys({"src": "https://x", "people": [{"name": "A", "profile_url": "not a url"}]})
    assert "no_name" in whys({"src": "https://x", "people": [{"name": "", "profile_url": "https://y"}]})
    assert "duplicate" in whys({"src": "https://x", "people": PEOPLE + PEOPLE[:1]})
    assert "empty" in whys({"src": "https://x", "people": []})
