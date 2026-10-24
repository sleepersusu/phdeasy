"""批次狀態命令列。

  uv run python scripts/state_cli.py init runs/<slug> --name "Yoshimi Fukuoka" --institution "UCSF"
  uv run python scripts/state_cli.py stage runs/<slug> stop1 --set works_total=24
  uv run python scripts/state_cli.py progress runs/<slug> setup "24 篇，全文 15"
  uv run python scripts/state_cli.py show runs/<slug>
"""
import argparse
import json

from pipeline.state import init_run, set_stage, append_progress, load_state


def _val(v):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init")
    a.add_argument("run")
    a.add_argument("--name", required=True)
    a.add_argument("--institution", default=None)
    a.add_argument("--orcid", default=None)
    b = sub.add_parser("stage")
    b.add_argument("run")
    b.add_argument("stage")
    b.add_argument("--set", action="append", default=[], help="key=value，value 可為 JSON")
    c = sub.add_parser("progress")
    c.add_argument("run")
    c.add_argument("stage")
    c.add_argument("text")
    d = sub.add_parser("show")
    d.add_argument("run")
    args = ap.parse_args()

    if args.cmd == "init":
        run = init_run(args.run, {"name": args.name, "institution": args.institution, "orcid": args.orcid})
        print(f"OK {run}")
    elif args.cmd == "stage":
        fields = dict(kv.split("=", 1) for kv in args.set)
        s = set_stage(args.run, args.stage, **{k: _val(v) for k, v in fields.items()})
        print(f"OK stage={s['stage']}")
    elif args.cmd == "progress":
        append_progress(args.run, args.stage, args.text)
        print("OK")
    else:
        print(json.dumps(load_state(args.run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
