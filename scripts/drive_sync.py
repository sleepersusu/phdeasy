"""把 runs/（每位教授的資料夾＋首頁）和 Google 雲端硬碟雙向同步，別台電腦打開就有。

  uv run python scripts/drive_sync.py runs                 # 同步（找不到雲端硬碟就跳過）
  uv run python scripts/drive_sync.py runs --dir <資料夾>    # 第一次指定雲端資料夾，之後記在 runs/_me/drive.json

雲端位置：<我的雲端硬碟>/phdeasy教授檔案/。衝突與刪除的檔案收在該資料夾的 _同步衝突／_同步刪除。
"""
import argparse
import json
import sys
from pathlib import Path

from pipeline.drive_sync import FOLDER, find_drive, sync


def target(runs, given=None):
    cfg = runs / "_me" / "drive.json"
    conf = json.loads(cfg.read_text()) if cfg.exists() else {}
    if given:
        conf["dir"] = str(Path(given).expanduser())
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(conf, ensure_ascii=False, indent=1))
    if conf.get("dir"):
        return Path(conf["dir"])
    d = find_drive(prefer=conf.get("account"))
    return d / FOLDER if d else None


def run(runs, given=None):
    dst = target(runs, given)
    if not dst or not dst.parent.exists():
        print("SKIP 找不到 Google 雲端硬碟（請安裝 Google Drive 電腦版並登入，或用 --dir 指定）")
        return
    n = sync(runs, dst)
    print(f"DONE 雲端同步 {dst}：" + ("、".join(f"{k} {v}" for k, v in sorted(n.items())) or "沒有變動"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default="runs")
    ap.add_argument("--dir", default=None)
    a = ap.parse_args()
    run(Path(a.runs), a.dir)


if __name__ == "__main__":
    sys.exit(main())
