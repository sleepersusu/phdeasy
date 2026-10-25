"""匯出：Zotero 用的 RIS、停 1 報告用的輔助函式。"""
from pathlib import Path

from .works import _similar

RIS_TYPE = {"article": "JOUR", "review": "JOUR", "preprint": "UNPB", "conference-abstract": "ABST", "book-chapter": "CHAP", "dissertation": "THES"}


def _au(name):
    parts = (name or "").split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else (name or "")


def to_ris(works, index, run_root, tags=(), notes=None):
    """每篇一筆；有全文時 L1 指向 pdfs/ 內的絕對路徑，Zotero 匯入時會一起附上檔案。notes: {id: 筆記文字}。"""
    root = Path(run_root).resolve()
    out = []
    for w in works:
        lines = [f"TY  - {RIS_TYPE.get(w.get('type'), 'JOUR')}", f"TI  - {w.get('title') or ''}"]
        lines += [f"AU  - {_au(a.get('name'))}" for a in w.get("authors") or []]
        if w.get("year"):
            lines.append(f"PY  - {w['year']}")
        if w.get("venue"):
            lines.append(f"T2  - {w['venue']}")
        if w.get("doi"):
            lines.append(f"DO  - {w['doi']}")
            lines.append(f"UR  - https://doi.org/{w['doi']}")
        if w.get("abstract"):
            lines.append(f"AB  - {' '.join(w['abstract'].split())}")
        lines += [f"KW  - {t}" for t in tags]
        lines.append(f"N1  - OpenAlex {w['id']}")
        if notes and notes.get(w["id"]):
            lines.append(f"N1  - {' '.join(notes[w['id']].split())}")
        row = index.get(w["id"]) or {}
        if row.get("status") == "ok" and row.get("path"):
            lines.append(f"L1  - file://{root / row['path']}")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


def unpaired_preprints(works):
    pubs = [w for w in works if w.get("type") != "preprint"]
    out = []
    for w in works:
        if w.get("type") != "preprint":
            continue
        best = max(pubs, key=lambda p: _similar(p["title"], w["title"]), default=None)
        out.append({"id": w["id"], "title": w["title"], "best_match": best["id"] if best else None,
                    "best_title": best["title"] if best else None, "score": round(_similar(best["title"], w["title"]), 2) if best else 0})
    return out


LABELS = [("summary", "大意"), ("design", "研究設計"), ("sample", "研究樣本"), ("gap", "研究缺口"), ("solves", "解決什麼"), ("findings", "發現"), ("limitations", "研究限制")]
STATE_TEXT = {"not_in_source": "來源未提及", "not_applicable": "短卡不適用", "unresolved": "判不出來（見例外紀錄）"}
ROLE = {"first": "第一作者", "middle": "中間作者", "last": "最後作者"}


def paper_dir_name(w):
    """每篇一個資料夾：out/papers/<年>_<第一作者>_<短標題>_<id>/（解析.md、figures/、重點.json 都放這裡，經雲端同步）。"""
    return paper_md_name(w)[:-3]


def paper_md_name(w):
    from .fetch import pdf_relpath

    base = pdf_relpath(w, "md").rsplit("/", 1)[-1]  # <id>_<姓>_<短標題>.md
    wid, rest = base.split("_", 1)
    return f"{w['year']}_{rest[:-3]}_{wid}.md"


def basis_label(card):
    b = card.get("basis")
    if b == "fulltext":
        return "全文（預印本版本，頁碼是預印本的頁碼）" if card.get("preprint_text") else "全文"
    return {"title_only": "只有標題（沒有全文也沒有摘要）"}.get(b, "只有摘要")


def render_paper_md(w, card):
    cite = lambda cs: "".join(f'\n  > "{c["quote"]}" [{w["id"]}, {c["loc"]}]' for c in cs or [])
    L = [f"# {w['title']}", "",
         f"- {w['year']}｜{w.get('venue') or '期刊來源未提及'}｜DOI {w.get('doi') or '無'}｜文章 id {w['id']}",
         f"- 作者：{'、'.join(a.get('name') or '' for a in w.get('authors') or [])}",
         f"- 教授角色：{ROLE.get(w.get('target_position'), '作者序不明')}{'＋通訊作者' if w.get('target_corresponding') else ''}",
         f"- 解析依據：{basis_label(card)}", ""]
    f = card.get("fields") or {}
    for key, label in LABELS:
        v = f.get(key) or {"status": "not_in_source"}
        L.append(f"## {label}")
        L.append("")
        st = v.get("status")
        if st in ("not_in_source", "not_applicable") or (st == "unresolved" and not v.get("text") and not v.get("claims")):
            L += [STATE_TEXT[st], ""]
            continue
        if st == "unresolved":
            L.append(f"**{STATE_TEXT['unresolved']}**")
        if key == "limitations":
            for x in v.get("author_stated") or []:
                L.append(f"- 作者自述：{x['text']}{cite(x.get('citations'))}")
            for x in v.get("inferred") or []:
                L.append(f"- 推論（非作者原話）：{x['text']}（依據：{x.get('basis') or '未寫'}）{cite(x.get('citations'))}")
        elif "claims" in v:
            for x in v.get("claims") or []:
                L.append(f"- {x['text']}{cite(x.get('citations'))}")
        else:
            extra = []
            if key == "design" and v.get("type"):
                extra.append(f"設計類型：{v['type']}")
            if key == "sample":
                extra += [f"{lab}：{v[k]}" for k, lab in (("population", "對象"), ("n_enrolled", "納入"), ("n_analyzed", "分析"), ("country", "國家"), ("setting", "場域"), ("period", "期間")) if v.get(k) not in (None, "")]
            if extra:
                L.append("（" + "；".join(str(e) for e in extra) + "）")
            L.append(f"{v.get('text') or ''}{cite(v.get('citations'))}")
        L.append("")
    return "\n".join(L)
