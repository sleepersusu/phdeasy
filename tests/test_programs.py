"""教授首頁的博士學程：查詢者寫 work/programs.json，腳本核對後寫 out/programs.json；沒查過就用查詢教授結果裡同一個人的。"""
import json

from pipeline.site import _programs

CPH = {"name": "Computational Precision Health", "url": "https://computationalhealth.ucsf.edu/", "member_src": "https://computationalhealth.ucsf.edu/faculty/page/3",
       "funding": {"value": "full", "years": 5, "src": "https://computationalhealth.ucsf.edu/?p=181"}}


def run(tmp_path, prof):
    r = tmp_path / "runs" / "hong-julian"
    (r / "work").mkdir(parents=True)
    (r / "state.json").write_text(json.dumps({"professor": prof}))
    return r


def test_programs_script_checks_and_writes(tmp_path, capsys):
    import programs
    r = run(tmp_path, {"name": "Julian Hong"})
    (r / "work" / "programs.json").write_text(json.dumps({"programs": [{**CPH, "member_src": None}]}))
    assert programs.main([str(r)]) == 1 and not (r / "out" / "programs.json").exists()
    assert "no_member_source" in capsys.readouterr().out
    (r / "work" / "programs.json").write_text(json.dumps({"programs": [CPH]}))
    assert programs.main([str(r), "--no-site"]) == 0
    out = json.loads((r / "out" / "programs.json").read_text())
    assert out["programs"][0]["name"] == "Computational Precision Health" and out["checked"]


def test_site_programs_own_then_discover(tmp_path):
    r = run(tmp_path, {"name": "Julian C. Hong", "orcid": "0000-0001-5172-6889"})
    disc = tmp_path / "runs" / "_discover"
    disc.mkdir()
    (disc / "latest.json").write_text(json.dumps({"candidates": [{"id": "A1", "name": "Someone", "orcid": "0000-0001-5172-6889", "programs": [CPH]}]}))
    got = _programs(r)
    assert got["from"] == "discover" and got["programs"][0]["name"] == "Computational Precision Health"
    (r / "out").mkdir()
    (r / "out" / "programs.json").write_text(json.dumps({"checked": "2026-10-26", "programs": []}))
    assert _programs(r) == {"checked": "2026-10-26", "programs": [], "from": "own"}  # 自己查過（沒有）就以自己的為準
    assert _programs(run(tmp_path / "x", {"name": "Nobody"})) is None
