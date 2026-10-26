"""本人的文件：Research Proposal（研究計畫書）、Personal Statement、Statement of Purpose（SOP）。

放在 runs/_me/docs/<文件>/v<N>/（只存本機與本人的雲端硬碟，不進 git）：
- 每次上傳 Word／PDF 就是一個新版本（原檔留在 source.docx／source.pdf）
- 每段 AI 編修也是一個新版本（只換那一段，其他段照舊）；舊版本都不動
- 中文（zh）由翻譯者補在同一版本裡，不算新版本
"""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .docx_doc import parse_docx, parse_statement
from .i18n import numbers_match

DOC_KINDS = {"proposal": ("Research Proposal", "研究計畫書"), "ps": ("Personal Statement", "個人陳述"),
             "sop": ("Statement of Purpose", "研究目的陳述（SOP）")}


def doc_key(kind, slug=None):
    """Personal Statement 一份；Research Proposal 每位教授一份（proposal--<教授>）；
    Statement of Purpose 每個學校系所一份（sop--<系所 id>，本人 2026-10-26）。"""
    if kind not in DOC_KINDS:
        raise ValueError(f"沒有這種文件：{kind}")
    if slug and not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"教授代號不對：{slug}")
    return f"{kind}--{slug}" if kind in ("proposal", "sop") and slug else kind


def parse_upload(path):
    """Word：計畫書樣式（有 ProposalHeading1）照章節與圖表；沒有標題樣式的短文照段落。PDF：依段落抽文字。"""
    path = Path(path)
    if path.suffix.lower() == ".docx":
        d = parse_docx(path)
        if len(d["sections"]) > 1:
            return {"title": d["title"], "subtitle": d["subtitle"], "meta": d["meta"], "sections": d["sections"], "media": d["media"]}
        st = parse_statement(path)
        return {"title": st["title"], "author": st["author"], "blocks": st["blocks"]}
    if path.suffix.lower() == ".pdf":
        import pymupdf
        paras = []
        for page in pymupdf.open(path):
            for b in page.get_text("blocks"):
                t = re.sub(r"\s+", " ", b[4]).strip()
                if t and not re.fullmatch(r"(page\s*)?\d+", t, re.I):
                    paras.append(t)
        title = paras[0] if paras else None
        return {"title": title, "blocks": [{"type": "note" if t.startswith("[") and t.endswith("]") else "p", "en": t} for t in paras[1:]]}
    raise ValueError("只收 .docx 或 .pdf")


def _versions_dir(root, key):
    return Path(root) / key


def list_versions(root, key):
    d = _versions_dir(root, key)
    out = []
    for v in sorted(d.glob("v*/version.json"), key=lambda p: int(p.parent.name[1:])):
        out.append(json.loads(v.read_text()))
    return out


def _write(root, key, doc, meta, source=None):
    vs = list_versions(root, key)
    n = (vs[-1]["n"] if vs else 0) + 1
    vd = _versions_dir(root, key) / f"v{n}"
    vd.mkdir(parents=True)
    media = doc.pop("media", None) or {}
    for name, data in media.items():  # 計畫書的圖：放在這一版的 figures/，區塊裡記相對路徑
        (vd / "figures").mkdir(exist_ok=True)
        (vd / "figures" / name).write_bytes(data)
    for s in doc.get("sections") or []:
        for b in s.get("blocks") or []:
            if b.get("type") == "figure" and b.get("media"):
                b["src"] = f"docs/{key}/v{n}/figures/{b.pop('media')}"  # 相對於 runs/_me/
    if source:
        shutil.copyfile(source, vd / f"source{Path(source).suffix.lower()}")
    (vd / "doc.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    meta = {"n": n, "created": datetime.now().astimezone().isoformat(timespec="seconds"), **meta}
    (vd / "version.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return meta


def new_version(root, key, doc, source=None, note=None):
    return _write(root, key, doc, {"origin": "upload", "note": note or (Path(source).name if source else None),
                                   "file": Path(source).name if source else None}, source=source)


def load(root, key, n):
    return json.loads((_versions_dir(root, key) / f"v{n}" / "doc.json").read_text())


def blocks_of(doc):
    """依顯示順序列出可編修的文字區塊（段落、小標、待填說明）；回傳 [(位置, 區塊)]。"""
    out = []
    if doc.get("sections"):
        for si, s in enumerate(doc["sections"]):
            for bi, b in enumerate(s.get("blocks") or []):
                if b.get("type") in ("p", "h2", "h3", "note"):
                    out.append(((si, bi), b))
    else:
        out = [((None, bi), b) for bi, b in enumerate(doc.get("blocks") or []) if b.get("type") in ("p", "h2", "h3", "note")]
    return out


def apply_edit(root, key, base, block, en, zh, note=None):
    """第 base 版的第 block 段（blocks_of 的順序）換成 AI 編修後的中英文，存成新版本。"""
    if not (en or "").strip() or not (zh or "").strip():
        raise ValueError("編修後的中英文都要有")
    if not numbers_match(zh, en):
        raise ValueError("編修後的中英文數字對不上")
    doc = load(root, key, base)
    items = blocks_of(doc)
    if not 0 <= block < len(items):
        raise ValueError(f"第 {base} 版沒有第 {block} 段")
    (si, bi), b = items[block]
    new = {**b, "en": en.strip(), "zh": zh.strip()}
    if si is None:
        doc["blocks"][bi] = new
    else:
        doc["sections"][si]["blocks"][bi] = new  # 圖的 src 沿用上一版的位置，不複製
    return _write(root, key, doc, {"origin": "ai-edit", "base": base, "changed": [block], "note": note})


def change(root, key, base, op, block, en=None, zh=None, note=None):
    """本人自己改：edit（改這一段）、delete（刪這一段）、insert_after（在這一段後面加一段）。每次都存成新版本，舊版不動。"""
    if op not in ("edit", "delete", "insert_after"):
        raise ValueError(f"不支援的動作：{op}")
    doc = load(root, key, base)
    items = blocks_of(doc)
    if not 0 <= block < len(items):
        raise ValueError(f"第 {base} 版沒有第 {block + 1} 段")
    (si, bi), b = items[block]
    seq = doc["blocks"] if si is None else doc["sections"][si]["blocks"]
    if op in ("edit", "insert_after"):
        if not (en or "").strip() and not (zh or "").strip():
            raise ValueError("內容不能空白")
        new = {"type": b["type"] if op == "edit" else "p", "en": (en or "").strip(), "zh": (zh or "").strip()}
        if op == "edit":
            seq[bi] = {**b, **new}
        else:
            seq.insert(bi + 1, new)
    else:
        del seq[bi]
    origin = {"edit": "edit", "delete": "delete", "insert_after": "insert"}[op]
    changed = [] if op == "delete" else [block if op == "edit" else block + 1]
    return _write(root, key, doc, {"origin": origin, "base": base, "changed": changed, "note": note or {"edit": f"改第 {block + 1} 段",
                  "delete": f"刪掉第 {block + 1} 段", "insert_after": f"在第 {block + 1} 段後面加一段"}[op]})


def index(root):
    """首頁讀的索引：每份文件的版本清單與最新版內容（舊版內容按需要再讀 v<N>/doc.json）。"""
    root = Path(root)
    out = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        vs = list_versions(root, d.name)
        if vs:
            kind, _, slug = d.name.partition("--")
            out[d.name] = {"kind": kind, "for": slug or None, "versions": vs, "latest": load(root, d.name, vs[-1]["n"])}
    return out
