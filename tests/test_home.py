"""個人首頁：本人資料 → 教授比對清單 → 教授詳細頁。比對沿用前端同一份 JS（由 node 執行）。"""
import json
import shutil

import pytest

from pipeline.home import build_home_data, render_home, match_with_node
from pipeline.site import build_site_data
from test_site import make_run

ME = {"name": "Andy", "headline": "AI engineer", "headline_zh": "AI 工程師", "summary": "s", "summary_zh": "摘要",
      "interests": [{"en": "Digital Health", "zh": "數位健康"}],
      "proposal": {"title": "When to Ask", "title_zh": "何時詢問", "synopsis": "syn", "synopsis_zh": "摘", "gaps": [], "studies": []},
      "capabilities": [{"area": "Quant", "area_zh": "量化", "items": ["SAS"], "items_zh": ["SAS"]}],
      "publications": [], "projects": [], "education": [],
      "match": {"goal": "mHealth study for women", "tags": "women, mHealth", "methods": ["rct"]}}

node = pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")


def runs_with_prof(tmp_path):
    run = make_run(tmp_path)  # tmp/runs/demo
    (tmp_path / "runs" / "_me").mkdir()
    (tmp_path / "runs" / "_me" / "me.json").write_text(json.dumps(ME))
    return tmp_path / "runs"


def test_site_data_has_match_docs_and_me_query(tmp_path):
    runs = runs_with_prof(tmp_path)
    d = build_site_data(runs / "demo")
    assert {x["id"] for x in d["match_docs"] if x["kind"] == "paper"} == {"W1", "W2"}
    assert any(x["kind"] == "grant" for x in d["match_docs"])
    assert d["me_query"]["goal"] == "mHealth study for women"
    assert d["home_href"] == "../../../index.html"


@node
def test_match_with_node_ranks():
    docs = [{"id": "A", "kind": "paper", "text": "women mHealth app"}, {"id": "B", "kind": "paper", "text": "children ventilation"}]
    r = match_with_node(docs, "mHealth for women")
    assert [x["id"] for x in r] == ["A"] and r[0]["matched"]


@node
def test_home_lists_professors_with_summary(tmp_path):
    runs = runs_with_prof(tmp_path)
    h = build_home_data(runs)
    assert h["me"]["name"] == "Andy"
    assert len(h["professors"]) == 1
    p = h["professors"][0]
    assert p["slug"] == "demo" and p["href"] == "demo/out/site/index.html"
    assert p["name"] == "Yoshimi Fukuoka"
    assert "top_papers" in p and "shared_terms" in p and "counts" in p


@node
def test_home_skips_folders_without_site(tmp_path):
    runs = runs_with_prof(tmp_path)
    (runs / "half").mkdir()
    (runs / "half" / "state.json").write_text("{}")
    assert [p["slug"] for p in build_home_data(runs)["professors"]] == ["demo"]


@node
def test_render_home_sections_and_link(tmp_path):
    runs = runs_with_prof(tmp_path)
    html = render_home(build_home_data(runs))
    for sid in ("me", "proposal", "capabilities", "professors"):
        assert f'id="{sid}"' in html
    assert "demo/out/site/index.html" in html
    assert html.count("<script>") == 1


def test_home_without_me_shows_setup_hint(tmp_path):
    make_run(tmp_path)
    h = build_home_data(tmp_path / "runs", use_node=False)
    assert h["me"] is None
    assert "runs/_me/me.json" in render_home(h)


@node
def test_methods_not_mixed_into_topic_query_and_strong_count(tmp_path):
    runs = runs_with_prof(tmp_path)
    p = build_home_data(runs)["professors"][0]
    assert "n_strong" in p and p["n_strong"] <= p["n_overlap_papers"]
    assert not any("rct" == t.lower() for t in p["shared_terms"])  # 研究設計另外算，不混進主題詞
