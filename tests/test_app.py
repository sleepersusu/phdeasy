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


def test_find_app_browser_prefers_edge(tmp_path):
    from pipeline.window import find_app_browser
    edge = tmp_path / "pf86" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_text("")
    assert find_app_browser({"ProgramFiles(x86)": str(tmp_path / "pf86")}).endswith("msedge.exe")


def test_account_chosen_in_window(tmp_path):
    from app import App
    a = App(tmp_path)
    a.drive_choices = ["a@x.com", "b@x.com"]
    a.need_account.set()
    assert a.status()["need_account"] is True
    a.post("account", {"account": "b@x.com"})
    assert a.account_chosen.is_set() and '"b@x.com"' in (tmp_path / "runs" / "_me" / "drive.json").read_text()


def test_upload_saves_pdf_into_inbox_without_overwrite(tmp_path):
    import pytest
    from app import App
    a = App(tmp_path)
    (tmp_path / "runs" / "prof").mkdir(parents=True)
    (tmp_path / "runs" / "prof" / "state.json").write_text("{}")
    assert a.upload("prof", "W1", b"%PDF-1.7 x")["saved"] == "prof/inbox/W1.pdf"
    assert a.upload("prof", "W1", b"%PDF-1.7 y")["saved"] == "prof/inbox/W1-2.pdf"
    with pytest.raises(ValueError):
        a.upload("prof", "W1", b"<html>not pdf")
    with pytest.raises(ValueError):
        a.upload("../etc", "W1", b"%PDF-1.7")


def test_settings_reports_keys_without_values_and_switches_account(tmp_path, monkeypatch):
    import pytest
    import app as appmod
    a = appmod.App(tmp_path)
    (tmp_path / "runs" / "_me").mkdir(parents=True)
    (tmp_path / "runs" / "_me" / "secrets.env").write_text("S2_API_KEY=secret-value\n")
    monkeypatch.setattr(appmod, "find_drives", lambda: [("a@x.com", tmp_path / "a"), ("b@x.com", tmp_path / "b")])
    monkeypatch.setattr(appmod, "target", lambda runs, *k: None)
    st = a.settings()
    assert st["keys"]["S2_API_KEY"] is True and "secret-value" not in str(st) and st["drives"] == ["a@x.com", "b@x.com"]
    started = []
    monkeypatch.setattr(appmod.App, "resync", lambda self: started.append(1) or {"ok": True})
    a.syncing = False
    a.post("account", {"account": "b@x.com"})
    assert started and '"b@x.com"' in (tmp_path / "runs" / "_me" / "drive.json").read_text()
    import pytest
    with pytest.raises(ValueError):
        a.post("account", {"account": "nobody@x.com"})


def test_propose_route_starts_job_for_known_professor(tmp_path):
    from app import App
    app = App(tmp_path)
    (tmp_path / "runs" / "doe-jane").mkdir(parents=True)
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text("{}")
    started = []
    app.jobs.start = lambda kind, prompt, title, slug=None: started.append((kind, title, slug)) or {"ok": True}
    app.blocked = None
    app.post("propose", {"slug": "doe-jane"})
    assert started == [("propose", "研究構想草稿：doe-jane", "doe-jane")]
    import pytest
    with pytest.raises(ValueError):
        app.post("propose", {"slug": "nobody"})


def test_propose_route_refuses_finalized_professor(tmp_path):
    import json, pytest
    from app import App
    app = App(tmp_path)
    (tmp_path / "runs" / "_me").mkdir(parents=True)
    (tmp_path / "runs" / "_me" / "me.json").write_text(json.dumps({"proposal_with": "doe-jane", "proposal": {"title": "x"}}))
    (tmp_path / "runs" / "doe-jane").mkdir()
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text("{}")
    app.jobs.start = lambda *a, **k: pytest.fail("不該開工")
    app.blocked = None
    with pytest.raises(ValueError, match="定案"):
        app.post("propose", {"slug": "doe-jane"})


