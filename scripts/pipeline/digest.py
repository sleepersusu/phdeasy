"""每篇的 AI 重點（重點.json）：讓本人快速知道這篇在講什麼，中英對照。

整理者（LLM）寫：重點 3–6 條、研究設計一段、每一張圖與表在講什麼；每條附原文引句。
腳本核對：
- 圖表一張都不能漏：figures.py 抓到的每個 label 都要有一筆說明，也不能多出不存在的圖表
- 每條引句逐字在原文該位置（同解析卡的引句規則）
- 中英的數字一致（同翻譯的數字規則）
"""
from .i18n import numbers_match
from .quotes import check_quote


# 研究方法的詳細拆解（本人要求：設計、樣本、變項等要詳細，也要有限制）
METHOD_KEYS = ["design", "setting", "participants", "sample_size", "intervention", "variables", "measures", "analysis",
               "limitations_author", "limitations_inferred"]
METHOD_LABELS = {"design": ("Study design", "研究設計"), "setting": ("Setting & period", "場域與期間"),
                 "participants": ("Participants (eligibility, recruitment)", "研究對象（納入／排除、招募）"),
                 "sample_size": ("Sample size, attrition & power", "樣本數、流失與檢定力"),
                 "intervention": ("Intervention / exposure & comparator", "介入／暴露與對照"),
                 "variables": ("Variables (independent, dependent, covariates)", "變項（自變項、依變項、共變項）"),
                 "measures": ("Measures & time points", "測量工具與時間點"), "analysis": ("Statistical analysis", "統計分析"),
                 "limitations_author": ("Limitations stated by the authors", "作者自述的限制"),
                 "limitations_inferred": ("Further limitations (reviewer's inference, not the authors')", "其他限制（整理者推論，非作者原話）")}


def check_method(m, text):
    fails = []
    for k in METHOD_KEYS:
        it = (m or {}).get(k)
        if not it:
            fails.append({"path": f"method.{k}", "why": "missing_part"})
            continue
        if it.get("not_reported"):
            continue
        en, zh = (it.get("en") or "").strip(), (it.get("zh") or "").strip()
        if not en or not zh:
            fails.append({"path": f"method.{k}", "why": "need_en_and_zh"})
            continue
        if not numbers_match(zh, en):
            fails.append({"path": f"method.{k}", "why": "numbers_differ"})
        cites = it.get("citations") or []
        if not cites and k != "limitations_inferred":
            fails.append({"path": f"method.{k}", "why": "no_citation"})
        for j, c in enumerate(cites):
            ok, why = check_quote(text, c.get("quote"), c.get("loc"))
            if not ok:
                fails.append({"path": f"method.{k}.citations[{j}]", "why": why, "quote": c.get("quote"), "loc": c.get("loc")})
    return fails


def _items(d):
    for i, k in enumerate(d.get("key_points") or []):
        yield f"key_points[{i}]", k
    if d.get("bottom_line"):
        yield "bottom_line", d["bottom_line"]
    for i, f in enumerate(d.get("findings") or []):
        yield f"findings[{i}]", f
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
    # 研究發現（本人 2026-10-26）：一句白話結論＋每一項結果（事實＋白話說明），都要中英、引句
    if not d.get("bottom_line"):
        fails.append({"path": "bottom_line", "why": "missing_bottom_line"})
    if not d.get("findings"):
        fails.append({"path": "findings", "why": "missing_findings"})
    for i, f in enumerate(d.get("findings") or []):
        pe, pz = (f.get("plain_en") or "").strip(), (f.get("plain_zh") or "").strip()
        if not pe or not pz:
            fails.append({"path": f"findings[{i}]", "why": "need_plain"})
        elif not numbers_match(pz, pe):
            fails.append({"path": f"findings[{i}]", "why": "plain_numbers_differ"})
    if "method" in d:
        fails += check_method(d["method"], text)
    else:  # 重點與研究方法由同一個 agent 一次寫完（本人 2026-10-26），不能缺
        fails.append({"path": "method", "why": "missing_method"})
    for i, f in enumerate(d.get("figures") or []):  # 看圖逐步解讀（本人 2026-10-26）：每步中英都要有、數字一致
        for j, st in enumerate(f.get("detail") or []):
            en, zh = (st.get("en") or "").strip(), (st.get("zh") or "").strip()
            if not en or not zh:
                fails.append({"path": f"figures[{i}].detail[{j}]", "why": "need_en_and_zh"})
            elif not numbers_match(zh, en):
                fails.append({"path": f"figures[{i}].detail[{j}]", "why": "numbers_differ"})
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
           if f["why"] not in ("need_3_to_6", "figure_missing", "figure_not_in_paper", "figure_duplicate", "missing_method",
                               "missing_findings", "missing_bottom_line")}
    bad_detail = {f["path"] for f in check_digest(d, text, figure_labels) if ".detail[" in f["path"]}
    rejected = []
    out = {"id": d.get("id"), "key_points": [], "design": None, "figures": [], "method": None, "bottom_line": None, "findings": []}
    if d.get("bottom_line") and "bottom_line" not in bad:
        out["bottom_line"] = d["bottom_line"]
    for i, f in enumerate(d.get("findings") or []):
        (rejected if f"findings[{i}]" in bad else out["findings"]).append(f)
    if d.get("method"):
        mbad = {f["path"].split(".citations")[0] for f in check_method(d["method"], text)}
        out["method"] = [{"key": k, "label_en": METHOD_LABELS[k][0], "label_zh": METHOD_LABELS[k][1], **d["method"][k]}
                         for k in METHOD_KEYS if d["method"].get(k) and f"method.{k}" not in mbad]
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
        i = next((k for k, f in enumerate(d.get("figures") or []) if f.get("label") == lab), None)
        detail = [st for j, st in enumerate(e.get("detail") or []) if f"figures[{i}].detail[{j}]" not in bad_detail]
        out["figures"].append({"label": lab, "caption": src.get("caption"), "image": src.get("image"), "loc": src.get("loc"),
                               "table_html": src.get("table_html"),
                               "en": e.get("en"), "zh": e.get("zh"), "citations": e.get("citations") or [], "detail": detail})
    return out, rejected
