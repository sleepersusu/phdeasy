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


def test_other_computer_in_use_blocks_unless_forced(tmp_path):
    a, b, drive = tmp_path / "A", tmp_path / "B", tmp_path / "drive"
    _w(a / "x.txt", "1")
    assert "blocked" not in sync(a, drive, my_id="pcA", device="Mac")
    assert sync(b, drive, my_id="pcB", device="Win") == {"blocked": "Mac"}
    assert "blocked" not in sync(b, drive, my_id="pcB", device="Win", force=True)
    from pipeline.drive_sync import release
    assert release(drive, my_id="pcB") and "blocked" not in sync(a, drive, my_id="pcA")


def test_switching_remote_folder_never_deletes(tmp_path):
    a = tmp_path / "A"
    _w(a / "keep.txt", "1")
    sync(a, tmp_path / "drive1", my_id="pcA")
    sync(a, tmp_path / "drive2", my_id="pcA")  # 新雲端是空的：不可以因為舊 base 把這台的檔刪掉
    assert (a / "keep.txt").exists() and (tmp_path / "drive2" / "keep.txt").exists()


def test_remote_json_suddenly_tiny_does_not_overwrite_local(tmp_path):
    a, drive = tmp_path / "A", tmp_path / "drive"
    _w(a / "state.json", '{"x": "' + "a" * 5000 + '"}')
    sync(a, drive, my_id="pcA")
    _w(drive / "state.json", "{}", time.time() + 10)
    n = sync(a, drive, my_id="pcA")
    assert n.get("shrunk") == 1 and len((a / "state.json").read_text()) > 5000
    assert any((drive / "_同步衝突").rglob("state.json"))


def test_plan_ignores_subsecond_mtime_drift():
    base = {"x": {"l": [5, 100], "r": [5, 100]}}
    assert plan({"x": (5, 100.7)}, {"x": (5, 100.2)}, base) == []


def test_pull_only_when_other_computer_in_use(tmp_path):
    a, b, drive = tmp_path / "A", tmp_path / "B", tmp_path / "drive"
    _w(a / "prof" / "card.json", "data")
    sync(a, drive, my_id="pcA", device="Mac")  # A 正在用（沒釋放）
    _w(b / "mine.txt", "b-only")
    n = sync(b, drive, my_id="pcB", device="Win", pull_only=True)
    assert n.get("pull") == 1 and (b / "prof" / "card.json").read_text() == "data"
    assert not (drive / "mine.txt").exists()  # 只拉不推
    from pipeline.drive_sync import read_lock
    assert read_lock(drive)["id"] == "pcA"  # 不搶使用中


def test_cli_sync_releases_unless_holding(tmp_path, monkeypatch):
    import drive_sync as cli
    from pipeline.drive_sync import read_lock
    drive = tmp_path / "drive"
    monkeypatch.setattr(cli, "target", lambda runs, *a, **k: drive)
    (tmp_path / "runs").mkdir()
    cli.run(tmp_path / "runs")
    assert not read_lock(drive).get("id")  # 一次性的同步（重建首頁、每段收尾）做完就放開
    cli.run(tmp_path / "runs", hold=True)
    assert read_lock(drive).get("id")  # 應用程式開著時才佔用


def test_cli_waits_for_release_before_giving_up(tmp_path, monkeypatch):
    import drive_sync as cli
    from pipeline.drive_sync import release
    drive = tmp_path / "drive"
    (tmp_path / "runs").mkdir()
    sync(tmp_path / "other", drive, my_id="pcB", device="Win")  # 別台佔著
    monkeypatch.setattr(cli, "target", lambda runs, *a, **k: drive)
    calls = []
    def fake_sleep(s):
        calls.append(s)
        release(drive, my_id="pcB")  # 等的時候那台的「已釋放」同步過來了
    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    assert cli.run(tmp_path / "runs", wait=60) == 0 and calls