def _lib_app(tmp_path):
    from app import App
    app = App(tmp_path)
    (tmp_path / "runs" / "doe-jane").mkdir(parents=True)
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text("{}")
    app.blocked = None
    calls = []
    app.lib_script = lambda *a: calls.append(a) or "ADD W1 2024 Paper"
    app._rebuild_site = lambda slug: None
    app._bg = lambda fn: fn()  # 背景工作在測試裡直接跑完
    app.jobs.start = lambda kind, prompt, title, slug=None, key=None, session=None: calls.append(("job", kind, slug, prompt)) or {"ok": True}
    return app, calls


def test_library_upload_saves_pdf_then_adds_with_who_gave_it(tmp_path):
    import pytest
    app, calls = _lib_app(tmp_path)
    with pytest.raises(ValueError):
        app.library_upload("doe-jane", b"not a pdf", {})
    r = app.library_upload("doe-jane", b"%PDF-1.7 ...", {"given_by": "Jane", "discussion": "2026-11-03"})
    saved = list((tmp_path / "runs" / "doe-jane" / "library" / "inbox").glob("*.pdf"))
    assert len(saved) == 1 and r["ok"]
    args = calls[0]
    assert args[0] == "add-pdf" and "--given-by" in args and "Jane" in args and "2026-11-03" in args


def test_library_add_doi_and_jobs(tmp_path):
    import pytest
    app, calls = _lib_app(tmp_path)
    app.post("library-add", {"slug": "doe-jane", "dois": ["10.1234/a", " "], "given_by": "Jane", "source": "zotero"})
    assert [c[0] for c in calls if c[0] not in ("build", "job")] == ["add-doi"] and "10.1234/a" in calls[0] and "zotero" in calls[0]
    with pytest.raises(ValueError):
        app.post("library-add", {"slug": "doe-jane", "dois": ["not-a-doi"]})
    app.post("library-process", {"slug": "doe-jane"})
    assert calls[-1][:3] == ("job", "library", "doe-jane") and "prof-library" in calls[-1][3]
    with pytest.raises(ValueError):
        app.post("library-draft", {"slug": "doe-jane", "ids": []})
    app.post("library-draft", {"slug": "doe-jane", "ids": ["W1", "L1abc"]})
    assert calls[-1][1] == "library-draft" and "W1,L1abc" in calls[-1][3]
    with pytest.raises(ValueError):
        app.post("library-draft", {"slug": "doe-jane", "ids": ["W1; rm -rf"]})


def test_doc_upload_saves_file_runs_upload_and_starts_translation(tmp_path):
    import pytest
    app, calls = _lib_app(tmp_path)
    app.doc_script = lambda *a: calls.append(("doc",) + a) or "DONE ps 第 2 版：11 段"
    app.jobs.running = lambda: False
    with pytest.raises(ValueError):
        app.doc_upload({"kind": "cv"}, b"%PDF-1.7")
    with pytest.raises(ValueError):
        app.doc_upload({"kind": "ps", "ext": "pdf"}, b"not a pdf")
    r = app.doc_upload({"kind": "ps", "ext": "docx"}, b"PK\x03\x04 docx")
    assert r["ok"] and r["version"] == 2
    up = [c for c in calls if c[0] == "doc"][0]
    assert up[1] == "upload" and up[2] == "ps" and up[3].endswith(".docx")
    assert ("job", "doc-translate", None) == calls[-1][:3] and "my-docs" in calls[-1][3]


def test_doc_edit_job_validates_inputs(tmp_path):
    import pytest
    app, calls = _lib_app(tmp_path)
    app.post("doc-edit", {"key": "proposal--doe-jane", "version": 3, "block": 4, "instruction": "更精簡"})
    assert calls[-1][1] == "doc-edit" and "第 3 版" in calls[-1][3] and "更精簡" in calls[-1][3]
    for bad in ({"key": "../x", "version": 1, "block": 0}, {"key": "ps", "version": "a", "block": 0}, {"key": "ps", "version": 1, "block": -1}):
        with pytest.raises(ValueError):
            app.post("doc-edit", bad)


