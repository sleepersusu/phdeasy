import socket
from pathlib import Path

from app import Closer, free_port


def test_free_port_skips_busy_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert free_port(busy) != busy


def test_closer_syncs_and_releases_once(tmp_path):
    calls = []
    c = Closer(tmp_path, sync=lambda r: calls.append("sync"), rel=lambda d: calls.append("release"), tgt=lambda r: tmp_path)
    c()
    c()  # 訊號和 atexit 都會叫：只做一次
    assert calls == ["sync", "release"]


def test_choose_account_asks_once_when_several_drives(tmp_path):
    from app import choose_account
    drives = [("a@example.com", tmp_path / "a"), ("b@example.com", tmp_path / "b")]
    answers = iter(["9", "2"])
    assert choose_account(tmp_path, drives, ask=lambda _: next(answers)) == "b@example.com"
    assert choose_account(tmp_path, drives, ask=lambda _: 1 / 0) == "b@example.com"  # 記住了，不再問
