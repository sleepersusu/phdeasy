import pytest
from pipeline.index import load_index, save_index, find_existing


def test_save_and_load_roundtrip(tmp_path):
    (tmp_path / "pdfs").mkdir()
    save_index(tmp_path, {"W1": {"id": "W1", "year": 2022, "status": "ok"}, "W2": {"id": "W2", "year": "2021", "status": "ok"}})
    idx = load_index(tmp_path)
    assert list(idx) == ["W2", "W1"] and idx["W1"]["status"] == "ok"


def test_failed_save_keeps_previous_file(tmp_path):
    (tmp_path / "pdfs").mkdir()
    save_index(tmp_path, {"W1": {"id": "W1", "year": 2022, "status": "ok"}})
    with pytest.raises(Exception):
        save_index(tmp_path, {"W1": {"id": "W1", "year": 2022, "status": "ok"}, "W2": None})
    assert load_index(tmp_path)["W1"]["status"] == "ok"


def test_find_existing_file(tmp_path):
    d = tmp_path / "pdfs" / "2023"
    d.mkdir(parents=True)
    (d / "W5_Chang_X.pdf").write_bytes(b"%PDF-1.4")
    (d / "W55_Other_Y.pdf").write_bytes(b"%PDF-1.4")
    assert find_existing(tmp_path, "W5") == "pdfs/2023/W5_Chang_X.pdf"
    assert find_existing(tmp_path, "W6") is None


def test_find_existing_ignores_rejected_folder(tmp_path):
    d = tmp_path / "pdfs" / "_rejected"
    d.mkdir(parents=True)
    (d / "W7_X_Y.pdf").write_bytes(b"%PDF-1.4")
    assert find_existing(tmp_path, "W7") is None


def test_reject_file_moves_and_keeps_hash(tmp_path):
    from pipeline.index import reject_file
    (tmp_path / "pdfs" / "2022").mkdir(parents=True)
    f = tmp_path / "pdfs" / "2022" / "W7_X_Y.pdf"
    f.write_bytes(b"%PDF-1.4")
    hashes = {"pdfs/2022/W7_X_Y.pdf": "abc"}
    index = {"W7": {"id": "W7", "year": 2022, "status": "ok", "path": "pdfs/2022/W7_X_Y.pdf", "url": "u"}}
    new_rel = reject_file(tmp_path, "W7", index, hashes)
    assert not f.exists() and (tmp_path / new_rel).exists()
    assert new_rel.startswith("pdfs/_rejected/")
    assert hashes == {new_rel: "abc"}
    assert "W7" not in index