def test_me_update_saves_allowed_fields_and_keeps_backup(tmp_path):
    import json, pytest
    app, calls = _lib_app(tmp_path)
    me = tmp_path / "runs" / "_me"
    me.mkdir(parents=True)
    (me / "me.json").write_text(json.dumps({"name": "A", "summary": "old", "interests": [{"en": "X", "zh": "甲"}, {"en": "Y", "zh": "乙"}]}))
    app.post("me-update", {"summary": "new", "summary_zh": "新", "interests": [{"en": "Y", "zh": "乙"}], "name": "hacker"})
    d = json.loads((me / "me.json").read_text())
    assert d["summary"] == "new" and d["summary_zh"] == "新" and d["interests"] == [{"en": "Y", "zh": "乙"}]
    assert d["name"] == "A"  # 只改允許的欄位
    backups = list((me / "history").glob("me-*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["summary"] == "old"
    with pytest.raises(ValueError):
        app.post("me-update", {"interests": [{"en": ""}]})


def test_discover_runs_search_in_background_with_safe_args(tmp_path):
    import pytest
    app, calls = _lib_app(tmp_path)
    ran = []
    app._run_discover = lambda args: ran.append(args)
    r = app.post("discover", {"query": "digital twin", "since": 2023})
    assert r["started"] and ran == [["--query", "digital twin", "--from", "2023"]]
    with pytest.raises(ValueError):
        app.post("discover", {"since": "abc"})


def test_doc_change_runs_directly_and_updates_index(tmp_path):
    import json, zipfile, pytest
    from pipeline.mydocs import new_version, parse_upload
    app, calls = _lib_app(tmp_path)
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    f = tmp_path / "ps.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", f"<w:document {W}><w:body>" + "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in ["N", "T", "A.", "B."]) + "</w:body></w:document>")
        z.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    root = tmp_path / "runs" / "_me" / "docs"
    new_version(root, "ps", parse_upload(f), source=f)
    r = app.post("doc-change", {"key": "ps", "version": 1, "op": "delete", "block": 0})
    assert r["version"] == 2
    idx = json.loads((root / "index.json").read_text())
    assert [b["en"] for b in idx["ps"]["latest"]["blocks"]] == ["B."]
    with pytest.raises(ValueError):
        app.post("doc-change", {"key": "ps", "version": 2, "op": "rm -rf", "block": 0})


def test_professor_edit_remove_restore_keeps_files(tmp_path):
    import json
    app, calls = _lib_app(tmp_path)
    run = tmp_path / "runs" / "doe-jane"
    app.post("prof-update", {"slug": "doe-jane", "note": "11/3 面談", "institution": "Uni X"})
    o = json.loads((run / "owner.json").read_text())
    assert o["note"] == "11/3 面談" and o["institution"] == "Uni X"
    app.post("prof-remove", {"slug": "doe-jane"})
    assert json.loads((run / "owner.json").read_text())["archived"] is True and (run / "state.json").exists()
    app.post("prof-restore", {"slug": "doe-jane"})
    assert json.loads((run / "owner.json").read_text())["archived"] is False


def test_me_update_experience_and_education(tmp_path):
    import json, pytest
    app, calls = _lib_app(tmp_path)
    me = tmp_path / "runs" / "_me"
    me.mkdir(parents=True)
    (me / "me.json").write_text(json.dumps({"name": "A", "experience": [], "education": []}))
    app.post("me-update", {"experience": [{"role": "Engineer", "org": "Co", "dates": "2025–", "bullets": [{"en": "Built X."}], "skills": ["Python"]}],
                           "education": [{"degree": "M.S.", "school": "NTUNHS", "years": "2018–2020"}]})
    d = json.loads((me / "me.json").read_text())
    assert d["experience"][0]["role"] == "Engineer" and d["education"][0]["school"] == "NTUNHS"
    with pytest.raises(ValueError):
        app.post("me-update", {"experience": [{"role": "", "org": ""}]})


def test_discover_enrich_starts_job(tmp_path):
    app, calls = _lib_app(tmp_path)
    (tmp_path / "runs" / "_discover").mkdir(parents=True)
    (tmp_path / "runs" / "_discover" / "latest.json").write_text('{"candidates": []}')
    app.post("discover-enrich", {})
    assert calls[-1][1] == "discover-enrich" and "prof-discover" in calls[-1][3]


def test_engine_choice_is_saved_and_used_by_jobs(tmp_path):
    import pytest
    from app import App
    app = App(tmp_path)
    assert app.jobs.engine() == "claude"
    app.post("engine", {"engine": "codex"})
    assert app.jobs.engine() == "codex" and App(tmp_path).jobs.engine() == "codex"  # 重開程式還記得（只存在這台）
    with pytest.raises(ValueError):
        app.post("engine", {"engine": "gpt"})
    assert app.status()["engine"] == "codex"


def test_notion_connect_and_import(tmp_path, monkeypatch):
    import json
    from pipeline import notion
    app, calls = _lib_app(tmp_path)
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text(json.dumps({"professor": {"name": "Jane Doe", "institution": "Uni X", "orcid": "0000-1"}}))
    seen = {}
    monkeypatch.setattr(notion, "setup", lambda token, link, seed: seen.update(token=token, seed=seed) or {"page_id": "p", "db_id": "db1", "db_url": "https://notion.so/db1"})
    monkeypatch.setattr(notion, "fetch_rows", lambda token, db: [{"name": "Jane Doe", "orcid": None, "status": "已面談", "deadline": "2026-12-01"},
                                                                 {"name": "New Prof", "orcid": None, "institution": "Uni Y"}])
    r = app.post("notion-connect", {"token": "secret_abc", "link": "https://notion.so/x-2f1c3d4e5a6b7c8d9e0f1a2b3c4d5e6f"})
    assert r["rows"] == 2 and seen["token"] == "secret_abc" and seen["seed"][0]["name"] == "Jane Doe"
    assert "NOTION_TOKEN=secret_abc" in (tmp_path / "runs" / "_me" / "secrets.env").read_text()
    assert "secret_abc" not in (tmp_path / "runs" / "_me" / "notion.json").read_text()  # 金鑰只在 secrets.env
    apps = json.loads((tmp_path / "runs" / "_me" / "applications.json").read_text())
    assert [x["slug"] for x in apps["rows"]] == ["doe-jane", None]
    assert app.settings()["notion"]["db_url"] == "https://notion.so/db1"


def test_gcal_login_import_and_create(tmp_path, monkeypatch):
    import json
    from pipeline import gcal
    import pytest
    import app as appmod
    app, _ = _lib_app(tmp_path)
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text(json.dumps({"professor": {"name": "Jane Doe", "institution": "Uni X"}}))
    with pytest.raises(ValueError):
        app.post("gcal-login", {})  # 還沒上傳用戶端
    app.post("gcal-client", {"json": '{"installed": {"client_id": "cid", "client_secret": "cs"}}'})
    opened = []
    monkeypatch.setattr(appmod.webbrowser, "open", opened.append)
    app.port = 8799
    r = app.post("gcal-login", {})
    assert opened == [r["url"]] and "redirect_uri=http%3A%2F%2F127.0.0.1%3A8799%2F" in r["url"]
    with pytest.raises(ValueError):  # state 對不上就不換權杖
        app.gcal_callback({"state": "forged", "code": "c"})
    monkeypatch.setattr(gcal, "exchange", lambda client, code, v, redir: {"access_token": "at", "refresh_token": "rt", "expires_at": "2999-01-01T00:00:00+00:00"})
    made = {}
    monkeypatch.setattr(gcal, "list_events", lambda access: [{"id": "e1", "summary": "Chat with Jane Doe", "start": {"dateTime": "2026-11-03T10:00:00+08:00"}, "end": {}},
                                                             {"id": "e2", "summary": "Gym", "start": {}, "end": {}}])
    monkeypatch.setattr(gcal, "create_event", lambda access, body, notify: made.update(body=body, notify=notify) or {"htmlLink": "https://cal/e3"})
    assert app.gcal_callback({"state": app.gcal_pending["state"], "code": "c"})["events"] == 1
    cal = json.loads((tmp_path / "runs" / "_me" / "calendar.json").read_text())
    assert [e["slug"] for e in cal["events"]] == ["doe-jane"]
    assert app.settings()["gcal"]["connected"] is True
    r = app.post("gcal-create", {"slug": "doe-jane", "summary": "PhD 討論", "start": "2026-11-10T09:00", "minutes": 30, "tz": "Asia/Taipei",
                                 "attendees": ["jane@x.edu"], "meet": True})
    assert r["link"] == "https://cal/e3" and made["notify"] is False
    assert made["body"]["extendedProperties"]["private"]["phdeasy_slug"] == "doe-jane"
    with pytest.raises(ValueError):
        app.post("gcal-create", {"slug": "../etc", "summary": "x", "start": "2026-11-10T09:00"})


def test_new_professor_gets_slug_and_reply_targets_job(tmp_path):
    import json
    import pytest
    from pipeline.jobs import slug_of
    assert slug_of("Julian Hong, M.D., M.S.") == "hong-julian" and slug_of("Julian C. Hong") == "hong-julian"
    assert slug_of("Dr. Yoshimi Fukuoka (UCSF)") == "fukuoka-yoshimi" and slug_of("José Núñez") == "nunez-jose"
    app, calls = _lib_app(tmp_path)
    app.post("new", {"name": "Julian Hong, M.D.", "institution": "UCSF"})
    job = [c for c in calls if c[0] == "job"][-1]
    assert job[1] == "new" and job[2] == "hong-julian" and "runs/hong-julian" in job[3]
    (tmp_path / "runs" / "hong-julian").mkdir(exist_ok=True)
    (tmp_path / "runs" / "hong-julian" / "state.json").write_text("{}")
    with pytest.raises(ValueError, match="已經有"):
        app.post("new", {"name": "Julian Hong", "institution": "UCSF"})
    app.jobs.load = lambda jid: {"id": jid, "title": "建檔：Julian Hong", "session": "s-h", "slug": "hong-julian", "key": "hong-julian"} if jid == "J2" else None
    app.post("reply", {"job": "J2", "text": "範圍選 E"})
    assert [c for c in calls if c[0] == "job"][-1][1:3] == ("reply", "hong-julian")


def test_deep_route_adds_focus_and_starts_job(tmp_path, monkeypatch):
    import json
    import subprocess
    import pytest
    import app as appmod
    app, calls = _lib_app(tmp_path)
    w = tmp_path / "runs" / "doe-jane" / "work"
    w.mkdir(parents=True, exist_ok=True)
    (tmp_path / "runs" / "doe-jane" / "state.json").write_text("{}")
    (w / "works.json").write_text(json.dumps([{"id": "W1", "kind": "full"}, {"id": "W2", "kind": "title"}, {"id": "W3", "kind": "title"}]))
    ran = []
    monkeypatch.setattr(appmod, "find_uv", lambda: "uv")
    monkeypatch.setattr(appmod.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0, "DONE", ""))
    app.post("deep", {"slug": "doe-jane", "ids": ["W1", "W2", "W3", "bad"]})
    assert ran[-1][-1] == "W2,W3"  # 已經完全解析的與亂填的不送
    job = [c for c in calls if c[0] == "job"][-1]
    assert job[1:3] == ("deep", "doe-jane") and "W2, W3" in job[3]
    with pytest.raises(ValueError):
        app.post("deep", {"slug": "doe-jane", "ids": ["W1"]})


def test_applicant_status_saved_and_in_settings(tmp_path):
    """申請身分（國際生／本地生、國籍、要哪一年入學）：設定裡選一次，查博士學程時照這個身分寫學費、條件、期限。"""
    import json
    import pytest
    app, _ = _lib_app(tmp_path)
    (tmp_path / "runs" / "_me").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runs" / "_me" / "me.json").write_text(json.dumps({"name": "A"}))
    app.post("me-update", {"applicant": {"status": "international", "citizenship": "Taiwan", "intake": "2027", "evil": "x"}})
    me = json.loads((tmp_path / "runs" / "_me" / "me.json").read_text())
    assert me["applicant"] == {"status": "international", "citizenship": "Taiwan", "intake": "2027"}
    assert app.settings()["applicant"]["status"] == "international"
    with pytest.raises(ValueError):
        app.post("me-update", {"applicant": {"status": "alien"}})


def test_targets_faculty_build_and_queue(tmp_path):
    """新增學校系所 → 背景查教員名單；勾選建檔：放進系所，同時上限滿了就排隊，跑完一個自動開下一個。"""
    import json
    app, calls = _lib_app(tmp_path)
    started = []

    def start(kind, prompt, title, slug=None, key=None, session=None):
        if len(started) >= 2:
            raise RuntimeError("已經有 3 個工作在跑，等其中一個到停點或跑完再開新的")
        started.append((kind, slug or key, prompt))
        return {"id": title}
    app.jobs.start = start
    r = app.post("target-add", {"school": "University of California, San Francisco", "department": "Computational Precision Health"})
    dept = r["dept"]
    assert started[-1][0] == "faculty" and dept in started[-1][2]
    r = app.post("faculty-build", {"dept": dept, "names": ["Yoshimi Fukuoka", "Julian Hong, M.D."]})
    assert r["started"] == ["Yoshimi Fukuoka"] and r["queued"] == ["Julian Hong, M.D."]
    t = json.loads((tmp_path / "runs" / "_me" / "targets.json").read_text())
    assert t["schools"][0]["departments"][0]["members"] == ["fukuoka-yoshimi", "hong-julian"]
    assert app.status()["queue"] == ["建檔：Julian Hong, M.D."]
    started.clear()
    app.after_job({"id": "x"})
    assert started and started[0][:2] == ("new", "hong-julian") and app.queue == []


def test_halted_build_shows_unfinished_and_queue_survives_restart(tmp_path):
    """建檔停下（熔斷）的不能算「跑完了」；排隊清單存成檔，重開程式還在；繼續跑滿了也排隊。"""
    import json
    import app as appmod
    app, _ = _lib_app(tmp_path)
    r = tmp_path / "runs" / "doe-jane"
    r.mkdir(parents=True, exist_ok=True)
    (r / "state.json").write_text(json.dumps({"stage": "halted"}))
    job = {"id": "J1", "kind": "new", "title": "建檔：Jane Doe", "slug": "doe-jane", "key": "doe-jane", "status": "done", "started": 1}
    (app.jobs.dir / "J1.json").write_text(json.dumps(job))
    app.jobs.active = lambda: []
    got = {j["id"]: j for j in app.job_list()}
    assert got["J1"]["status"] == "halted"
    app.jobs.start = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("已經有 3 個工作在跑，等其中一個到停點或跑完再開新的"))
    assert app.post("continue", {"slug": "doe-jane"})["queued"]
    app2 = appmod.App(tmp_path)
    assert [q["title"] for q in app2.queue] == ["繼續：doe-jane"]


