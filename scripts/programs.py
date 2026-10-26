"""教授掛名的博士學程（教授首頁「博士學程」）：核對查詢者寫的 runs/<slug>/work/programs.json，寫 out/programs.json，重建教授頁。

  uv run python scripts/programs.py runs/<slug> [--no-site]

每個學程都要有看得到教授名字的官方頁（member_src）；資助值只能是 full／partial／none／unknown，不是 unknown 就要有出處。
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pipeline.discover import check_programs
from pipeline.education import check_education


def _dept_of(run):
    """這位教授在哪個目標系所（runs/_me/targets.json），回傳 (targets, 系所) 或 (None, None)。"""
    tp = run.parent / "_me" / "targets.json"
    if not tp.exists():
        return None, None
    t = json.loads(tp.read_text())
    for sc in t.get("schools") or []:
        for d in sc.get("departments") or []:
            if run.name in (d.get("members") or []):
                return t, d
    return t, None


def _on_faculty(run, d):
    st = json.loads((run / "state.json").read_text())
    name = " ".join(((st.get("professor") or {}).get("name") or "").lower().split())
    return any(" ".join((p.get("name") or "").lower().split()) == name for p in ((d.get("faculty") or {}).get("people") or []))


def _write(run, progs, no_site, extra=None):
    (run / "out").mkdir(exist_ok=True)
    (run / "out" / "programs.json").write_text(json.dumps({"checked": datetime.now().astimezone().date().isoformat(), "programs": progs, **(extra or {})},
                                                          ensure_ascii=False, indent=1))
    if not no_site:
        subprocess.run([sys.executable, str(Path(__file__).parent / "build_site.py"), str(run)], check=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--no-site", action="store_true")
    ap.add_argument("--from-dept", action="store_true", help="同系所已查過學程：直接套用（不派 AI）；沒查過回 2")
    a = ap.parse_args(argv)
    run = Path(a.run)
    t, d = _dept_of(run)
    if a.from_dept:
        info = (d or {}).get("program_info")
        if not d or not info or not _on_faculty(run, d):
            print("NEED 這個系所還沒查過學程（或教授不在系所教員名單上）：派查詢者")
            return 2
        prog = {**info["program"], "basis": "member", "member_src": d["faculty"]["src"], "via": d["name"]}  # 系所教員名單證明他在這個學程
        _write(run, [prog], a.no_site, {"from": "dept"})
        print(f"DONE 博士學程：沿用系所「{d['name']}」查過的（{info.get('checked')}），沒有派 AI")
        return 0
    raw = json.loads((run / "work" / "programs.json").read_text())
    progs = raw.get("programs") or []
    edu = raw.get("education") or []
    fails = check_programs(progs) + check_education(edu)
    for f in fails:
        print(f"FAIL {f['where']} {f['why']}")
    if fails:
        return 1
    own = next((p for p in progs if p.get("dept_program")), None)
    if d is not None and own:  # 存成系所的學程資訊，同系所下一位教授直接套用
        d["program_info"] = {"checked": datetime.now().astimezone().date().isoformat(),
                             "program": {k: v for k, v in own.items() if k not in ("member_src", "dept_program", "via")}}
        (run.parent / "_me" / "targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1))
    if edu:  # 查詢者從官方個人頁／CV／LinkedIn 讀到的學歷
        (run / "out").mkdir(exist_ok=True)
        (run / "out" / "education.json").write_text(json.dumps({"fetched": datetime.now().astimezone().date().isoformat(), "source": "lookup", "items": edu},
                                                               ensure_ascii=False, indent=1))
    _write(run, [{k: v for k, v in p.items() if k != "dept_program"} for p in progs], a.no_site)
    print(f"DONE 博士學程：{len(progs)} 個（全額 {sum(1 for p in progs if (p.get('funding') or {}).get('value') == 'full')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
