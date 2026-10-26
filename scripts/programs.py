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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--no-site", action="store_true")
    a = ap.parse_args(argv)
    run = Path(a.run)
    progs = json.loads((run / "work" / "programs.json").read_text()).get("programs") or []
    fails = check_programs(progs)
    for f in fails:
        print(f"FAIL {f['where']} {f['why']}")
    if fails:
        return 1
    (run / "out").mkdir(exist_ok=True)
    (run / "out" / "programs.json").write_text(json.dumps({"checked": datetime.now().astimezone().date().isoformat(), "programs": progs},
                                                          ensure_ascii=False, indent=1))
    if not a.no_site:
        subprocess.run([sys.executable, str(Path(__file__).parent / "build_site.py"), str(run)], check=False)
    print(f"DONE 博士學程：{len(progs)} 個（全額 {sum(1 for p in progs if (p.get('funding') or {}).get('value') == 'full')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