def test_child_python_runs_in_utf8_mode():
    """Windows 中文版預設 cp950：子程序（腳本、Claude Code 跑的腳本）讀寫 JSON 要一律用 UTF-8。"""
    import subprocess
    import sys
    import app  # noqa: F401  匯入就要設好
    r = subprocess.run([sys.executable, "-c", "import sys; print(sys.flags.utf8_mode)"], capture_output=True, text=True)
    assert r.stdout.strip() == "1"


def test_windows_background_commands_get_no_console_window():
    """照 ieltsgod：Windows 上背景跑的指令（測試 AI、換模型、腳本）不要跳黑色終端機；指定了 creationflags 的（登入要開新視窗）不動。"""
    import app

    class FakePopen:
        def __init__(self, *a, **k):
            self.k = k

    class FakeSP:
        Popen = FakePopen
    app.hide_console_windows(FakeSP)
    assert FakeSP.Popen(["claude"]).k["creationflags"] == 0x08000000
    assert FakeSP.Popen(["cmd"], creationflags=0x10).k["creationflags"] == 0x10


def test_library_failure_is_logged_where_drive_syncs(tmp_path, monkeypatch):
    """加入失敗的完整訊息寫進 runs/_logs/（會同步），不只寫在 Windows 那台的 app.log。"""
    import subprocess
    import app
    a = app.App.__new__(app.App)
    a.workspace, a.runs = tmp_path, tmp_path / "runs"
    monkeypatch.setattr(app, "find_uv", lambda: "uv")
    monkeypatch.setattr(subprocess, "run", lambda *x, **k: subprocess.CompletedProcess(x, 1, "", "Traceback ...\nPermissionError: [WinError 32] 檔案正由另一個程序使用"))
    import pytest
    with pytest.raises(ValueError) as e:
        a.lib_script("add-pdf", "runs/x", "--pdf", "y.pdf")
    assert "WinError 32" in str(e.value)
    logs = list((tmp_path / "runs" / "_logs").glob("*.log"))
    assert logs and "WinError 32" in logs[0].read_text(encoding="utf-8") and "add-pdf" in logs[0].read_text(encoding="utf-8")


