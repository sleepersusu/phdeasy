"""批次狀態：state.json 只寫現況（覆寫），progress.md 只追加。"""
import json
from datetime import datetime
from pathlib import Path

STAGES = ["setup", "stop1", "ingest", "network", "grants", "cards", "profile", "verify", "stop2"]
HALTED = "halted"  # 熔斷，不在正常順序中
SUBDIRS = ["inbox", "pdfs", "work", "out", "verify"]


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def init_run(run, professor):
    run = Path(run)
    for d in SUBDIRS:
        (run / d).mkdir(parents=True, exist_ok=True)
    if not (run / "state.json").exists():
        _write(run, {"slug": run.name, "professor": professor, "stage": "setup", "updated": _now(), "exceptions": [], "circuit": {"tripped": False, "reason": None}})
    if not (run / "progress.md").exists():
        (run / "progress.md").write_text(f"# 進度紀錄：{run.name}\n\n")
    return run


def load_state(run):
    return json.loads((Path(run) / "state.json").read_text())


def _write(run, state):
    p = Path(run) / "state.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(p)


def set_stage(run, stage, **fields):
    if stage not in STAGES and stage != HALTED:
        raise ValueError(f"未知的 stage：{stage}")
    s = load_state(run)
    s.update(fields)
    s["stage"] = stage
    s["updated"] = _now()
    _write(run, s)
    return s


def append_progress(run, stage, text):
    with open(Path(run) / "progress.md", "a") as f:
        f.write(f"- {_now()} {stage}：{text}\n")
