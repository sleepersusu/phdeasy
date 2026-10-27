"""故意埋錯：上傳 PDF（Windows 不能改名開著的檔：讀完要先關；同一個檔重傳不能多一筆；之前沒改到名的要能對回去）。"""
import json
from pathlib import Path

import pymupdf
import pytest

import library


def _pdf(path, text="Short scanned-like note"):
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), text)
    d.save(path)
    d.close()
    return path


@pytest.fixture
def lib(tmp_path):
    lib = tmp_path / "library"
    (lib / "work").mkdir(parents=True)
    (lib / "inbox").mkdir()
    (lib / "work" / "works.json").write_text("[]")
    return lib


def test_pdf_is_closed_before_rename_like_windows(lib, monkeypatch):
    opened = []
    real_open = pymupdf.open

    def tracking(*a, **k):
        d = real_open(*a, **k)
        opened.append(d)
        return d
    monkeypatch.setattr(pymupdf, "open", tracking)
    real_rename = Path.rename

    def windows_rename(self, target):  # Windows：檔案還開著就不准改名
        if any(not d.is_closed for d in opened):
            raise PermissionError("[WinError 32] 程序無法存取檔案，因為檔案正由另一個程序使用。")
        return real_rename(self, target)
    monkeypatch.setattr(Path, "rename", windows_rename)
    up = _pdf(lib / "inbox" / "_upload_1.pdf")
    w = library.add_pdf(lib, up, given_by="L", discussion="2026-10-27", note=None, today="2026-10-27")
    assert (lib / "inbox" / f"{w['id']}__upload_1.pdf").exists() and not up.exists()


def test_rename_refused_falls_back_to_copy(lib, monkeypatch):
    monkeypatch.setattr(Path, "rename", lambda self, t: (_ for _ in ()).throw(PermissionError("WinError 32")))
    up = _pdf(lib / "inbox" / "_upload_1.pdf")
    w = library.add_pdf(lib, up, given_by="L", discussion=None, note=None, today="2026-10-27")
    assert (lib / "inbox" / f"{w['id']}__upload_1.pdf").exists()  # 對得上文章 id 的那一份一定要有


def test_same_file_twice_is_one_entry_and_duplicates_are_cleaned(lib):
    a = _pdf(lib / "inbox" / "_upload_1.pdf")
    b = lib / "inbox" / "_upload_2.pdf"
    b.write_bytes(a.read_bytes())
    w1 = library.add_pdf(lib, a, given_by="L", discussion=None, note=None, today="2026-10-27")
    w2 = library.add_pdf(lib, b, given_by="L", discussion=None, note=None, today="2026-10-27")
    works = json.loads((lib / "work" / "works.json").read_text())
    assert w1["id"] == w2["id"] and len(works) == 1
    (lib / "work" / "works.json").write_text(json.dumps(works + works))  # 舊版重試留下的重複
    library._save(lib, library._load(lib))
    assert len(json.loads((lib / "work" / "works.json").read_text())) == 1


def test_relink_old_uploads_that_were_never_renamed(lib):
    a = _pdf(lib / "inbox" / "_upload_1.pdf")
    w = library.add_pdf(lib, a, given_by="L", discussion=None, note=None, today="2026-10-27")
    orphan = lib / "inbox" / "_upload_9.pdf"  # 舊版在 Windows 加進去了、但改名失敗留下的
    orphan.write_bytes((lib / "inbox" / f"{w['id']}__upload_1.pdf").read_bytes())
    stranger = _pdf(lib / "inbox" / "_upload_8.pdf", text="a different file never added")
    assert library.relink_uploads(lib) == 1
    assert (lib / "inbox" / f"{w['id']}__upload_9.pdf").exists() and stranger.exists()


def test_many_uploads_at_once_all_get_added(lib):
    """同一位教授一次丟很多篇（各自一個程序同時跑）：查資料可以同時，寫清單時輪流，一篇都不能少。"""
    import threading
    pdfs = [_pdf(lib / "inbox" / f"_upload_{i}.pdf", text=f"different paper number {i}") for i in range(8)]
    errs = []

    def add(p):
        try:
            library.add_pdf(lib, p, given_by="L", discussion=None, note=None, today="2026-10-27")
        except Exception as e:
            errs.append(e)
    ts = [threading.Thread(target=add, args=(p,)) for p in pdfs]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(json.loads((lib / "work" / "works.json").read_text())) == 8
