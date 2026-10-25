import pymupdf

from pipeline.textify import (
    pdf_to_marked,
    xml_to_marked,
    abstract_to_marked,
    has_text,
    title_matches,
    normalize_for_match,
    units,
)


def make_pdf(path, pages):
    doc = pymupdf.open()
    for t in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), t, fontsize=10)
    doc.save(path)


def test_pdf_pages_get_markers(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["Walking Study Title\nIntro text here.", "Results: n = 120 women."])
    text, n = pdf_to_marked(p)
    assert n == 2
    assert text.index("[p.1]") < text.index("Walking Study") < text.index("[p.2]") < text.index("n = 120")


def test_scanned_pdf_has_no_text(tmp_path):
    p = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(p)
    text, n = pdf_to_marked(p)
    assert n == 1 and not has_text(text)


JATS = b"""<?xml version="1.0"?>
<article><front><article-meta>
 <title-group><article-title>AI HeartBot Pilot</article-title></title-group>
 <funding-group><award-group><funding-source>NIH</funding-source><award-id>R01HL123</award-id></award-group></funding-group>
 <abstract><sec><title>Background</title><p>Heart attack awareness is low.</p></sec></abstract>
</article-meta></front>
<body>
 <sec><title>Methods</title><p>We enrolled <bold>92</bold> women.</p>
  <table-wrap><caption><p>Table 1. Characteristics</p></caption></table-wrap></sec>
 <sec><title>Results</title><p>Knowledge improved.</p></sec>
</body>
<back><ack><p>We thank the participants.</p></ack>
 <ref-list><ref><mixed-citation>Smith J. Some cited paper. 2020.</mixed-citation></ref></ref-list></back>
</article>"""


def test_xml_paragraphs_numbered_and_sections_kept():
    text, n = xml_to_marked(JATS)
    assert "[§1]" in text
    assert "We enrolled 92 women." in text
    assert text.index("## Methods") < text.index("We enrolled") < text.index("## Results")
    assert "Table 1. Characteristics" in text
    assert "We thank the participants." in text  # 致謝要留（grants 會用）
    assert "R01HL123" in text  # 補助資訊要留
    assert "Some cited paper" not in text  # 參考文獻不要
    assert n == units(text)


def test_abstract_marker():
    text = abstract_to_marked("Short abstract.")
    assert text.startswith("[abs]") and "Short abstract." in text


def test_has_text_threshold():
    assert has_text("[p.1]\n" + "word " * 400)
    assert not has_text("[p.1]\n\n[p.2]\n  ")


def test_title_matches_with_hyphenation_and_case():
    text = "[p.1]\nJMIR Cardio\nAn App-Based Physical Activ-\nity Intervention in Community-Dwelling Women\nAbstract ..."
    assert title_matches(text, "An App-Based Physical Activity Intervention in Community-Dwelling Women")


def test_title_mismatch_detects_wrong_file():
    text = "[p.1]\nQuality of life among colorectal cancer survivors: a pilot trial\n..."
    assert not title_matches(text, "AI HeartBot to Increase Women's Awareness and Knowledge of Heart Attack")


def test_normalize_for_match_unifies_ligatures_quotes_dashes():
    a = normalize_for_match("The ﬁrst “effect” – was signiﬁ-\ncant")
    b = normalize_for_match('the first "effect" - was significant')
    assert a == b


def test_soft_hyphen_at_line_break_rejoins_word():
    # 「can\u00ad\ncer」在 PDF 是斷行處的軟連字號，比對時要接回「cancer」，不能變成「can cer」
    assert normalize_for_match("global can\u00ad\ncer morbidity") == "global cancer morbidity"
    assert normalize_for_match("Aus\u00ad \n tralian adults") == "australian adults"


def test_units_counts_markers():
    assert units("[p.1]\na\n[p.2]\nb") == 2
    assert units("[§1] a\n[§2] b\n[§3] c") == 3


def test_supplement_first_page_detected():
    from pipeline.textify import looks_like_supplement
    assert looks_like_supplement("[p.1]\n10/6/21, 8:01 PM\nCONSORT-EHEALTH (V 1.6.1) - Submission/Publication Form\n...")
    assert looks_like_supplement("[p.1]\nMultimedia Appendix 2. Interview guide\n...")
    assert looks_like_supplement("[p.1]\nSupplementary Material\nTable S1 ...")
    assert not looks_like_supplement("[p.1]\nJMIR Cancer\nFeasibility and Acceptability of a Physical Activity Tracker\nAbstract\nBackground: ... CONSORT diagram in Figure 1")


def test_pdf_control_char_minus_restored():
    from pipeline.textify import clean_pdf_text
    assert clean_pdf_text("β = \x020.02 (95% CI \x020.04 to \x020.01)") == "β = −0.02 (95% CI −0.04 to −0.01)"
    assert clean_pdf_text("plain text") == "plain text"


def test_clean_pdf_text_restores_mid_dot_decimal_encoded_as_dollar():
    from pipeline.textify import clean_pdf_text
    assert clean_pdf_text("GPs surveyed (94$7%) were; cost US$5 and $20") == "GPs surveyed (94.7%) were; cost US$5 and $20"
