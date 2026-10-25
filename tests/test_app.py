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


def test_install_bundle_never_touches_runs(tmp_path):
    from app import install_bundle
    src, ws = tmp_path / "bundle", tmp_path / "ws"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "a.py").write_text("v2")
    (ws / "runs" / "prof").mkdir(parents=True)
    (ws / "runs" / "prof" / "card.json").write_text("keep")
    assert install_bundle(src, ws, "v2") and (ws / "scripts" / "a.py").read_text() == "v2"
    assert (ws / "runs" / "prof" / "card.json").read_text() == "keep"
    assert install_bundle(src, ws, "v2") is False  # 同一版不重複複製


def test_post_requires_app_header(tmp_path):
    import http.client, threading, http.server
    from app import App, make_handler
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("home")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_port)
        c.request("POST", "/api/stop", body="{}", headers={"Content-Type": "application/json"})
        assert c.getresponse().status == 403
        c.request("GET", "/web/index.html"); r = c.getresponse()
        assert r.status == 200 and r.read() == b"home"
        c.request("GET", "/web/../../etc/passwd"); r = c.getresponse(); r.read()
        assert r.status == 404
    finally:
        srv.shutdown()