def test_library_add_processes_automatically_without_button(tmp_path):
    """上傳或貼 DOI 之後就自動開始處理（找全文、AI 重點）；同一位教授的文獻處理已在跑，就等它跑完再自動接著跑一次。"""
    app, calls = _lib_app(tmp_path)
    app.library_upload("doe-jane", b"%PDF-1.7 ...", {})
    jobs = [c for c in calls if c[0] == "job"]
    assert jobs and jobs[-1][1] == "library" and "prof-library" in jobs[-1][3]
    def busy(*a, **k):
        raise RuntimeError("這位教授（或這份文件）已經有一個工作在跑：Meeting 文獻")
    app.jobs.start = busy
    app.post("library-add", {"slug": "doe-jane", "dois": ["10.1234/b"]})
    assert "doe-jane" in app._lib_again  # 正在跑：跑完再接著跑
    app.jobs.start = lambda kind, prompt, title, slug=None, key=None, session=None: calls.append(("job", kind, slug, key)) or {"ok": True}
    app.rebuild_after = False
    app._drain_queue = lambda: None
    import app as appmod
    appmod.rebuild = lambda ws: None
    app.after_job({"key": "lib:doe-jane", "slug": "doe-jane"})
    assert calls[-1] == ("job", "library", "doe-jane", "lib:doe-jane")


