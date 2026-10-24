from pipeline.export import to_ris, unpaired_preprints


W = [
    {"id": "W1", "doi": "10.1/a", "title": "Study A", "year": 2024, "type": "article", "venue": "J A",
     "authors": [{"name": "Yoshimi Fukuoka"}, {"name": "Jane Doe"}], "abstract": "Abs.", "kind": "full"},
    {"id": "W2", "doi": None, "title": "Abstract 1: Poster", "year": 2023, "type": "conference-abstract", "venue": None,
     "authors": [], "abstract": None, "kind": "short"},
]
INDEX = {"W1": {"status": "ok", "path": "pdfs/2024/W1_Fukuoka_Study-A.pdf"}, "W2": {"status": "not_needed", "path": ""}}


def test_ris_has_one_record_per_work_with_file_link(tmp_path):
    ris = to_ris(W, INDEX, tmp_path, tags=["phdeasy:fukuoka"])
    recs = [r for r in ris.split("ER  -") if r.strip()]
    assert len(recs) == 2
    assert "TY  - JOUR" in recs[0] and "TY  - ABST" in recs[1]
    assert "AU  - Fukuoka, Yoshimi" in recs[0]
    assert f"L1  - file://{tmp_path}/pdfs/2024/W1_Fukuoka_Study-A.pdf" in recs[0]
    assert "DO  - 10.1/a" in recs[0]
    assert "KW  - phdeasy:fukuoka" in recs[0]
    assert "N1  - OpenAlex W1" in recs[0]
    assert "L1  -" not in recs[1]


def test_unpaired_preprints_reports_best_match():
    works = [
        {"id": "P", "type": "preprint", "title": "Risk Factors Associated with Readmission Among Children: A Protocol"},
        {"id": "A", "type": "article", "title": "Readmission among children: a systematic review"},
        {"id": "B", "type": "article", "title": "Unrelated walking study"},
    ]
    out = unpaired_preprints(works)
    assert out[0]["id"] == "P" and out[0]["best_match"] == "A"
    assert 0 < out[0]["score"] < 1


def test_render_paper_md_has_all_fields_and_citations():
    from pipeline.export import render_paper_md, paper_md_name
    w = {"id": "W1", "title": "Study A", "year": 2024, "venue": "J A", "doi": "10.1/a", "type": "article",
         "authors": [{"name": "Ann Lee"}, {"name": "Yoshimi Fukuoka"}], "target_position": "last", "target_corresponding": True}
    card = {"basis": "fulltext", "fields": {
        "summary": {"status": "ok", "text": "大意", "citations": [{"quote": "We enrolled 92 women", "loc": "p.2"}]},
        "design": {"status": "ok", "type": "rct", "text": "隨機", "citations": []},
        "sample": {"status": "unresolved", "text": "出處核對未通過", "citations": []},
        "gap": {"status": "not_in_source", "claims": []},
        "solves": {"status": "ok", "claims": [{"text": "問題", "citations": [{"quote": "aim of this study was", "loc": "p.1"}]}]},
        "findings": {"status": "ok", "claims": [{"text": "結果", "citations": []}]},
        "limitations": {"status": "ok", "author_stated": [{"text": "小樣本", "citations": []}], "inferred": [{"text": "無對照", "basis": "單組", "citations": []}]}}}
    md = render_paper_md(w, card)
    for label in ["大意", "研究設計", "研究樣本", "研究缺口", "解決什麼", "發現", "研究限制"]:
        assert f"## {label}" in md
    assert '"We enrolled 92 women" [W1, p.2]' in md
    assert "來源未提及" in md and "判不出來" in md and "推論（非作者原話）" in md
    assert paper_md_name(w) == "2024_Lee_Study-A_W1.md"
