"""自動檢查更新（做法同雅思練習室）：打開時與每 6 小時看一次 GitHub Releases 的最新版；
有新版就在畫面上提示，按「更新」下載安裝檔、安靜安裝，裝完自動重開（教授資料不動）。只有 Windows 安裝版會自己更新。"""
import json
import re
import urllib.request
from pathlib import Path

REPO = "sleepersusu/phdeasy"
ASSET = "PhdeasyProfessorFiles-Setup.exe"


def parse_version(v):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def latest_release(fetch=None):
    """回傳 {"tag", "url"（安裝檔下載網址）, "size", "notes", "page"}；查不到回 None。"""
    def _fetch(u):
        req = urllib.request.Request(u, headers={"Accept": "application/vnd.github+json", "User-Agent": "phdeasy-updater"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    try:
        d = (fetch or _fetch)(f"https://api.github.com/repos/{REPO}/releases/latest")
    except Exception:
        return None
    asset = next((a for a in d.get("assets") or [] if a.get("name") == ASSET), None)
    if not asset:
        return None
    return {"tag": d.get("tag_name"), "url": asset.get("browser_download_url"), "size": asset.get("size"),
            "notes": (d.get("body") or "")[:2000], "page": d.get("html_url")}


def check(current, fetch=None):
    rel = latest_release(fetch)
    return {"current": current, "latest": (rel or {}).get("tag"), "available": bool(rel and newer(rel["tag"], current)), "release": rel}


def download(rel, dest_dir, opener=None):
    """下載安裝檔並檢查大小與檔頭（Windows 執行檔開頭是 MZ）。回傳檔案路徑。"""
    url = rel["url"]
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        raise ValueError("下載網址不是這個專案的 GitHub Releases")
    dest = Path(dest_dir) / f"Setup-{rel['tag']}.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "phdeasy-updater"})
    with (opener or urllib.request.urlopen)(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    data_ok = tmp.stat().st_size == rel.get("size") and tmp.read_bytes()[:2] == b"MZ"
    if not data_ok:
        tmp.unlink(missing_ok=True)
        raise ValueError("下載的安裝檔不完整，請稍後再試")
    tmp.replace(dest)
    return dest