def test_library_delete_moves_files_and_forgets_entry(tmp_path):
    import json
    import pytest
    app, calls = _lib_app(tmp_path)
    lib = tmp_path / "runs" / "doe-jane" / "library"
    (lib / "work").mkdir(parents=True)
    (lib / "inbox").mkdir()
    (lib / "work" / "works.json").write_text(json.dumps([{"id": "W1", "title": "a"}, {"id": "L2", "title": "b"}]))
    (lib / "meta.json").write_text(json.dumps({"items": {"W1": {"topic": "x"}, "L2": {"topic": "y"}}}))
    (lib / "inbox" / "W1__upload_1.pdf").write_bytes(b"%PDF")
    (lib / "inbox" / "L2__upload_2.pdf").write_bytes(b"%PDF")
    app.post("lib-delete", {"slug": "doe-jane", "id": "W1"})
    assert [w["id"] for w in json.loads((lib / "work" / "works.json").read_text())] == ["L2"]
    assert "W1" not in json.loads((lib / "meta.json").read_text())["items"]
    assert not (lib / "inbox" / "W1__upload_1.pdf").exists() and (lib / "_已刪除" / "W1__upload_1.pdf").exists()  # 不真的刪：移到 _已刪除
    assert (lib / "inbox" / "L2__upload_2.pdf").exists()
    with pytest.raises(ValueError):
        app.post("lib-delete", {"slug": "doe-jane", "id": "../x"})



