"""故意埋錯：Meeting 文件不一定是論文——表格要留成表格、掃描檔要轉錄、指引或檢核表不能被當成「不是正文」隔離。"""
import csv
import json

import pymupdf
import pytest

import library
from pipeline.reader import text_blocks
from pipeline.textify import pdf_to_marked


def _table_pdf(path):
    """一頁：一段文字＋一個 3 欄 3 列、有框線的表格。"""
    d = pymupdf.open()
    pg = d.new_page()
    pg.insert_text((72, 60), "Recommendation summary for evidence synthesis teams.")
    xs, ys = [72, 212, 352, 492], [100, 130, 160, 190]
    for x in xs:
        pg.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        pg.draw_line((xs[0], y), (xs[-1], y))
    cells = [["Stage", "Tool", "Rating"], ["Screening", "CoreSR", "Strong"], ["Extraction", "LLM", "Weak"]]
    for r, row in enumerate(cells):
        for c, t in enumerate(row):
            pg.insert_text((xs[c] + 6, ys[r] + 20), t)
    d.save(path)
    d.close()
    return path


def test_pdf_tables_kept_as_markdown_tables(tmp_path):
    text, n = pdf_to_marked(_table_pdf(tmp_path / "t.pdf"), tables=True)
    assert n == 1 and "Recommendation summary" in text
    rows = [l for l in text.splitlines() if l.startswith("|")]
    assert any("Screening" in r and "CoreSR" in r and "Strong" in r for r in rows)  # 同一列的格子在同一行
    assert text.count("CoreSR") == 1  # 表格裡的字不會在下面又重複一次
    plain, _ = pdf_to_marked(tmp_path / "t.pdf")
    assert not any(l.startswith("|") for l in plain.splitlines())  # 論文流程照舊


def test_reader_blocks_understand_tables_lists_and_headings():
    raw = ("# L1 | pdf | RAISE\n\n[p.1]\n## Recommendations\n- Use a protocol.\n- Report the AI tool.\n"
           "| Stage | Tool |\n| --- | --- |\n| Screening | CoreSR |\n| Extraction | LLM |\n\nPlain closing paragraph that ends here.\n")
    b = text_blocks(raw)
    kinds = [x["kind"] for x in b]
    assert kinds == ["h2", "li", "li", "table", "p"]
    t = b[3]
    assert t["rows"] == [["Stage", "Tool"], ["Screening", "CoreSR"], ["Extraction", "LLM"]] and t["head"] is True
    assert len({x["key"] for x in b}) == len(b)


