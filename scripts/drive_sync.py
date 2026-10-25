"""把 runs/（每位教授的資料夾＋首頁）和 Google 雲端硬碟雙向同步，別台電腦打開就有（做法同雅思練習室）。

  uv run python scripts/drive_sync.py runs --setup              # 第一次：列出這台登入的 Google 雲端硬碟帳號
  uv run python scripts/drive_sync.py runs --account <email>    # 選定帳號（記在 runs/_me/drive.json，只在這台）
  uv run python scripts/drive_sync.py runs                      # 同步（開工、每段收尾、停點前）
  uv run python scripts/drive_sync.py runs --release            # 收工：最後同步一次並拿掉「使用中」，別台才能接著用
  uv run python scripts/drive_sync.py runs --force              # 別台顯示使用中但其實已關掉時，強制同步

雲端位置：<我的雲端硬碟>/phdeasy教授檔案/。衝突與刪除的檔案收在該資料夾的 _同步衝突／_同步刪除。
"""
import argparse
import json
import sys
from pathlib import Path

from pipeline.drive_sync import FOLDER, find_drive, find_drives, release, sync


def _cfg(runs):
    p = runs / "_me" / "drive.json"
    return p, (json.loads(p.read_text()) if p.exists() else {})


def target(runs, account=None, given=None):
    p, conf = _cfg(runs)
    if account or given:
        if account:
            conf["account"] = account
        if given:
            conf["dir"] = str(Path(given).expanduser())
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(conf, ensure_ascii=False, indent=1))
    if conf.get("dir"):
        return Path(conf["dir"])
    d = find_drive(prefer=conf.get("account"))
    return d / FOLDER if d else None


def run(runs, account=None, given=None, force=False, do_release=False):
    dst = target(runs, account, given)
    if not dst or not dst.parent.exists():
        print("SKIP 找不到 Google 雲端硬碟：請安裝 Google Drive 電腦版並登入，再跑 --setup")
        return 1
    n = sync(runs, dst, force=force)
    if "blocked" in n:
        print(f"BLOCKED 另一台電腦（{n['blocked']}）10 分鐘內還在用，先不同步。那台收工（--release）後再跑；確定那台已關掉就加 --force")
        return 2
    msg = "、".join(f"{k} {v}" for k, v in sorted(n.items())) or "沒有變動"
    if do_release:
        release(dst)
        msg += "；已釋放使用中"
    print(f"DONE 雲端同步 {dst}：{msg}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default="runs")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--account", default=None)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--release", action="store_true")
    a = ap.parse_args()
    runs = Path(a.runs)
    if a.setup:
        drives = find_drives()
        _, conf = _cfg(runs)
        if not drives:
            print("沒有找到 Google 雲端硬碟。請安裝 Google Drive 電腦版（https://www.google.com/drive/download/）並登入。")
            return 1
        for label, p in drives:
            mark = "（目前使用）" if label == conf.get("account") else ""
            print(f"- {label}：{p}{mark}")
        print("選一個帳號：uv run python scripts/drive_sync.py runs --account <上面的帳號>")
        return 0
    return run(runs, a.account, a.dir, a.force, a.release)


if __name__ == "__main__":
    sys.exit(main())
