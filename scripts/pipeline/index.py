"""pdfs/index.csv：每篇的全文狀態。寫入先寫暫存檔再替換，中途失敗不會清空舊檔。"""
import csv
import io
from pathlib import Path

FIELDS = ["id", "year", "kind", "status", "source", "ext", "path", "sha256", "url", "tried", "title"]


def load_index(run):
    p = Path(run) / "pdfs" / "index.csv"
    if not p.exists():
        return {}
    with open(p, newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def save_index(run, rows):
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=FIELDS)
    wr.writeheader()
    for r in sorted(rows.values(), key=lambda r: (str(r["year"]), r["id"])):
        wr.writerow({k: r.get(k, "") for k in FIELDS})
    p = Path(run) / "pdfs" / "index.csv"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(buf.getvalue())
    tmp.replace(p)
    return {r["id"]: r for r in csv.DictReader(io.StringIO(buf.getvalue()))}


def find_existing(run, work_id):
    """已歸位的全文（之前跑過但索引沒記到時用）。"""
    run = Path(run)
    for p in sorted((run / "pdfs").glob(f"*/{work_id}_*")):
        if p.parent.name != "_rejected" and p.suffix in (".pdf", ".xml"):
            return str(p.relative_to(run))
    return None


def reject_file(run, work_id, index, hashes):
    """抓錯的檔案移到 pdfs/_rejected/（不刪），雜湊紀錄跟著搬，索引列移除以便重找。回傳新相對路徑。"""
    run = Path(run)
    row = index.pop(work_id)
    src = run / row["path"]
    dest = run / "pdfs" / "_rejected" / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists() or not dest.exists():  # 已經移過（例：重跑 --reject）就不再搬
        src.replace(dest)
    rel = str(dest.relative_to(run))
    if row["path"] in hashes:
        hashes[rel] = hashes.pop(row["path"])
    return rel
