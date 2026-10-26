"""必讀前五篇：只有這幾篇抓全文、轉文字、寫解析卡與重點；其他文章只列標題（kind=title），流水線各步都跳過。"""
import json

import pytest

from pipeline.focus import apply_focus, check_picks, deep_works

WORKS = [{"id": f"W{i}", "kind": "full" if i % 3 else "short", "title": f"Paper {i} on digital health coaching",
          "abstract": f"We tested a conversational agent for hypertension self-management in study {i}." if i != 7 else None} for i in range(10)]


def pick(i, quote=None):
    return {"id": f"W{i}", "reason": "跟你的對話式 AI 興趣相關", "quote": quote or "conversational agent for hypertension"}


def test_check_picks_catches_bad_lists():
    assert check_picks([pick(i) for i in range(5)], WORKS, n=5) == []
    whys = lambda ps: [f["why"] for f in check_picks(ps, WORKS, n=5)]
    assert "wrong_count" in whys([pick(i) for i in range(4)])
    assert "duplicate" in whys([pick(0), pick(0), pick(1), pick(2), pick(3)])
    assert "unknown_id" in whys([pick(0), pick(1), pick(2), pick(3), {**pick(9), "id": "W99"}])
    assert "quote_not_found" in whys([pick(0), pick(1), pick(2), pick(3), pick(4, "made up words here")])
    assert "no_reason" in whys([pick(0), pick(1), pick(2), pick(3), {**pick(4), "reason": ""}])
    assert check_picks([pick(i) for i in range(3)], WORKS[:3], n=5) == []  # 不到 5 篇就全部


def test_apply_focus_marks_rest_title_and_is_reversible():
    ws = json.loads(json.dumps(WORKS))
    apply_focus(ws, ["W1", "W2"])
    kinds = {w["id"]: w["kind"] for w in ws}
    assert kinds["W1"] == "full" and kinds["W0"] == "title" and kinds["W3"] == "title"
    assert [w["id"] for w in deep_works(ws)] == ["W1", "W2"]
    apply_focus(ws, ["W0", "W1"])  # 本人在停 1 換掉一篇：原本的種類還原
    kinds = {w["id"]: w["kind"] for w in ws}
    assert kinds["W0"] == "short" and kinds["W2"] == "title" and kinds["W1"] == "full"
    with pytest.raises(ValueError):
        apply_focus(ws, ["W404"])


def test_title_works_skip_fulltext():
    from pipeline.fetch import needs_fulltext
    assert not needs_fulltext({"kind": "title", "short_reason": "not_led"})
    assert needs_fulltext({"kind": "full"})


def test_focus_add_cli_keeps_existing_and_adds(tmp_path, capsys):
    import focus
    r = tmp_path / "runs" / "x"
    (r / "work").mkdir(parents=True)
    ws = json.loads(json.dumps(WORKS))
    apply_focus(ws, ["W1", "W2"])
    (r / "work" / "works.json").write_text(json.dumps(ws))
    (r / "work" / "focus.json").write_text(json.dumps({"ids": ["W1", "W2"], "picks": [pick(1), pick(2)]}))
    assert focus.main(["add", str(r), "--ids", "W0,W5"]) == 0
    f = json.loads((r / "work" / "focus.json").read_text())
    assert f["ids"] == ["W1", "W2", "W0", "W5"] and f["picks"][2]["reason"].startswith("本人")
    kinds = {w["id"]: w["kind"] for w in json.loads((r / "work" / "works.json").read_text())}
    assert kinds["W0"] == "short" and kinds["W5"] == "full" and kinds["W3"] == "title"
    assert focus.main(["add", str(r), "--ids", "W404"]) == 1


def test_picks_targets_must_be_known():
    """挑選者標「這篇對到你的哪些興趣／CV」（比對階段直接用）：只能是 inputs 給的 id。"""
    ps = [{**pick(i), "targets": ["i1"]} for i in range(5)]
    assert check_picks(ps, WORKS, n=5, target_ids={"i1", "c1"}) == []
    ps[0]["targets"] = ["i9"]
    assert "unknown_target" in {f["why"] for f in check_picks(ps, WORKS, n=5, target_ids={"i1", "c1"})}
