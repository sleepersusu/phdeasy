"""E2E 總檢查：重跑所有機械核對，寫 verify/e2e.json；任何一項不過 exit 1。

  uv run python scripts/e2e.py runs/<slug>
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline.e2e import run_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    run = Path(ap.parse_args().run)
    tests = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:warnings"], capture_output=True, text=True)
    last = (tests.stdout.strip().splitlines() or [""])[-1]
    results = [{"name": "pytest", "pass": tests.returncode == 0, "detail": last}] + run_all(run)
    (run / "verify").mkdir(exist_ok=True)
    (run / "verify" / "e2e.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    for r in results:
        print(f"{'PASS' if r['pass'] else 'FAIL'} {r['name']}：{r['detail']}")
    n_ok = sum(r["pass"] for r in results)
    print(f"{'DONE' if n_ok == len(results) else 'FAIL'} E2E {n_ok}/{len(results)}")
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
