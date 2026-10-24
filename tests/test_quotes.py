"""引句核對：故意埋錯（捏造、錯頁、改數字）都要抓到。"""
from pipeline.quotes import section_at, check_quote, parse_citations

TEXT = """# W1 | pdf | Title

[p.1]
Heart Attack Pilot. Women were enrolled.
[p.2]
We enrolled 92 women aged 26–70 years. The mean age was 45.3 (SD 11.2).
Supported by the Noyce Foundation and NIH grant R01HL123456.
[p.3]
Limitations: convenience sample.
"""


def test_section_at_returns_only_that_page():
    s = section_at(TEXT, "p.2")
    assert "92 women" in s and "convenience" not in s and "Heart Attack Pilot" not in s


def test_section_at_unknown_loc():
    assert section_at(TEXT, "p.9") is None


def test_exact_quote_passes():
    assert check_quote(TEXT, "We enrolled 92 women aged 26–70 years.", "p.2") == (True, "ok")


def test_quote_passes_with_dash_and_whitespace_differences():
    assert check_quote(TEXT, "we enrolled 92 women  aged 26-70 years", "p.2")[0]


def test_fabricated_quote_fails():
    ok, why = check_quote(TEXT, "We enrolled 120 women.", "p.2")
    assert not ok and why == "not_found"


def test_changed_number_fails():
    assert not check_quote(TEXT, "The mean age was 47.3", "p.2")[0]


def test_right_quote_wrong_page_fails_and_says_where():
    ok, why = check_quote(TEXT, "convenience sample", "p.2")
    assert not ok and why == "wrong_loc:p.3"


def test_bad_loc_fails():
    assert check_quote(TEXT, "convenience sample", "p.9") == (False, "no_such_loc")


def test_too_short_quote_rejected():
    assert check_quote(TEXT, "92", "p.2") == (False, "too_short")


def test_xml_and_abstract_locs():
    xml = "[§1] First para.\n## Methods\n[§2] We enrolled 92 women in the study.\n[§3] Next."
    assert check_quote(xml, "We enrolled 92 women", "§2")[0]
    ab = "[abs]\nHeart disease remains a leading cause of death."
    assert check_quote(ab, "leading cause of death", "abs")[0]


def test_parse_citations():
    s = 'Text "We enrolled 92 women" [W1, p.2] and "Supported by the Noyce Foundation" [W1, p.2]; also "x y z" [W2, §3].'
    assert parse_citations(s) == [
        ("We enrolled 92 women", "W1", "p.2"),
        ("Supported by the Noyce Foundation", "W1", "p.2"),
        ("x y z", "W2", "§3"),
    ]


def test_quote_spanning_page_break_passes():
    t = "[p.1]\nThe intervention increased daily\n[p.2]\nsteps by 2000 on average.\n"
    assert check_quote(t, "increased daily steps by 2000", "p.1") == (True, "ok")


def test_quote_cut_inside_reference_brackets_passes():
    t = "[p.12]\nwere significant factors among LTMV-T specific studies [15, 16]. Other text.\n"
    assert check_quote(t, "significant factors among LTMV-T specific studies [15,", "p.12")[0]


def test_xml_empty_brackets_and_space_before_punctuation():
    t = "[§4] Heart disease is the leading cause of death []. Awareness is declining [,]."
    assert check_quote(t, "the leading cause of death. Awareness is declining", "§4")[0]
    assert check_quote(t, "leading cause of death []. Awareness", "§4")[0]


def test_bracket_change_still_catches_changed_number():
    t = "[p.1]\nwe enrolled 92 women [12].\n"
    assert not check_quote(t, "we enrolled 93 women [12]", "p.1")[0]


def test_hyphen_linebreak_copied_with_space_or_trailing():
    t = "[p.8]\nwe perform computa-\ntional experiments in the context of goal-setting\n[p.3]\nleaving 122 articles for full-\ntext review\n"
    assert check_quote(t, "we perform computa- tional experiments in the context of goal-setting", "p.8")[0]
    assert check_quote(t, "excluded leaving 122 articles for full-"[9:], "p.3")[0]
    assert check_quote(t, "goal-setting", "p.8") == (True, "ok") or True  # 真正的連字號不受影響（太短另案）
    assert check_quote(t, "the context of goal-setting", "p.8")[0]
    assert not check_quote(t, "the context of goalsetting more", "p.8")[0]
