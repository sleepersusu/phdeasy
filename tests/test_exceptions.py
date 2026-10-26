from pipeline.state import init_run, load_state
from pipeline.exceptions import add_exception, exception_ratio, check_circuit


def test_add_exception_writes_state_and_md_without_duplicates(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "ingest", "no_text", "掃描檔")
    add_exception(run, "W1", "ingest", "no_text", "掃描檔")
    s = load_state(run)
    assert len(s["exceptions"]) == 1 and s["exceptions"][0]["kind"] == "no_text"
    assert (run / "exceptions.md").read_text().count("W1") == 1


def test_exception_ratio_counts_works_not_entries(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "ingest", "a", "")
    add_exception(run, "W1", "cards", "b", "")
    add_exception(run, "W2", "ingest", "a", "")
    assert exception_ratio(run, total=10) == 0.2


def test_informational_kinds_do_not_count_toward_circuit(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "setup", "year_mismatch", "")
    assert exception_ratio(run, total=1) == 0


def test_circuit_trips_over_threshold(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    for i in range(4):
        add_exception(run, f"W{i}", "ingest", "no_text", "")
    tripped, reason = check_circuit(run, total=10, limit=0.3)
    assert tripped and "40%" in reason
    assert load_state(run)["stage"] == "halted"


def test_circuit_ok_under_threshold(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "ingest", "no_text", "")
    assert check_circuit(run, total=10, limit=0.3) == (False, None)


def test_resolved_exception_not_counted_and_logged(tmp_path):
    from pipeline.exceptions import resolve_exception
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "ingest", "no_source", "沒摘要")
    assert resolve_exception(run, "W1", "ingest", "no_source", "已從 Europe PMC 補摘要")
    assert exception_ratio(run, total=1) == 0
    assert load_state(run)["exceptions"][0]["resolved"] == "已從 Europe PMC 補摘要"
    assert "已解決" in (run / "exceptions.md").read_text()


def test_resolve_missing_returns_false(tmp_path):
    from pipeline.exceptions import resolve_exception
    run = init_run(tmp_path / "x", professor={})
    assert resolve_exception(run, "W9", "ingest", "no_source", "") is False


def test_missing_fulltext_does_not_trip_circuit(tmp_path):
    """本人 2026-10-26：只精讀 5 篇、不停下；必讀沒有免費全文改用摘要（abstract_only）不算熔斷，教授頁有「再找全文／上傳 PDF」按鈕。"""
    run = init_run(tmp_path / "x", professor={})
    add_exception(run, "W1", "ingest", "abstract_only", "")
    add_exception(run, "W2", "ingest", "abstract_only", "")
    assert check_circuit(run, total=5, limit=0.3) == (False, None)
    add_exception(run, "W3", "ingest", "no_text", "")
    add_exception(run, "W4", "ingest", "title_mismatch", "")
    assert check_circuit(run, total=5, limit=0.3)[0]  # 讀不出字、拿錯檔案這種真的錯仍會停