def _lib(tmp_path):
    lib = tmp_path / "library"
    for d in ("work/text", "pdfs/2026", "inbox"):
        (lib / d).mkdir(parents=True)
    (lib / "work" / "works.json").write_text(json.dumps([{"id": "Lscan", "title": "RAISE 1", "kind": "full"}, {"id": "Wok", "title": "Paper", "kind": "full"}]))
    d = pymupdf.open()
    for _ in range(3):
        d.new_page()  # 3 頁空白＝掃描檔（沒有文字層）
    d.save(lib / "pdfs" / "2026" / "Lscan.pdf")
    d.close()
    with open(lib / "pdfs" / "index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "status", "path", "sha256"])
        w.writeheader()
        w.writerow({"id": "Lscan", "status": "ok", "path": "pdfs/2026/Lscan.pdf", "sha256": "x"})
        w.writerow({"id": "Wok", "status": "ok", "path": "pdfs/2026/Wok.pdf", "sha256": "y"})
    (lib / "work" / "ingest.json").write_text(json.dumps({"Lscan": {"source_type": "none", "exceptions": ["no_text"]},
                                                           "Wok": {"source_type": "pdf", "exceptions": []}}))
    return lib


def test_scanned_docs_listed_for_transcription_and_checked(tmp_path):
    lib = _lib(tmp_path)
    todo = library.ocr_todo(lib)
    assert [t["id"] for t in todo] == ["Lscan"] and todo[0]["pages"] == 3 and todo[0]["pdf"].endswith("Lscan.pdf")
    out = lib / "work" / "ocr"
    (out / "Lscan.txt").write_text("[p.1]\n## RAISE\n- one\n[p.2]\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")  # 少了第 3 頁
    with pytest.raises(ValueError, match="p.3"):
        library.ocr_apply(lib, "Lscan")
    (out / "Lscan.txt").write_text("[p.1]\n## RAISE\n- one\n[p.2]\n| a | b |\n| --- | --- |\n| 1 | 2 |\n[p.3]\n（空白頁）\n")
    library.ocr_apply(lib, "Lscan")
    text = (lib / "work" / "text" / "Lscan.txt").read_text()
    assert text.startswith("# Lscan | pdf | RAISE 1") and "[p.3]" in text
    ing = json.loads((lib / "work" / "ingest.json").read_text())["Lscan"]
    assert ing["source_type"] == "pdf" and ing["ocr"] is True and ing["source_path"] == "pdfs/2026/Lscan.pdf"
    assert library.ocr_todo(lib) == []  # 轉錄好了就不再列


def test_library_ingest_does_not_quarantine_guidelines(tmp_path):
    import ingest
    lib = _lib(tmp_path)
    p = _table_pdf(lib / "pdfs" / "2026" / "Wok.pdf")
    text, stype, exc = ingest.convert(lib, {"id": "Wok", "title": "Something totally different", "kind": "full"},
                                      {"status": "ok", "path": "pdfs/2026/Wok.pdf"}, library=True)
    assert stype == "pdf" and exc == [] and "| Screening" in text  # 標題對不上、像檢核表都不隔離；表格留著


def test_ocr_spacing_fix_splits_glued_english_words():
    from pipeline.textify import fix_ocr_spacing
    assert fix_ocr_spacing("PeoplewhomeettheICMJEcriteriaforauthorship") .startswith("People who meet the")
    assert fix_ocr_spacing("Screening,analysis;andreporting") == "Screening, analysis; and reporting"
    assert fix_ocr_spacing("短中文不動 and normal words stay") == "短中文不動 and normal words stay"


def test_scanned_pdf_gets_ocr_text_when_engine_available(tmp_path, monkeypatch):
    """掃描檔（沒有文字層）：用 OCR 套件讀出字；OCR 不能用就照舊留給轉錄者。"""
    import pipeline.textify as tx
    d = pymupdf.open()
    d.new_page()
    d.save(tmp_path / "scan.pdf")
    d.close()
    monkeypatch.setattr(tx, "_ocr_engine", lambda: (lambda png: ([[[[0, 10], [100, 10], [100, 20], [0, 20]], "Recommendationsforpractice", 0.9],
                                                                  [[[0, 25], [100, 25], [100, 35], [0, 35]], "second line of the same paragraph.", 0.9]], None)))
    text, n = pdf_to_marked(tmp_path / "scan.pdf", tables=True, ocr=True)
    assert "Recommendations for practice second line" in text
    monkeypatch.setattr(tx, "_ocr_engine", lambda: None)
    text, _ = pdf_to_marked(tmp_path / "scan.pdf", tables=True, ocr=True)
    assert text.strip() == "[p.1]"


def test_uploaded_pdf_counts_as_fulltext_before_processing(tmp_path):
    from pipeline.site import _library
    run = tmp_path / "doe-jane"
    lib = run / "library"
    (lib / "work").mkdir(parents=True)
    (lib / "inbox").mkdir()
    (lib / "work" / "works.json").write_text(json.dumps([{"id": "Lx1", "title": "RAISE", "year": None, "library": {}}]))
    (lib / "inbox" / "Lx1__upload_1.pdf").write_bytes(b"%PDF-1.4")
    w = _library(run)[0]
    assert w["fulltext"] == "ok" and w["pdf_href"] == "../../library/inbox/Lx1__upload_1.pdf"


# ---------- 上傳的檔案轉不成可讀資料（2026-10-27 本人回報）：一次把整條路修好 ----------
def test_inbox_upload_names_match_on_any_os():
    from pipeline.fetch import match_inbox
    works = [{"id": "Le8f1a128"}, {"id": "W4379966791", "doi": "10.1/x"}]
    m = match_inbox({r"C:\Users\su\phdeasy\runs\x\library\inbox\Le8f1a128__upload_20261027.pdf": "",
                     "/Users/u/runs/x/library/inbox/W4379966791__upload_2.pdf": ""}, works)
    assert set(m) == {"Le8f1a128", "W4379966791"}  # id 後面接 _ 也要對得上；Windows 路徑也一樣
    assert match_inbox({"/x/inbox/W43799667911_other.pdf": ""}, works) == {}  # 多一個數字就不是同一篇


def test_file_urls_survive_windows_paths_and_spaces(tmp_path):
    from pipeline.http import file_url, path_of_file_url, get
    assert path_of_file_url(file_url(r"C:\Users\蘇\phd easy\inbox\a.pdf")) == "C:/Users/蘇/phd easy/inbox/a.pdf"
    p = tmp_path / "有 空白.pdf"
    p.write_bytes(b"%PDF-1.4 x")
    assert get(file_url(str(p))) == (b"%PDF-1.4 x", "ok")


def test_hash_check_tolerates_deleted_uploads_and_windows_keys(tmp_path):
    import ingest
    run = tmp_path / "library"
    (run / "inbox").mkdir(parents=True)
    keep = run / "inbox" / "W1__upload_1.pdf"
    keep.write_bytes(b"%PDF a")
    h = {"inbox\\W1__upload_1.pdf": ingest.sha256_file(keep), "inbox\\W9__upload_9.pdf": "deadbeef"}  # W9 本人刪了（移到 _已刪除）
    assert ingest.verify_hashes(run, h, library=True) == []
    assert set(h) == {"inbox/W1__upload_1.pdf"}  # 反斜線改成 /，刪掉的不再檢查
    keep.write_bytes(b"%PDF changed")
    assert ingest.verify_hashes(run, h, library=True) == ["inbox/W1__upload_1.pdf"]  # 內容真的被改：照樣擋
    h2 = {"inbox/W9__upload_9.pdf": "deadbeef"}
    assert ingest.verify_hashes(run, h2) == ["inbox/W9__upload_9.pdf"]  # 教授批次照舊嚴格
