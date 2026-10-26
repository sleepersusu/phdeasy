"""計畫書 Word 檔匯入：依原檔順序保留標題、段落、圖（原始圖檔）與表（真的表格），圖表標題要跟到對的圖表上。"""
import zipfile

from pipeline.docx_doc import parse_docx

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def p(text, style=None):
    st = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{st}<w:r><w:t>{text}</w:t></w:r></w:p>"


def tbl(rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows) + "</w:tbl>"


DRAWING = '<w:p><w:r><w:drawing><a:graphic><a:graphicData><a:blip r:embed="rId5"/></a:graphicData></a:graphic></w:drawing></w:r></w:p>'


def make_docx(path):
    body = (p("When to Ask", "ProposalTitle") + p("Evidence synthesis", "ProposalSubtitle") + p("Lead Supervisor: A/Prof X")
            + p("Synopsis") + p("Short synopsis.")
            + p("1. Rationale and Research Gap", "ProposalHeading1") + p("Gap text.", "ProposalBody")
            + DRAWING + p("Figure 1. Programme overview.", "ProposalCaption")
            + p("3. Research Programme and Methodology", "ProposalHeading1") + p("3.1 Study 1 - Review", "ProposalHeading2")
            + p("3.1.1 Outcomes", "ProposalBody") + p("Table 2. Controlled comparison", "ProposalCaption")
            + tbl([["Condition", "Action"], ["Agentic", "Ask one item"]])
            + p("References", "ProposalHeading1") + p("1. Someone. A paper.", "ProposalReference"))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId5" Type="image" Target="media/image1.png"/></Relationships>')
        z.writestr("word/media/image1.png", b"\x89PNG fake")


def test_parse_keeps_order_figures_tables_and_captions(tmp_path):
    f = tmp_path / "p.docx"
    make_docx(f)
    d = parse_docx(f)
    assert d["title"] == "When to Ask" and d["subtitle"] == "Evidence synthesis" and d["meta"] == ["Lead Supervisor: A/Prof X"]
    assert [s["key"] for s in d["sections"]] == ["synopsis", "rationale", "programme", "references"]
    rat = d["sections"][1]["blocks"]
    assert rat[0] == {"type": "p", "en": "Gap text."}
    assert rat[1] == {"type": "figure", "media": "image1.png", "caption_en": "Figure 1. Programme overview."}
    prog = d["sections"][2]["blocks"]
    assert [b["type"] for b in prog] == ["h2", "h3", "table"]
    assert prog[2]["caption_en"] == "Table 2. Controlled comparison" and prog[2]["rows"] == [["Condition", "Action"], ["Agentic", "Ask one item"]]
    assert d["sections"][3]["blocks"] == [{"type": "ref", "en": "1. Someone. A paper."}]
    assert d["media"] == {"image1.png": b"\x89PNG fake"}


def test_statement_paragraphs_with_title_and_placeholder(tmp_path):
    # Personal Statement 沒有標題樣式：前兩行是姓名與標題，其餘每段一個區塊；[方括號] 的是本人留的待填說明
    from pipeline.docx_doc import parse_statement
    f = tmp_path / "ps.docx"
    body = p("YU-HSIANG SU") + p("Personal Statement / Statement of Purpose") + p("First paragraph.") + p("[FIT: adapt per programme]") + p("Last.")
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    d = parse_statement(f)
    assert d["author"] == "YU-HSIANG SU" and d["title"] == "Personal Statement / Statement of Purpose"
    assert d["blocks"] == [{"type": "p", "en": "First paragraph."}, {"type": "note", "en": "[FIT: adapt per programme]"}, {"type": "p", "en": "Last."}]
