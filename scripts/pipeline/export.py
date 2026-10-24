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
