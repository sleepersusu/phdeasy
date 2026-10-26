"""本人的文件（Research Proposal、Personal Statement、Statement of Purpose）：上傳就成一個版本，每段 AI 編修成新版本，舊版都留著。"""
import json
import zipfile

import pytest

from pipeline.mydocs import DOC_KINDS, apply_edit, doc_key, list_versions, new_version, parse_upload

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(path, paras):
    body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paras)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
        z.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    return path


def test_kinds_and_keys():
    assert set(DOC_KINDS) == {"proposal", "ps", "sop"}
    assert doc_key("ps") == "ps" and doc_key("proposal", "laranjo-liliana") == "proposal--laranjo-liliana"
    with pytest.raises(ValueError):
        doc_key("cv")
    with pytest.raises(ValueError):
        doc_key("proposal", "../x")


def test_upload_docx_becomes_version_1_and_keeps_original(tmp_path):
    src = docx(tmp_path / "ps.docx", ["YU-HSIANG SU", "Personal Statement", "First paragraph.", "Second."])
    root = tmp_path / "docs"
    v = new_version(root, "ps", parse_upload(src), source=src, note="上傳 ps.docx")
    assert v["n"] == 1 and v["origin"] == "upload"
    d = json.loads((root / "ps" / "v1" / "doc.json").read_text())
    assert [b["en"] for b in d["blocks"]] == ["First paragraph.", "Second."] and d["title"] == "Personal Statement"
    assert (root / "ps" / "v1" / "source.docx").read_bytes() == src.read_bytes()
    assert [x["n"] for x in list_versions(root, "ps")] == [1]


def test_upload_pdf_paragraphs(tmp_path):
    import pymupdf
    pdf = tmp_path / "sop.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Statement of Purpose")
    page.insert_text((72, 110), "I want to study AI.")
    page.insert_text((72, 150), "I have built systems.")
    doc.save(pdf)
    d = parse_upload(pdf)
    assert d["title"] == "Statement of Purpose" and [b["en"] for b in d["blocks"]] == ["I want to study AI.", "I have built systems."]


def test_ai_edit_makes_new_version_and_keeps_old(tmp_path):
    src = docx(tmp_path / "ps.docx", ["Name", "Title", "Old first.", "Second."])
    root = tmp_path / "docs"
    new_version(root, "ps", parse_upload(src), source=src)
    v2 = apply_edit(root, "ps", base=1, block=0, en="New first.", zh="新的第一段。", note="更精簡")
    assert v2["n"] == 2 and v2["origin"] == "ai-edit" and v2["changed"] == [0] and v2["base"] == 1
    new = json.loads((root / "ps" / "v2" / "doc.json").read_text())
    old = json.loads((root / "ps" / "v1" / "doc.json").read_text())
    assert new["blocks"][0] == {"type": "p", "en": "New first.", "zh": "新的第一段。"} and new["blocks"][1]["en"] == "Second."
    assert old["blocks"][0]["en"] == "Old first."  # 舊版不動
    with pytest.raises(ValueError):
        apply_edit(root, "ps", base=2, block=9, en="x", zh="x")
    with pytest.raises(ValueError):  # 數字對不上：中英要一致
        apply_edit(root, "ps", base=2, block=0, en="We enrolled 120.", zh="收了 100 人。")