def test_library_add_returns_at_once_and_runs_in_background(tmp_path):
    """上傳／貼 DOI 馬上回應（照 ieltsgod：背景處理）；加入中的篇數與失敗訊息在狀態裡，畫面看得到。"""
    app, calls = _lib_app(tmp_path)
    pending = []
    app._bg = pending.append  # 先不跑：模擬還在背景
    r = app.library_upload("doe-jane", b"%PDF-1.7 ...", {})
    assert r["ok"] and not [c for c in calls if c[0] == "add-pdf"]  # 還沒查 OpenAlex 就回應了
    assert app.lib_status()["doe-jane"]["adding"] == 1
    app.lib_script = lambda *a: (_ for _ in ()).throw(ValueError("PermissionError: [WinError 32]"))
    for fn in pending:
        fn()
    st = app.lib_status()["doe-jane"]
    assert st["adding"] == 0 and "WinError 32" in st["errors"][-1]
    app.lib_script = lambda *a: calls.append(a) or "ADD W2 2024 B"
    pending.clear()
    app.post("library-add", {"slug": "doe-jane", "dois": ["10.1234/x"]})
    assert app.lib_status()["doe-jane"]["adding"] == 1
    for fn in pending:
        fn()
    assert any(c[0] == "add-doi" for c in calls) and any(c[0] == "job" for c in calls)  # 加完自動開始處理


