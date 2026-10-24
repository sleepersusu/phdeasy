import json
import pytest
from pipeline.state import init_run, load_state, set_stage, append_progress, STAGES


def test_init_creates_files(tmp_path):
    run = init_run(tmp_path / "runs" / "x", professor={"name": "Y F"})
    s = load_state(run)
    assert s["stage"] == "setup"
    assert s["professor"]["name"] == "Y F"
    assert (run / "progress.md").exists()
    assert (run / "inbox").is_dir() and (run / "pdfs").is_dir()


def test_init_does_not_overwrite_existing(tmp_path):
    run = init_run(tmp_path / "x", professor={"name": "A"})
    set_stage(run, "stop1")
    init_run(tmp_path / "x", professor={"name": "B"})
    assert load_state(run)["stage"] == "stop1"
    assert load_state(run)["professor"]["name"] == "A"


def test_set_stage_rejects_unknown(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    with pytest.raises(ValueError):
        set_stage(run, "bogus")


def test_set_stage_merges_fields(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    set_stage(run, "stop1", works_total=24)
    s = json.loads((run / "state.json").read_text())
    assert s["stage"] == "stop1" and s["works_total"] == 24


def test_progress_is_append_only(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    append_progress(run, "setup", "a")
    append_progress(run, "setup", "b")
    lines = [l for l in (run / "progress.md").read_text().splitlines() if l.startswith("- ")]
    assert lines[-2].endswith("setup：a") and lines[-1].endswith("setup：b")


def test_stage_order():
    assert STAGES[0] == "setup" and STAGES[-1] == "stop2"


def test_halt_is_allowed_but_not_a_stage(tmp_path):
    run = init_run(tmp_path / "x", professor={})
    s = set_stage(run, "halted", circuit={"tripped": True, "reason": "例外 40% > 30%"})
    assert s["stage"] == "halted" and "halted" not in STAGES
