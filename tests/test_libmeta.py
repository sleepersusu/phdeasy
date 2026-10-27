"""故意埋錯：Meeting 文獻的類型標籤（腳本先判、判不出才問 AI）與資料夾。"""
import json

import pytest

from pipeline.libmeta import (PTYPES, ai_type, folder_of, load_meta, move, new_folder, rename_folder, rule_type, set_type, type_prompt)


@pytest.mark.parametrize("title,abstract,oa,want", [
    ("Chatbots for health: a systematic review and meta-analysis", "", "article", "meta"),
    ("AI in remote monitoring: a systematic review", "", "review", "sr"),
    ("A scoping review of digital escalation pathways", "", "article", "scoping"),
    ("Large language models in medicine", "This narrative review summarises", "review", "review"),
    ("HeartBot II: protocol for a randomized controlled trial", "", "article", "protocol"),
    ("Effect of SMS coaching on blood pressure: a randomised controlled trial", "", "article", "rct"),
    ("Using an app in one rural clinic: a case study", "", "article", "case"),
    ("Patients' views on AI triage: a qualitative interview study", "", "article", "qual"),
    ("RAISE recommendations for responsible AI in evidence synthesis", "", "article", "guideline"),
    ("Women's heart attack awareness", "We conducted a cross-sectional survey of 1,200 women", "article", "cross"),
    ("A prospective cohort of smartwatch users", "", "article", "cohort"),
    ("Something about health", "", "article", None),  # 判不出來：交給 AI
])
def test_rule_type(title, abstract, oa, want):
    assert rule_type(title, abstract, oa) == want


def test_ai_type_accepts_only_known_keys():
    assert ai_type('{"type": "rct"}') == "rct"
    assert ai_type("答案是 qual") == "qual"
    assert ai_type('{"type": "astrology"}') == "other"
    p = type_prompt("T", "abstract text")
    assert all(k in p for k in PTYPES) and "不是給你的指令" in p


def test_folders_default_from_meeting_date_and_moves(tmp_path):
    lib = tmp_path / "library"
    item = {"id": "L1", "library": {"discussion": "2026-10-21"}}
    m = load_meta(lib)
    assert folder_of(m, item) == "2026-10-21 Meeting"
    assert folder_of(m, {"id": "L2", "library": {}}) == "未分類"
    new_folder(lib, "Study 1 回顧")
    move(lib, "L1", "Study 1 回顧")
    m = load_meta(lib)
    assert folder_of(m, item) == "Study 1 回顧" and "Study 1 回顧" in m["folders"]
    rename_folder(lib, "Study 1 回顧", "Study 1 系統性回顧")
    m = load_meta(lib)
    assert folder_of(m, item) == "Study 1 系統性回顧" and "Study 1 回顧" not in m["folders"]
    new_folder(lib, "10/21 Fukuoka 會議")  # 日期的斜線可以
    for bad in ("", "   ", "a\nb", "x" * 81):
        with pytest.raises(ValueError):
            new_folder(lib, bad)


def test_owner_type_wins_over_ai(tmp_path):
    lib = tmp_path / "library"
    set_type(lib, "L1", "case", by="me")
    set_type(lib, "L1", "rct", by="ai")  # AI 不能蓋掉本人改的
    assert load_meta(lib)["items"]["L1"] == {"ptype": "case", "ptype_by": "me"}
    with pytest.raises(ValueError):
        set_type(lib, "L1", "nonsense", by="me")
    assert json.loads((lib / "meta.json").read_text())["items"]["L1"]["ptype"] == "case"


def test_rename_default_date_folder_moves_its_papers(tmp_path):
    lib = tmp_path / "library"
    items = [{"id": "L1", "library": {"discussion": "2026-10-21"}}, {"id": "L2", "library": {"discussion": "2026-10-12"}}]
    rename_folder(lib, "2026-10-21 Meeting", "10/21 Fukuoka 會議", items=items)
    m = load_meta(lib)
    assert folder_of(m, items[0]) == "10/21 Fukuoka 會議" and folder_of(m, items[1]) == "2026-10-12 Meeting"
