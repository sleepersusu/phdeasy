"""必讀前五篇（本人 2026-10-26）：依本人的研究興趣與 CV，從標題與摘要挑出最該先讀的幾篇；
只有這幾篇走完整流程（找全文、轉文字、解析卡、重點與研究方法、圖表），其他文章 kind 改成 "title"，只列標題。
原本的種類記在 kind_orig，本人在停 1 換篇時可以還原。
"""
import re

DEEP_KINDS = ("full", "short")


def deep_works(works):
    """要做完整流程的文章（不是只列標題的）。"""
    return [w for w in works if w.get("kind") != "title"]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def check_picks(picks, works, n=5):
    by = {w["id"]: w for w in works}
    want = min(n, len(works))
    fails = []
    if len(picks) != want:
        fails.append({"where": "picks", "why": "wrong_count", "detail": f"要 {want} 篇，給了 {len(picks)} 篇"})
    seen = set()
    for i, p in enumerate(picks):
        w = f"picks[{i}]"
        if p.get("id") in seen:
            fails.append({"where": w, "why": "duplicate"})
        seen.add(p.get("id"))
        work = by.get(p.get("id"))
        if not work:
            fails.append({"where": w, "why": "unknown_id"})
            continue
        if not (p.get("reason") or "").strip():
            fails.append({"where": w, "why": "no_reason"})
        q = _norm(p.get("quote"))
        if len(q) < 12 or (q not in _norm(work.get("title")) and q not in _norm(work.get("abstract"))):
            fails.append({"where": w, "why": "quote_not_found"})
    return fails


def apply_focus(works, ids):
    """ids 以外的文章改成只列標題；ids 裡原本被改掉的還原成原本的種類。"""
    ids = list(ids)
    known = {w["id"] for w in works}
    bad = [i for i in ids if i not in known]
    if bad:
        raise ValueError(f"沒有這幾篇：{bad}")
    for w in works:
        if w["id"] in ids:
            if w.get("kind") == "title":
                w["kind"] = w.get("kind_orig") or "full"
        elif w.get("kind") != "title":
            w["kind_orig"] = w["kind"]
            w["kind"] = "title"
    return works
