"""故意埋錯：漏掉一張表、編一張不存在的圖、引句不在原文、中英數字不一致，都要被抓到。"""
from pipeline.digest import METHOD_KEYS, assemble_digest, check_digest

TEXT = "[p.1]\nWe enrolled 103 participants in a randomized controlled trial of conversational AI.\n[p.4]\nTable 1. Baseline characteristics of the 103 participants.\nFigure 1. Flowchart of participants included in the trial.\n"
LABELS = ["Table 1", "Figure 1"]
FIGS = [{"label": "Table 1", "caption": "Table 1. Baseline", "image": "../papers/x/figures/p4.png", "loc": "p.4"},
        {"label": "Figure 1", "caption": "Figure 1. Flowchart", "image": "../papers/x/figures/p4.png", "loc": "p.4"}]
C = lambda q, loc: [{"quote": q, "loc": loc}]


def good():
    kp = {"en": "103 people were enrolled.", "zh": "共收 103 人。", "citations": C("We enrolled 103 participants in a randomized", "p.1")}
    return {"id": "W1", "key_points": [kp, kp, kp],
            "design": {"en": "A randomized controlled trial.", "zh": "隨機對照試驗。", "citations": C("randomized controlled trial of conversational AI", "p.1")},
            "figures": [{"label": "Table 1", "en": "Baseline of 103 people.", "zh": "103 人的基本資料。", "citations": C("Baseline characteristics of the 103 participants", "p.4")},
                        {"label": "Figure 1", "en": "Participant flow.", "zh": "受試者流程。", "citations": C("Flowchart of participants included in the trial", "p.4")}],
            "method": {k: {"not_reported": True, "en": "Not reported", "zh": "原文未提及"} for k in METHOD_KEYS}}


def test_good_digest_passes():
    assert check_digest(good(), TEXT, LABELS) == []


def test_method_is_required():
    # 本人 2026-10-26：重點與研究方法由同一個 agent 一次寫完，研究方法十部分不能缺
    d = good()
    del d["method"]
    assert "missing_method" in {f["why"] for f in check_digest(d, TEXT, LABELS)}


def test_missing_fake_figure_bad_quote_and_numbers_are_caught():
    d = good()
    d["figures"] = d["figures"][:1] + [{"label": "Figure 9", "en": "x", "zh": "x", "citations": C("Flowchart of participants included in the trial", "p.4")}]
    d["key_points"][0] = {"en": "105 people.", "zh": "共收 103 人。", "citations": C("We enrolled 205 participants in a randomized", "p.1")}
    whys = {f["why"] for f in check_digest(d, TEXT, LABELS)}
    assert {"figure_missing", "figure_not_in_paper", "numbers_differ"} <= whys
    assert any(w not in ("figure_missing", "figure_not_in_paper", "numbers_differ") for w in whys)  # 引句錯


def test_assemble_keeps_every_figure_even_without_explanation():
    d = good()
    d["figures"][1]["citations"] = C("this sentence is not in the paper at all", "p.4")
    out, rej = assemble_digest(d, TEXT, LABELS, FIGS)
    assert [f["label"] for f in out["figures"]] == ["Table 1", "Figure 1"]
    assert out["figures"][1]["zh"] is None and out["figures"][1]["image"] and len(rej) == 1


def test_method_detail_needs_every_part_and_allows_not_reported():
    from pipeline.digest import METHOD_KEYS, check_method
    m = {k: {"not_reported": True, "en": "Not reported", "zh": "原文未提及"} for k in METHOD_KEYS}
    m["design"] = {"en": "Randomized controlled trial.", "zh": "隨機對照試驗。", "citations": C("randomized controlled trial of conversational AI", "p.1")}
    m["sample_size"] = {"en": "103 enrolled.", "zh": "收 103 人。", "citations": C("We enrolled 103 participants in a randomized", "p.1")}
    assert check_method(m, TEXT) == []
    bad = dict(m)
    del bad["variables"]
    bad["sample_size"] = {"en": "105 enrolled.", "zh": "收 103 人。", "citations": C("We enrolled 103 participants in a randomized", "p.1")}
    bad["design"] = {"en": "RCT.", "zh": "隨機對照試驗。", "citations": []}
    whys = {f["why"] for f in check_method(bad, TEXT)}
    assert {"missing_part", "numbers_differ", "no_citation"} <= whys


def test_figure_detail_is_checked_and_kept():
    # 本人 2026-10-26：圖不能只給一句話，要看圖逐步解讀（流程圖每一格、圖的軸與各組、表的列與欄）
    d = good()
    d["figures"][1]["detail"] = [{"en": "Assessed for eligibility (n=103).", "zh": "評估資格（103 人）。"},
                                 {"en": "Randomized 1:1.", "zh": "以 1:1 隨機分派。"}]
    assert check_digest(d, TEXT, LABELS) == []
    figs = [{"label": "Table 1", "caption": "Baseline", "image": None}, {"label": "Figure 1", "caption": "Flow", "image": "f1.png"}]
    out, _ = assemble_digest(d, TEXT, LABELS, figs)
    assert [x["en"] for x in next(f for f in out["figures"] if f["label"] == "Figure 1")["detail"]] == ["Assessed for eligibility (n=103).", "Randomized 1:1."]
    d["figures"][1]["detail"] = [{"en": "Randomized 120 people.", "zh": "隨機分派 100 人。"}, {"en": "Only English."}]
    whys = {f["why"] for f in check_digest(d, TEXT, LABELS)}
    assert {"numbers_differ", "need_en_and_zh"} <= whys
