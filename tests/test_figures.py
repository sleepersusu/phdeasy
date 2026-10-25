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
