"""工作進度的進度條與預估時間：看批次資料夾裡已經產生的檔案，算出目前在哪一步、做了幾成、大概還要多久。

預估時間：這一步有量到速度（開始後至少做完 1 項）就用實際速度；還沒量到、或後面的步驟，用預設每項秒數。
只是估計，畫面上標「約」。
"""
import json
import time
from pathlib import Path

# (key, 名稱, 每項預設秒數；固定步驟 total=1 就是整步的秒數)
STEPS = [("list", "列文章與比對", 180), ("fulltext", "找全文", 15), ("ingest", "轉成文字", 3), ("network", "合作與領域", 60),
         ("grants", "研究計畫", 900), ("cards", "文章解析卡", 45), ("digest", "重點、圖表與研究方法", 60),
         ("profile", "總覽撰寫", 900), ("match", "與你的研究比對", 600), ("verify", "獨立驗收", 900)]
SETUP_ONLY = ("list", "fulltext")  # 新建檔、停 1 前的回覆：只跑到停 1
DONE_STAGES = {"stop2"}


def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def _fulltext_texts(run):
    n = 0
    for t in (run / "work" / "text").glob("*.txt"):
        try:
            with open(t, encoding="utf-8") as f:
                head = f.readline()
        except OSError:
            continue
        if any(f"| {k} |" in head for k in ("pdf", "xml", "abstract")):
            n += 1
    return n


def steps_of(run):
    run = Path(run)
    w = run / "work"
    works = _j(w / "works.json", None)
    n = len(works) if isinstance(works, list) else 0
    tried = set()
    try:
        for line in open(w / "fulltext_log.jsonl", encoding="utf-8"):
            try:
                tried.add(json.loads(line).get("id"))
            except ValueError:
                pass
    except OSError:
        pass
    one = lambda ok: (1 if ok else 0, 1)
    counts = {
        "list": one(works is not None),
        "fulltext": (min(len(tried), n), n),
        "ingest": (min(len(list((w / "text").glob("*.txt"))), n), n),
        "network": one((w / "network.json").exists()),
        "grants": one((run / "out" / "data" / "grants.csv").exists()),
        "cards": (min(len(list((w / "cards").glob("*/card.json"))), n), n),
        "digest": (len(list((w / "digest").glob("*.json"))), _fulltext_texts(run)),
        "profile": one((run / "out" / "profile.md").exists()),
        "match": one((run / "out" / "match.json").exists()),
        "verify": one(((_j(run / "state.json", {}) or {}).get("stage")) in DONE_STAGES),
    }
    out = []
    for key, label, per in STEPS:
        d, t = counts[key]
        out.append({"key": key, "label": label, "done": min(d, t) if t else d, "total": t, "per_s": per})
    return out


def estimate(run, kind, samples=None, now=None):
    """samples：{步驟: (第一次看到的時間, 當時做完幾項)}，由應用程式在輪詢時記下，用來量實際速度。"""
    now = time.time() if now is None else now
    stage = (_j(Path(run) / "state.json", {}) or {}).get("stage")
    steps = steps_of(run)
    if kind in ("new", "reply") and stage in (None, "setup", "stop1", "halted") and not any(
            s["done"] for s in steps if s["key"] not in SETUP_ONLY):
        steps = [s for s in steps if s["key"] in SETUP_ONLY]
    current = next((s["key"] for s in steps if s["total"] and s["done"] < s["total"]), None)
    total_s = left_s = 0.0
    for s in steps:
        per = s["per_s"]
        smp = (samples or {}).get(s["key"])
        if s["key"] == current and smp and s["done"] > smp[1] and now > smp[0]:
            per = (now - smp[0]) / (s["done"] - smp[1])  # 實際速度
        units = max(s["total"], 1) if s["total"] else 1
        left = max(units - s["done"], 0) if s["total"] else 0
        s["eta_s"] = round(left * per)
        total_s += units * s["per_s"]
        left_s += s["eta_s"]
    done_s = sum(min(s["done"], max(s["total"], 1)) * s["per_s"] for s in steps)
    pct = 100 if current is None else min(99, round(100 * done_s / total_s)) if total_s else 0
    return {"current": current, "percent": pct, "eta_s": round(left_s) if current else 0, "steps": steps}
