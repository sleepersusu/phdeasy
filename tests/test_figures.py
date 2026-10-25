"""故意埋錯：內文提到「Table 1 shows…」不能當成表格標題；同一張圖只算一次；每張圖表都要抓到。"""
import pymupdf

from pipeline.figures import captions_from_blocks, from_jats, from_pdf


def test_captions_skip_in_text_mentions_and_duplicates():
    blocks = [(2, "As Table 1 shows, the groups were similar."), (3, "Table 1. Baseline characteristics of participants"),
              (4, "Figure 1: CONSORT flow diagram"), (5, "Fig. 1 CONSORT flow diagram (continued)"), (6, "Figure 2 Change in AFEQT score"),
              (7, "Supplementary Table S1 Search strategy")]
    caps = captions_from_blocks(blocks)
    assert [(c["label"], c["page"]) for c in caps] == [("Table 1", 3), ("Figure 1", 4), ("Figure 2", 6), ("Supplementary Table S1", 7)]


def test_pdf_pages_rendered(tmp_path):
    doc = pymupdf.open()
    for t in ("Intro text", "Table 1. Characteristics\nAge 60", "Figure 1. Flow chart"):
        doc.new_page().insert_text((72, 72), t)
    doc.save(tmp_path / "a.pdf")
    items = from_pdf(tmp_path / "a.pdf", tmp_path / "out")
    assert [i["label"] for i in items] == ["Table 1", "Figure 1"]
    assert (tmp_path / "out" / "p2.png").exists() and items[1]["loc"] == "p.3"


def test_jats_figs_and_tables():
    xml = b"""<article><body><fig id="f1"><label>Figure 1</label><caption><p>Study flow</p></caption></fig>
      <table-wrap id="t1"><label>Table 1</label><caption><title>Baseline</title></caption></table-wrap></body></article>"""
    items = from_jats(xml)
    assert [i["label"] for i in items] == ["Figure 1", "Table 1"] and "Study flow" in items[0]["caption"]


def test_caption_in_the_middle_of_a_block_is_found():
    blocks = [(5, "Results were consistent.\nTable 2  OR of cardiovascular disease according to menopause category\nAge-adjusted model")]
    assert [c["label"] for c in captions_from_blocks(blocks)] == ["Table 2"]


def test_non_english_labels():
    caps = captions_from_blocks([(2, "Encadré 1 Les principes de McWhinney"), (3, "Tableau 2. Caractéristiques"), (4, "Tabla 1 Resultados")])
    assert [c["label"] for c in caps] == ["Encadré 1", "Tableau 2", "Tabla 1"]


def test_real_caption_beats_body_text_starting_with_label():
    blocks = [(9, "Fig. 5 The nursing model was developed in response to evidence that modifiable risk factors were common, and nurses provided " + "long text " * 60),
              (11, "Fig. 5 An overview of nursing model of care")]
    caps = captions_from_blocks(blocks)
    assert caps[0]["page"] == 11 and "overview" in caps[0]["caption"]


def test_soft_hyphen_ignored_when_matching_quotes():
    from pipeline.quotes import check_quote
    text = "[p.1]\nWe used a meta­analysis of eleven trials in adults.\n"
    assert check_quote(text, "We used a meta-analysis of eleven trials", "p.1")[0] or check_quote(text, "We used a metaanalysis of eleven trials", "p.1")[0]
    assert check_quote(text, "We used a meta­analysis of eleven trials", "p.1")[0]
