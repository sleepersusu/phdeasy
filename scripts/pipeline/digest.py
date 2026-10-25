"""每篇的 AI 重點（重點.json）：讓本人快速知道這篇在講什麼，中英對照。

整理者（LLM）寫：重點 3–6 條、研究設計一段、每一張圖與表在講什麼；每條附原文引句。
腳本核對：
- 圖表一張都不能漏：figures.py 抓到的每個 label 都要有一筆說明，也不能多出不存在的圖表
- 每條引句逐字在原文該位置（同解析卡的引句規則）
- 中英的數字一致（同翻譯的數字規則）
"""
from .i18n import numbers_match
from .quotes import check_quote


def _items(d):
    for i, k in enumerate(d.get("key_points") or []):
        yield f"key_points[{i}]", k
    if d.get("design"):
        yield "design", d["design"]
    for i, f in enumerate(d.get("figures") or []):
        yield f"figures[{i}]", f


def check_digest(d, text, figure_labels):
    fails = []
    kp = d.get("key_points") or []
    if not 3 <= len(kp) <= 6:
        fails.append({"path": "key_points", "why": "need_3_to_6"})
    if not d.get("design"):
        fails.append({"path": "design", "why": "missing"})
    got = [f.get("label") for f in d.get("figures") or []]
    for lab in figure_labels:
        if lab not in got:
            fails.append({"path": f"figure:{lab}", "why": "figure_missing"})
    for lab in got:
        if lab not in figure_labels:
            fails.append({"path": f"figure:{lab}", "why": "figure_not_in_paper"})
    if len(got) != len(set(got)):
        fails.append({"path": "figures", "why": "figure_duplicate"})
    for path, it in _items(d):
        en, zh = (it.get("en") or "").strip(), (it.get("zh") or "").strip()
        if not en or not zh:
            fails.append({"path": path, "why": "need_en_and_zh"})
            continue
        if not numbers_match(zh, en):
            fails.append({"path": path, "why": "numbers_differ"})
        cites = it.get("citations") or []
        if not cites:
            fails.append({"path": path, "why": "no_citation"})
        for j, c in enumerate(cites):
            ok, why = check_quote(text, c.get("quote"), c.get("loc"))
            if not ok:
                fails.append({"path": f"{path}.citations[{j}]", "why": why, "quote": c.get("quote"), "loc": c.get("loc")})
    return fails


def assemble_digest(d, text, figure_labels, figures):
    """拿掉核對不過的條目（記下來給 rejected），圖表說明併入圖片位置與標題，給前端直接用。"""
    bad = {f["path"].split(".citations")[0] for f in check_digest(d, text, figure_labels)
           if f["why"] not in ("need_3_to_6", "figure_missing", "figure_not_in_paper", "figure_duplicate")}
    rejected = []
    out = {"id": d.get("id"), "key_points": [], "design": None, "figures": []}
    for i, k in enumerate(d.get("key_points") or []):
        (rejected if f"key_points[{i}]" in bad else out["key_points"]).append(k)
    if d.get("design") and "design" not in bad:
        out["design"] = d["design"]
    by = {f["label"]: f for f in figures}
    explained = {}
    for i, f in enumerate(d.get("figures") or []):
        if f"figures[{i}]" in bad or f.get("label") not in by:
            rejected.append(f)
            continue
        explained[f["label"]] = f
    for lab in figure_labels:  # 依原文順序；沒有通過核對的圖表也要列出（只有標題，沒有 AI 說明）
        src = by[lab]
        e = explained.get(lab) or {}
        out["figures"].append({"label": lab, "caption": src.get("caption"), "image": src.get("image"), "loc": src.get("loc"),
                               "en": e.get("en"), "zh": e.get("zh"), "citations": e.get("citations") or []})
    return out, rejected
