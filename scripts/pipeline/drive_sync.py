"""runs/ 與 Google 雲端硬碟雙向同步（做法同雅思練習室）。

三方比對：這台（local）、雲端（remote）、上次同步時（base，記在 runs/.drive_sync.json，只在這台）。
- 只有一邊改 → 複製到另一邊
- 兩邊都改 → 用比較新的；被取代的那份留在雲端 `_同步衝突/`
- 一邊刪掉、另一邊沒改 → 另一邊也刪（刪的檔先收到 `_同步刪除/`，不直接消失）
- 第一次同步、或換了雲端資料夾（base 不是這個雲端）→ 只合併、不刪
- 雲端的 JSON 突然變得小很多（例：被空檔蓋掉）→ 不拿它蓋這台，雲端那份收到 `_同步衝突/`
- 使用中記號（雲端 `_使用中.json`）：別台電腦 5 分鐘內同步過＝還在用，這台先不同步（先到先用），除非 force
"""
import contextlib
import json
import os
import shutil
import socket
import time
import uuid
from pathlib import Path

DRIVE_NAMES = ("我的雲端硬碟", "My Drive", "我的云端硬盘")
FOLDER = "phdeasy教授檔案"
STATE = ".drive_sync.json"
LOCK = "_使用中.json"
LOCK_FRESH = 5 * 60  # 開著的程式每 3 分鐘同步一次；超過 5 分鐘沒動靜就當作已關掉
SKIP_DIRS = {"_同步衝突", "_同步刪除", "__pycache__", "_app"}  # _app：這台的背景工作紀錄，只在這台
LOCAL_LOCK = ".drive_sync.lock"  # 這台電腦上同時只能有一個同步（定時同步、背景工作的同步會排隊）
SKIP_FILES = {STATE, LOCK, LOCAL_LOCK, ".DS_Store", "drive.json"}  # drive.json：每台電腦自己的雲端設定，不同步
DEVICE = (socket.gethostname() or "這台電腦").split(".")[0]


def device_id(home=None):
    """每台電腦自己的編號（存在使用者資料夾，不跟著同步），用來分辨是不是同一台。"""
    p = Path(home or os.path.expanduser("~")) / ".phdeasy" / "device-id"
    try:
        v = p.read_text().strip()
        if v:
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    except OSError:
        pass
    return v


def find_drives(home=None):
    """這台電腦上所有 Google 雲端硬碟帳號的「我的雲端硬碟」：[(帳號, 路徑)]。"""
    home = Path(home or os.path.expanduser("~"))
    cands = []
    cs = home / "Library" / "CloudStorage"
    if cs.exists():
        for d in sorted(cs.iterdir()):
            if d.name.startswith("GoogleDrive"):
                cands += [(d.name.split("-", 1)[-1], d / n) for n in DRIVE_NAMES]
    if os.name == "nt":  # Windows：G:\我的雲端硬碟 等
        cands += [(f"{L}: 磁碟機", Path(f"{L}:/") / n) for L in "GHIJKLMNOPQRSTUVWXYZ" for n in DRIVE_NAMES]
    cands += [("Google Drive", home / "Google Drive" / n) for n in DRIVE_NAMES]
    out, seen = [], set()
    for label, p in cands:
        if p.is_dir() and os.path.realpath(p) not in seen:
            seen.add(os.path.realpath(p))
            out.append((label, p))
    return out


def find_drive(home=None, prefer=None):
    drives = find_drives(home)
    if prefer:
        drives.sort(key=lambda c: c[0] != prefer)
    return drives[0][1] if drives else None


class ScanError(RuntimeError):
    """有資料夾讀不到（例：macOS 不讓程式列出雲端硬碟的資料夾）。這時不能同步，否則讀不到的會被當成「刪掉了」。"""


def _raise(e):
    raise ScanError(f"讀不到資料夾：{getattr(e, 'filename', '') or e}（{e.strerror if hasattr(e, 'strerror') else e}）")


