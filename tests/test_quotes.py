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
