"""故意埋錯：比對推薦的每一筆都要指到真的文章／計畫，理由要引得到原文（卡片或計畫），興趣要是本人寫的。"""
from pipeline.match import assemble, check_draft, me_fingerprint, targets_from_me

ME = {"interests": [{"en": "Digital Health", "zh": "數位健康"}, {"en": "Healthy Ageing", "zh": "健康老化"}],
      "proposal": {"title": "Safe agentic AI", "studies": [{"name": "Study 1 — Evidence synthesis", "name_zh": "研究一：證據統整", "detail": "PRISMA review"}]},
      "match": {"goal": "remote monitoring"},
      "capabilities": [{"area": "Quantitative health research", "area_zh": "健康研究量化分析", "items": ["SAS, SPSS"]}],
      "projects": [{"name": "HomeWellness", "zh": "多 agent 健康陪伴"}]}
INPUTS = {
    "targets": targets_from_me(ME),
    "papers": {"W1": {"title": "App trial", "text": "這是一項隨機對照試驗，評估手機 app 降低血壓。"},
               "W2": {"title": "Review", "text": "系統性回顧遠距監測的轉介流程。"}},
    "grants": {"ID:G1": {"title": "Digital health to support behaviour change", "text": "Digital health to support behaviour change and chronic disease prevention"}},
}


def good():
    return {"targets": [
        {"target": "i1", "fit": "strong", "why": "她的 app 試驗直接評估數位介入", "papers": [{"id": "W1", "why": "評估 app 降血壓", "evidence": "評估手機 app 降低血壓"}],
         "grants": [{"key": "ID:G1", "why": "計畫主軸就是數位健康", "evidence": "Digital health to support behaviour change"}]},
        {"target": "i2", "fit": "none", "why": "來源未提及與健康老化直接相關的研究", "papers": [], "grants": []},
        {"target": "c1", "fit": "partial", "why": "她做過轉介流程的回顧", "papers": [{"id": "W2", "why": "方法相同", "evidence": "系統性回顧遠距監測的轉介流程"}], "grants": []},
        {"target": "c2", "fit": "none", "why": "來源未提及多 agent 健康陪伴的研究", "papers": [], "grants": []},
    ], "read_first": ["W2", "W1"]}


def test_targets_are_interests_and_cv_not_joint_proposal():
    # 研究計畫是本人與 Liliana 共同討論的（2026-10-26），比對只用本人的興趣與 CV（會的、做過的）
    ts = targets_from_me(ME)
    assert [t["id"] for t in ts] == ["i1", "i2", "c1", "c2"]
    assert [t["kind"] for t in ts] == ["interest", "interest", "cv", "cv"]
    assert ts[2]["label_zh"] == "健康研究量化分析" and "SAS" in ts[2]["detail"]
    assert ts[3]["label"] == "HomeWellness"


def test_fingerprint_ignores_joint_proposal_but_tracks_cv():
    a = me_fingerprint(ME)
    assert me_fingerprint({**ME, "proposal": {"title": "other", "studies": []}, "match": {"goal": "x"}}) == a
    assert me_fingerprint({**ME, "capabilities": []}) != a


def test_good_draft_passes():
    assert check_draft(good(), INPUTS) == []


def test_unknown_paper_and_fake_evidence_are_caught():
    d = good()
    d["targets"][0]["papers"].append({"id": "W99", "why": "x", "evidence": "y"})
    d["targets"][2]["papers"][0]["evidence"] = "她發明了新的轉介標準"  # 原文沒有
    whys = {f["why"] for f in check_draft(d, INPUTS)}
    assert {"unknown_paper", "evidence_not_in_source"} <= whys


def test_every_target_must_be_answered_and_read_first_must_be_recommended():
    d = good()
    d["targets"] = d["targets"][:2]
    d["read_first"] = ["W2", "W1", "W1"]
    whys = {f["why"] for f in check_draft(d, INPUTS)}
    assert "missing_target" in whys and "read_first_not_recommended" in whys and "read_first_duplicate" in whys


def test_fit_none_must_not_list_items_and_strong_needs_items():
    d = good()
    d["targets"][1]["papers"] = [{"id": "W1", "why": "x", "evidence": "評估手機 app 降低血壓"}]
    d["targets"][0]["papers"], d["targets"][0]["grants"] = [], []
    whys = {f["why"] for f in check_draft(d, INPUTS)}
    assert "none_with_items" in whys and "fit_without_items" in whys


def test_assemble_drops_rejected_and_records_fingerprint():
    verdicts = [{"path": "targets[0].papers[0]", "verdict": "reject", "reason": "不相關"}]
    out, rejected = assemble(good(), verdicts, INPUTS, fp="abc")
    assert out["targets"][0]["papers"] == [] and out["fingerprint"] == "abc" and len(rejected) == 1
    assert "W1" not in out["read_first"]  # 被推翻的文章也從「先看」拿掉
    assert out["targets"][0]["label_zh"] == "數位健康"


def test_fingerprint_changes_when_interests_change():
    a = me_fingerprint(ME)
    b = me_fingerprint({**ME, "interests": ME["interests"][:1]})
    assert a != b


def test_prefill_from_focus_papers_and_grants_only_matcher():
    """本人 2026-10-26：文章直接用必讀五篇（挑選者已寫理由、標了對到哪些興趣），比對者只判經費與整體適合度，沒有推翻者。"""
    from pipeline.match import prefill_from_focus
    focus = {"ids": ["W1", "W2"], "picks": [{"id": "W1", "reason": "評估 app 降血壓", "quote": "App trial", "targets": ["i1"]},
                                          {"id": "W2", "reason": "轉介流程回顧", "quote": "Review", "targets": ["c1", "i1"]}]}
    pre = prefill_from_focus(focus, INPUTS)
    assert [p["id"] for p in pre["i1"]] == ["W1", "W2"] and [p["id"] for p in pre["c1"]] == ["W2"] and "i2" not in pre
    assert prefill_from_focus({"picks": [{"id": "W1"}]}, INPUTS) is None  # 舊批次沒有 targets 標記：走原本的流程
    draft = {"targets": [{"target": "i1", "fit": "strong", "why": "app 試驗", "grants": [{"key": "ID:G1", "why": "數位健康", "evidence": "Digital health to support behaviour change"}]},
                         {"target": "i2", "fit": "none", "why": "沒有相關", "grants": []},
                         {"target": "c1", "fit": "partial", "why": "回顧", "grants": []},
                         {"target": "c2", "fit": "none", "why": "沒有相關", "grants": []}]}
    assert check_draft(draft, INPUTS, prefill=pre) == []  # 文章由腳本帶入，比對者不用寫 papers 與 read_first
    bad = {"targets": draft["targets"][:1] + [{"target": "i2", "fit": "strong", "why": "x", "grants": []}] + draft["targets"][2:]}
    assert "fit_without_items" in {f["why"] for f in check_draft(bad, INPUTS, prefill=pre)}
    final, rej = assemble(draft, [], INPUTS, fp="x", prefill=pre, read_first=focus["ids"])
    t1 = final["targets"][0]
    assert [p["id"] for p in t1["papers"]] == ["W1", "W2"] and t1["papers"][0]["why"] == "評估 app 降血壓" and t1["grants"][0]["key"] == "ID:G1"
    assert final["read_first"] == ["W1", "W2"] and rej == []
