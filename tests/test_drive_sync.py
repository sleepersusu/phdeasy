import os
import time

from pipeline.drive_sync import find_drive, plan, sync


def _w(p, text, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if mtime:
        os.utime(p, (mtime, mtime))


def test_plan_one_side_changes_and_deletes():
    base = {"a": {"l": [1, 10.0], "r": [1, 10.0]}, "b": {"l": [1, 10.0], "r": [1, 10.0]},
            "c": {"l": [1, 10.0], "r": [1, 10.0]}}
    local = {"a": (2, 20.0), "b": (1, 10.0), "new": (1, 5.0)}  # a 這台改、c 這台刪
    remote = {"a": (1, 10.0), "b": (3, 30.0), "c": (1, 10.0)}  # b 雲端改
    acts = dict((r, a) for a, r in plan(local, remote, base))
    assert acts == {"a": "push", "b": "pull", "c": "del_remote", "new": "push"}


def test_plan_both_changed_keeps_newer_and_first_sync_never_deletes():
    base = {"x": {"l": [1, 10.0], "r": [1, 10.0]}}
    assert plan({"x": (2, 50.0)}, {"x": (3, 40.0)}, base) == [("conflict_push", "x")]
    assert plan({"x": (2, 30.0)}, {"x": (3, 40.0)}, base) == [("conflict_pull", "x")]
    assert plan({"only_l": (1, 1.0)}, {"only_r": (1, 1.0)}, {}) == [("push", "only_l"), ("pull", "only_r")]


def test_sync_roundtrip_two_computers(tmp_path):
    a, b, drive = tmp_path / "pcA", tmp_path / "pcB", tmp_path / "drive"
    _w(a / "prof1" / "card.json", "v1")
    sync(a, drive)
    sync(b, drive)
    assert (b / "prof1" / "card.json").read_text() == "v1"
    _w(b / "prof1" / "card.json", "v2-from-B", time.time() + 5)
    _w(b / "prof2" / "x.txt", "new")
    sync(b, drive)
    sync(a, drive)
    assert (a / "prof1" / "card.json").read_text() == "v2-from-B" and (a / "prof2" / "x.txt").exists()
    (a / "prof2" / "x.txt").unlink()
    sync(a, drive)
    assert not (drive / "prof2" / "x.txt").exists() and any((drive / "_同步刪除").rglob("x.txt"))


def test_find_drive_prefers_account(tmp_path):
    for acct in ("a@example.com", "b@example.com"):
        (tmp_path / "Library" / "CloudStorage" / f"GoogleDrive-{acct}" / "我的雲端硬碟").mkdir(parents=True)
    assert "b@example" in str(find_drive(tmp_path, prefer="b@example.com"))
