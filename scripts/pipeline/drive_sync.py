"""runs/ 與 Google 雲端硬碟雙向同步（做法同雅思練習室）。

三方比對：這台（local）、雲端（remote）、上次同步時（base，記在 runs/.drive_sync.json）。
- 只有一邊改 → 複製到另一邊
- 兩邊都改 → 用比較新的；舊的那份留在雲端 `_同步衝突/`
- 一邊刪掉、另一邊沒改 → 另一邊也刪（刪的檔先收到雲端 `_同步刪除/`，不直接消失）
- 第一次同步（沒有 base）→ 只合併、不刪
"""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

DRIVE_NAMES = ("我的雲端硬碟", "My Drive", "我的云端硬盘")
FOLDER = "phdeasy教授檔案"
STATE = ".drive_sync.json"
SKIP_DIRS = {"_同步衝突", "_同步刪除", "__pycache__"}
SKIP_FILES = {STATE, ".DS_Store"}


def find_drive(home=None, prefer=None):
    """這台電腦上 Google 雲端硬碟電腦版的「我的雲端硬碟」；有多個帳號時優先 prefer（email）。"""
    home = Path(home or os.path.expanduser("~"))
    cs = home / "Library" / "CloudStorage"
    cands = []
    if cs.exists():
        for d in sorted(cs.iterdir()):
            if d.name.startswith("GoogleDrive"):
                for n in DRIVE_NAMES:
                    if (d / n).is_dir():
                        cands.append((d.name.split("-", 1)[-1], d / n))
    for n in DRIVE_NAMES:  # Windows：G:\我的雲端硬碟
        for root in (Path("G:/"), home / "Google Drive"):
            if (root / n).is_dir():
                cands.append(("", root / n))
    if prefer:
        cands.sort(key=lambda c: c[0] != prefer)
    return cands[0][1] if cands else None


def scan(root):
    """{相對路徑: (大小, 修改時間)}；略過同步自己的資料夾與暫存檔。"""
    root = Path(root)
    out = {}
    if not root.exists():
        return out
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fns:
            if f in SKIP_FILES or f.startswith("~$") or f.endswith(".tmp"):
                continue
            p = Path(dp) / f
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime)
    return out


def _sig(s):
    return [s[0], round(s[1], 3)] if s else None


def plan(local, remote, base):
    """local/remote: scan() 結果；base: {相對路徑: {"l": sig, "r": sig}}。回傳 [(動作, 路徑)]。
    動作：push（這台→雲端）、pull（雲端→這台）、del_local、del_remote、conflict_push、conflict_pull。"""
    acts = []
    first = not base
    for rel in sorted(set(local) | set(remote) | set(base)):
        l, r, b = _sig(local.get(rel)), _sig(remote.get(rel)), base.get(rel) or {}
        lchg, rchg = l != b.get("l"), r != b.get("r")
        if l and r:
            if not lchg and not rchg:
                continue
            if l[0] == r[0] and abs(l[1] - r[1]) < 2:
                acts.append(("same", rel))  # 兩邊一樣（例：第一次同步），只記 base
            elif lchg and not rchg:
                acts.append(("push", rel))
            elif rchg and not lchg:
                acts.append(("pull", rel))
            else:
                acts.append(("conflict_push" if l[1] >= r[1] else "conflict_pull", rel))
        elif l and not r:
            acts.append(("push", rel) if first or lchg or not b.get("r") else ("del_local", rel))
        elif r and not l:
            acts.append(("pull", rel) if first or rchg or not b.get("l") else ("del_remote", rel))
    return acts


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _stash(root, rel, kind):
    src = root / rel
    if src.exists():
        dst = root / kind / time.strftime("%Y%m%d-%H%M%S") / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), dst)


def sync(local_root, remote_root):
    local_root, remote_root = Path(local_root), Path(remote_root)
    remote_root.mkdir(parents=True, exist_ok=True)
    sp = local_root / STATE
    base = json.loads(sp.read_text()) if sp.exists() else {}
    acts = plan(scan(local_root), scan(remote_root), base)
    n = {}
    for act, rel in acts:
        lp, rp = local_root / rel, remote_root / rel
        if act in ("push", "conflict_push"):
            if act == "conflict_push":
                _stash(remote_root, rel, "_同步衝突")
            _copy(lp, rp)
        elif act in ("pull", "conflict_pull"):
            if act == "conflict_pull":
                _copy(lp, remote_root / "_同步衝突" / time.strftime("%Y%m%d-%H%M%S") / rel)
            _copy(rp, lp)
        elif act == "del_local":
            lp.unlink(missing_ok=True)
        elif act == "del_remote":
            _stash(remote_root, rel, "_同步刪除")
        n[act] = n.get(act, 0) + 1
    l2, r2 = scan(local_root), scan(remote_root)
    new_base = {rel: {"l": _sig(l2.get(rel)), "r": _sig(r2.get(rel))} for rel in set(l2) & set(r2)}
    sp.write_text(json.dumps(new_base, ensure_ascii=False))
    return n
