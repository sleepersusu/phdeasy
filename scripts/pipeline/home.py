"""個人首頁（runs/index.html）：本人資料 → 教授比對清單 → 各教授詳細頁。

本人資料在 runs/_me/me.json（只存本機）。比對重用前端同一份 site_match.js，由 node 執行，
所以首頁的摘要和教授頁裡的比對結果一致。比對只呈現重疊與證據，不是適配判斷。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .site import build_site_data

MATCH_CLI = Path(__file__).with_name("match_cli.mjs")
TEMPLATE = Path(__file__).with_name("home_template.html")


def _j(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def match_with_node(docs, query):
    if not shutil.which("node"):
        return []
    r = subprocess.run(["node", str(MATCH_CLI)], input=json.dumps({"docs": docs, "query": query}), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)


def _design_code(w):
    f = next((x for x in w["card"]["fields"] if x["key"] == "design"), {}) or {}
    label = (f.get("facts") or {}).get("設計類型") or ""
    m = re.search(r"（([a-z-]+)）", label)
    return m.group(1) if m else None


def professor_summary(run, me, use_node=True):
    d = build_site_data(run)
    m = (me or {}).get("match") or {}
    # 研究設計另外比（design_overlap），不混進主題比對
    query = " ".join([m.get("goal") or "", (m.get("tags") or "").replace(",", " ")]).strip()
    ranked = match_with_node(d["match_docs"], query) if (use_node and query) else []
    W = {w["id"]: w for w in d["works"]}
    G = {g["key"]: g for g in d["grants"]}
    papers = [r for r in ranked if r["kind"] == "paper"]
    grants = [r for r in ranked if r["kind"] == "grant"]
    top = papers[0]["score"] if papers else 1
    count = {}
    for r in ranked[:10]:
        for t in r.get("terms") or []:
            count[t] = count.get(t, 0) + 1
    designs = {}
    for w in d["works"]:
        c = _design_code(w)
        if c:
            designs[c] = designs.get(c, 0) + 1
    return {
        "slug": run.name,
        "href": f"{run.name}/out/site/index.html",
        "built": (run / "out" / "site" / "index.html").exists(),
        "name": d["professor"]["name"],
        "institution": d["professor"]["institution"],
        "counts": d["counts"],
        "stage": d["pipeline"]["stage"],
        "n_overlap_papers": len(papers),
        "n_strong": sum(1 for r in papers if r["score"] >= top * 0.5),
        "shared_terms": [t for t, _ in sorted(count.items(), key=lambda kv: -kv[1])][:12],
        "top_papers": [{"id": r["id"], "title": W[r["id"]]["title"], "title_zh": W[r["id"]].get("title_zh"), "year": W[r["id"]]["year"],
                        "terms": (r.get("terms") or [])[:6], "pct": round(r["score"] / top * 100)} for r in papers[:3]],
        "top_grants": [{"key": r["id"], "title": G[r["id"]].get("title") or G[r["id"]].get("funder"),
                        "title_zh": G[r["id"]].get("title_zh") or G[r["id"]].get("funder_zh"), "status": G[r["id"]]["status"],
                        "award_id": G[r["id"]].get("award_id"), "end": G[r["id"]].get("end")} for r in grants[:2]],
        "design_overlap": [{"method": mth, "n": designs.get(mth, 0)} for mth in (m.get("methods") or [])],
        "designs": designs,
    }


def build_home_data(runs, use_node=True):
    runs = Path(runs)
    me = _j(runs / "_me" / "me.json")
    profs = []
    for d in sorted(runs.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "state.json").exists() and (d / "work" / "works.json").exists():
            profs.append(professor_summary(d, me, use_node=use_node))
    return {"me": me, "professors": profs}


def render_home(data):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("__DATA__", payload)
