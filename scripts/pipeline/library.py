"""討論文獻：教授丟給本人的文獻（上傳 PDF、貼 DOI、從 Zotero 選）。

存在 runs/<教授>/library/，資料夾結構跟一位教授的批次一樣（work/works.json、pdfs/、work/text/、out/papers/），
所以找全文、轉文字、抓圖表、AI 重點與核對都直接用同一套腳本。這裡只放討論文獻專用的部分：
DOI 抽取、標記誰給的、Zotero 唯讀清單、RIS 匯出、勾選擬初稿的核對。
"""
import re

from .propose import check_version

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def doi_from_text(text):
    m = DOI_RE.search(text or "")
    if not m:
        return None
    d = m.group(1).rstrip(".,;]")
    while d.endswith(")") and d.count(")") > d.count("("):  # 句子的括號，不是 DOI 的一部分
        d = d[:-1]
    return d.lower()


def tag_item(w, given_by=None, discussion=None, note=None, source=None, today=None):
    """記下誰給的、哪次討論；討論文獻一律當完整文章處理（要全文重點）。"""
    return {**w, "kind": "full", "library": {"given_by": given_by or None, "discussion": discussion or None, "note": note or None,
                                             "source": source, "added": today}}


def parse_zotero_items(raw):
    """Zotero 本機 API（唯讀）的項目清單 → 給本人勾選；附件、筆記不列。"""
    out = []
    for it in raw or []:
        d = it.get("data") or {}
        if d.get("itemType") in ("attachment", "note", "annotation"):
            continue
        cr = [c.get("lastName") or c.get("name") or "" for c in d.get("creators") or []]
        out.append({"key": it.get("key"), "title": d.get("title"), "doi": (d.get("DOI") or "").lower() or None,
                    "year": (re.search(r"\d{4}", d.get("date") or "") or [None])[0], "authors": ", ".join(c for c in cr[:3] if c)})
    return out


def ris_export(items, digests, pdf_paths):
    """匯出到 Zotero：本人自己匯入（不寫入本人的 Zotero 文獻庫）。筆記放中文重點與誰給的。"""
    lines = []
    for w in items:
        lib = w.get("library") or {}
        lines += ["TY  - JOUR", f"TI  - {w.get('title') or ''}"]
        lines += [f"AU  - {a.get('name')}" for a in w.get("authors") or [] if a.get("name")]
        for tag, v in (("PY", w.get("year")), ("DO", w.get("doi")), ("JO", w.get("venue"))):
            if v:
                lines.append(f"{tag}  - {v}")
        who = "、".join(x for x in (lib.get("given_by") and f"{lib['given_by']} 給的", lib.get("discussion") and f"{lib['discussion']} 討論") if x)
        if who:
            lines.append(f"N1  - {who}")
        kp = (digests.get(w["id"]) or {}).get("key_points") or []
        if kp:
            lines.append("N1  - AI 重點（中）：" + "；".join(k.get("zh") or "" for k in kp))
        if pdf_paths.get(w["id"]):
            lines.append(f"L1  - {pdf_paths[w['id']]}")
        lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def lib_entry_paths(figures):
    """討論文獻的圖表放在 library/out/papers/…；教授頁的 data.json 在 out/site/，路徑要多走一層到 library/。"""
    fix = lambda p: ("../../library/out/" + p[3:]) if p and p.startswith("../papers/") else p
    return [{**f, "image": fix(f.get("image"))} for f in figures or []]


NEED_SOURCE = ("synopsis", "rationale", "contribution")


def check_lib_draft(v, selected, prof_ids, active):
    """用勾選的文獻擬的初稿：格式與核對同計畫書草稿；只能引勾選的文獻與她的文章；說法段落每段都要附出處。"""
    fails = check_version(v, set(selected) | set(prof_ids), active)
    paths = [(k, (v or {}).get(k)) for k in NEED_SOURCE]
    paths += [(f"gaps[{i}]", g) for i, g in enumerate((v or {}).get("gaps") or [])]
    paths += [(f"studies[{i}].methods", (st or {}).get("methods")) for i, st in enumerate((v or {}).get("studies") or [])]
    for path, it in paths:
        if isinstance(it, dict) and not [r for r in it.get("refs") or [] if not r.startswith("cv:")]:
            fails.append({"path": path, "why": "needs_source"})
    cited = set()
    for _, it in paths:
        cited |= set((it or {}).get("refs") or [])
    if not cited & set(selected):
        fails.append({"path": "refs", "why": "must_cite_selected"})
    return fails