PROTECT = ("_me/",)  # 本人資料：同步只會補，不會刪（2026-10-26 事故後加）
MAX_DELETE = 10  # 一次要刪超過這麼多（且超過 5%），就停下來不刪，等本人確認


def scan(root):
    """{相對路徑: (大小, 修改時間)}；略過同步自己的資料夾與暫存檔。任何資料夾讀不到就丟 ScanError（不當成空的）。"""
    root = Path(root)
    out = {}
    if not root.exists():
        return out
    for dp, dns, fns in os.walk(root, onerror=_raise):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for f in fns:
            if f in SKIP_FILES or f.startswith("~$") or f.endswith((".tmp", ".works.lock")):
                continue
            p = Path(dp) / f
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime)
    return out


def _sig(s):
    return [s[0], int(s[1])] if s else None  # 秒為單位：雲端硬碟不一定保留小數秒


def plan(local, remote, base):
    """local/remote: scan() 結果；base: {相對路徑: {"l": sig, "r": sig}}。回傳 [(動作, 路徑)]。
    動作：push（這台→雲端）、pull（雲端→這台）、same（只記 base）、del_local、del_remote、
    conflict_push、conflict_pull（兩邊都改，取較新的）、shrunk（雲端 JSON 變小很多，保留這台）。"""
    acts = []
    first = not base
    for rel in sorted(set(local) | set(remote) | set(base)):
        l, r, b = _sig(local.get(rel)), _sig(remote.get(rel)), base.get(rel) or {}
        lchg, rchg = l != b.get("l"), r != b.get("r")
        if l and r:
            if not lchg and not rchg:
                continue
            if l[0] == r[0] and abs(l[1] - r[1]) <= 2:
                acts.append(("same", rel))
            elif lchg and not rchg:
                acts.append(("push", rel))
            elif rchg and not lchg:
                shrunk = rel.endswith(".json") and l[0] > 2048 and r[0] < l[0] * 0.6
                acts.append(("shrunk" if shrunk else "pull", rel))
            else:
                acts.append(("conflict_push" if l[1] >= r[1] else "conflict_pull", rel))
        elif l and not r:
            keep = first or lchg or not b.get("r") or rel.startswith(PROTECT)
            acts.append(("push", rel) if keep else ("del_local", rel))
        elif r and not l:
            keep = first or rchg or not b.get("l") or rel.startswith(PROTECT)
            acts.append(("pull", rel) if keep else ("del_remote", rel))
    return acts


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def _keep(remote_root, kind, rel, src, who):
    """被取代或刪掉的那份留一份在雲端 kind/時間-電腦/路徑，不會不見。"""
    if src.exists():
        dst = remote_root / kind / f"{_stamp()}-{who}" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def read_lock(remote_root):
    try:
        return json.loads((Path(remote_root) / LOCK).read_text())
    except (OSError, ValueError):
        return {}


def busy_elsewhere(remote_root, my_id, now=None):
    """別台電腦 5 分鐘內同步過、還沒釋放 → 回傳那台的記號；否則 None。"""
    lk = read_lock(remote_root)
    now = now or time.time()
    if lk.get("id") and lk["id"] != my_id and now - (lk.get("t") or 0) < LOCK_FRESH:
        return lk
    return None


@contextlib.contextmanager
def local_lock(local_root, timeout=600):
    """跨程序的本機鎖（runs/.drive_sync.lock）：拿不到就等，超過 timeout 秒丟 TimeoutError。"""
    p = Path(local_root) / LOCAL_LOCK
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p, "a+")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("另一個同步一直沒結束") from None
                time.sleep(0.1)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def sync(local_root, remote_root, my_id=None, device=DEVICE, force=False, pull_only=False, progress=None, lock_timeout=600):
    """同一台電腦上同時只跑一個（local_lock）；其餘說明見 _sync。"""
    with local_lock(local_root, timeout=lock_timeout):
        return _sync(local_root, remote_root, my_id, device, force, pull_only, progress)


