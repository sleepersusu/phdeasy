"""目標學校 → 系所：查到的教員名單核對後併入 runs/_me/targets.json。

  uv run python scripts/targets.py faculty-apply <系所 id>   # 核對 runs/_me/targets/<系所 id>/faculty.json，通過才寫入
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.targets import check_faculty, find_dept

RUNS = Path(__file__).resolve().parent.parent / "runs"


def main(argv=None, runs=RUNS):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["faculty-apply"])
    ap.add_argument("dept")
    a = ap.parse_args(argv)
    tp = Path(runs) / "_me" / "targets.json"
    t = json.loads(tp.read_text())
    _, d = find_dept(t, a.dept)
    f = json.loads((Path(runs) / "_me" / "targets" / a.dept / "faculty.json").read_text())
    fails = check_faculty(f)
    for x in fails:
        print(f"FAIL {x['where']} {x['why']}")
    if fails:
        return 1
    d["faculty"] = {"fetched": datetime.now().astimezone().isoformat(timespec="seconds"), "src": f["src"],
                    "people": [{k: p.get(k) for k in ("name", "title", "profile_url", "research", "orcid")} for p in f["people"]]}
    tp.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    print(f"DONE {d['name']}：教員 {len(f['people'])} 位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
