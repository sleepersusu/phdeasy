"""例外：寫進 state.json 的 exceptions 與 exceptions.md（只追加）；熔斷檢查。"""
from datetime import datetime
from pathlib import Path

from .state import load_state, set_stage, _write

# 只是註記、不影響產出品質的例外，不算進熔斷比例
INFO_KINDS = {"year_mismatch", "author_not_linked", "owner_decision", "possible_author_split", "name_merge"}


def add_exception(run, work_id, stage, kind, detail):
    run = Path(run)
    s = load_state(run)
    if any(e["id"] == work_id and e["kind"] == kind and e["stage"] == stage and not e.get("resolved") for e in s["exceptions"]):
        return False
    s["exceptions"].append({"id": work_id, "stage": stage, "kind": kind, "detail": detail})
    _write(run, s)
    md = run / "exceptions.md"
    if not md.exists():
        md.write_text("# 例外紀錄\n\n| 時間 | 文章 id | 階段 | 類型 | 說明 |\n|---|---|---|---|---|\n")
    with open(md, "a") as f:
        f.write(f"| {datetime.now().astimezone().isoformat(timespec='seconds')} | {work_id} | {stage} | {kind} | {detail} |\n")
    return True


def resolve_exception(run, work_id, stage, kind, note):
    """問題已解決：state 裡標 resolved（不刪），exceptions.md 追加一行。"""
    run = Path(run)
    s = load_state(run)
    hit = next((e for e in s["exceptions"] if e["id"] == work_id and e["stage"] == stage and e["kind"] == kind and not e.get("resolved")), None)
    if hit is None:
        return False
    hit["resolved"] = note
    _write(run, s)
    with open(run / "exceptions.md", "a") as f:
        f.write(f"| {datetime.now().astimezone().isoformat(timespec='seconds')} | {work_id} | {stage} | {kind}（已解決） | {note} |\n")
    return True


def open_exceptions(run):
    return [e for e in load_state(run)["exceptions"] if not e.get("resolved")]


def exception_ratio(run, total):
    ids = {e["id"] for e in open_exceptions(run) if e["kind"] not in INFO_KINDS}
    return len(ids) / total if total else 0


def check_circuit(run, total, limit=0.3):
    r = exception_ratio(run, total)
    if r > limit:
        reason = f"例外篇數比例 {r:.0%} > {limit:.0%}"
        set_stage(run, "halted", circuit={"tripped": True, "reason": reason})
        return True, reason
    return False, None