def _sync(local_root, remote_root, my_id=None, device=DEVICE, force=False, pull_only=False, progress=None):
    """回傳 {動作: 數量}；別台正在用且沒有 force → 回傳 {"blocked": 那台電腦名}。
    pull_only：別台正在用時，只把雲端較新的檔拉下來看（不推、不刪、不搶使用中、不更新 base）。
    progress(第幾個, 共幾個, 檔名, {動作: 數量})：給開機畫面顯示進度。"""
    local_root, remote_root = Path(local_root), Path(remote_root)
    remote_root.mkdir(parents=True, exist_ok=True)
    my_id = my_id or device_id()
    if pull_only:
        n = {}
        loc, rem = scan(local_root), scan(remote_root)
        todo = [rel for rel, r in rem.items() if not loc.get(rel) or _sig(r)[1] > _sig(loc[rel])[1] + 2]
        for i, rel in enumerate(todo, 1):
            _copy(remote_root / rel, local_root / rel)
            n["pull"] = n.get("pull", 0) + 1
            if progress:
                progress(i, len(todo), rel, n)
        return n
    other = busy_elsewhere(remote_root, my_id)
    if other and not force:
        return {"blocked": other.get("device") or "另一台電腦"}
    sp = local_root / STATE
    saved = json.loads(sp.read_text()) if sp.exists() else {}
    base = saved.get("files", {}) if saved.get("remote") == str(remote_root) else {}  # 換了雲端資料夾：當第一次，只合併不刪
    who_r = (read_lock(remote_root).get("device") or read_lock(remote_root).get("closed") or "另一台")
    n = {}
    loc, rem = scan(local_root), scan(remote_root)
    acts = [a for a in plan(loc, rem, base)]
    dels = [rel for act, rel in acts if act in ("del_local", "del_remote")]
    if len(dels) > MAX_DELETE and len(dels) > 0.05 * max(len(loc), len(rem), 1):
        return {"refused": len(dels), "examples": dels[:5]}  # 一次要刪很多：多半是讀不到或搬家，先不動，等本人確認
    if progress:
        progress(0, len(acts), "", n)
    for i, (act, rel) in enumerate(acts, 1):
        lp, rp = local_root / rel, remote_root / rel
        if act in ("push", "conflict_push", "shrunk"):
            if act != "push":
                _keep(remote_root, "_同步衝突", rel, rp, who_r)
            _copy(lp, rp)
        elif act in ("pull", "conflict_pull"):
            if act == "conflict_pull":
                _keep(remote_root, "_同步衝突", rel, lp, device)
            _copy(rp, lp)
        elif act == "del_local":
            _keep(remote_root, "_同步刪除", rel, lp, device)
            lp.unlink(missing_ok=True)
        elif act == "del_remote":
            _keep(remote_root, "_同步刪除", rel, rp, who_r)
            rp.unlink(missing_ok=True)
        n[act] = n.get(act, 0) + 1
        if progress:
            progress(i, len(acts), rel, n)
    l2, r2 = scan(local_root), scan(remote_root)
    files = {rel: {"l": _sig(l2.get(rel)), "r": _sig(r2.get(rel))} for rel in set(l2) & set(r2)}
    sp.write_text(json.dumps({"remote": str(remote_root), "files": files}, ensure_ascii=False))
    (remote_root / LOCK).write_text(json.dumps({"device": device, "id": my_id, "t": int(time.time())}, ensure_ascii=False))
    return n


def release(remote_root, my_id=None, device=DEVICE):
    """收工：拿掉「使用中」記號，別台電腦就能接著用。"""
    my_id = my_id or device_id()
    lk = read_lock(remote_root)
    if lk.get("id") == my_id:
        (Path(remote_root) / LOCK).write_text(json.dumps({"device": "", "t": 0, "closed": device, "closed_t": int(time.time())}, ensure_ascii=False))
        return True
    return False