def test_stepfun_key_saved_in_secrets_and_tasks_routed(tmp_path, monkeypatch):
    """本人在設定貼 StepFun 的 key：存進金鑰檔（經雲端硬碟同步），畫面只看得到末四碼；各小工作用哪一位可以改。"""
    import json
    import pytest
    from app import App
    import pipeline.ai as AI
    app = App(tmp_path)
    monkeypatch.setattr(AI, "ai_test", lambda pv: AI.set_tested(pv, True) or {"ok": True})
    with pytest.raises(ValueError):
        app.post("ai-key", {"provider": "stepfun", "key": "  "})
    with pytest.raises(ValueError):
        app.post("ai-key", {"provider": "stepfun", "key": "abc def"})
    r = app.post("ai-key", {"provider": "stepfun", "key": "sk-live-ABCDEFGH1234"})
    assert "STEPFUN_API_KEY=sk-live-ABCDEFGH1234" in (tmp_path / "runs" / "_me" / "secrets.env").read_text()
    assert r["stepfunKey"] == "…1234" and "ABCDEFGH" not in json.dumps(r)  # 畫面拿不到整串
    assert r["tasks"]["translate"]["using"] == "stepfun"
    app.post("ai-settings", {"tasks": {"translate": "claude", "ask": "bogus"}})
    assert AI.w_settings()["tasks"] == {"translate": "claude"}
    app.post("ai-key", {"provider": "stepfun", "remove": True})
    assert AI.stepfun_key() is None
    with pytest.raises(ValueError):
        app.post("ai-install", {"provider": "stepfun"})


def test_main_process_reads_utf8_and_old_cp950_files(tmp_path):
    """Windows 中文版主程式預設 cp950：背景腳本寫的 UTF-8 中文檔一讀就當掉（打不開）。
    裝上之後沒指定編碼的讀寫一律 UTF-8；舊版主程式用 cp950 寫的檔也讀得回來，不會當掉。"""
    import pathlib
    import app
    utf = tmp_path / "state.json"
    utf.write_bytes('{"name": "邱尚志 教授"}'.encode("utf-8"))
    old = tmp_path / "queue.json"
    old.write_bytes('[{"title": "Meeting 文獻：林"}]'.encode("cp950"))
    restore = app.utf8_io(fallback="cp950")
    try:
        assert "邱尚志" in utf.read_text() and "林" in old.read_text()
        (tmp_path / "new.json").write_text("新的")
        assert (tmp_path / "new.json").read_bytes() == "新的".encode("utf-8")
        with open(tmp_path / "new.json") as f:
            assert f.read() == "新的"
    finally:
        restore()
    assert pathlib.Path.read_text.__name__ == "read_text"
