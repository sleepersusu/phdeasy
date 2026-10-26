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
        "recommend": _enrich(d.get("recommend"), W, G),
        "proposal": _proposal_summary(d),
    }


def _proposal_summary(d):
    """首頁「計畫書」頁籤：定案版或 AI 草稿各版的方向與信心（與 web/home.js 的 proposalSummary 相同）。"""
    j, pd = d.get("joint_proposal"), d.get("proposal_draft")
    return {"joint": bool(j), "joint_title": (j or {}).get("title"), "joint_title_zh": (j or {}).get("title_zh"), "stale": bool((pd or {}).get("stale")),
            "versions": [{"id": v.get("id"), "level": (v.get("confidence") or {}).get("level"), "direction_zh": (v.get("direction") or {}).get("zh"),
                          "direction_en": (v.get("direction") or {}).get("en")} for v in (pd or {}).get("versions") or []]}


def _enrich(r, W, G):
    """prof-match 的推薦只存 id：帶入標題、年份、計畫狀態（與 web/index.html 的 enrichRecommend 相同）。"""
    if not r:
        return None
    paper = lambda x: {**x, "title": W.get(x["id"], {}).get("title"), "title_zh": W.get(x["id"], {}).get("title_zh"), "year": W.get(x["id"], {}).get("year")}
    grant = lambda x: {**x, "title": G.get(x["key"], {}).get("title") or G.get(x["key"], {}).get("funder"),
                       "title_zh": G.get(x["key"], {}).get("title_zh") or G.get(x["key"], {}).get("funder_zh"),
                       "status": G.get(x["key"], {}).get("status"), "award_id": G.get(x["key"], {}).get("award_id")}
    return {**r, "targets": [{**t, "papers": [paper(x) for x in t["papers"]], "grants": [grant(x) for x in t["grants"]]} for t in r["targets"]],
            "read_first": [paper({"id": i}) for i in r["read_first"]]}


def professors_index(runs):
    """應用程式首頁（web/index.html）讀的教授清單：比對在瀏覽器裡算，這裡只給位置。"""
    runs = Path(runs)
    out = []
    for d in sorted(runs.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "state.json").exists() and (d / "work" / "works.json").exists():
            st = _j(d / "state.json") or {}
            out.append({"slug": d.name, "name": (st.get("professor") or {}).get("name"), "institution": (st.get("professor") or {}).get("institution"),
                        "stage": st.get("stage"), "data": f"{d.name}/out/site/data.json", "built": (d / "out" / "site" / "data.json").exists()})
    return out


def build_home_data(runs, use_node=True):
    runs = Path(runs)
    me = _j(runs / "_me" / "me.json")
    profs = []
    for d in sorted(runs.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "state.json").exists() and (d / "work" / "works.json").exists():
            profs.append(professor_summary(d, me, use_node=use_node))
    from .mydocs import index
    return {"me": me, "professors": profs, "docs": index(runs / "_me" / "docs")}


WEB = Path(__file__).resolve().parents[2] / "web"


def render_home(data):
    """離線單檔版首頁：資料與比對程式內嵌進 web/index.html（應用程式直接讀 runs/ 的 JSON，在瀏覽器裡比對）。"""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    js = (WEB / "site_match.js").read_text()
    html = (WEB / "index.html").read_text().replace("__INLINE__", payload, 1)
    html = html.replace('<link rel="stylesheet" href="home.css">', f"<style>\n{(WEB / 'home.css').read_text()}</style>", 1)
    html = html.replace('<script src="home.js"></script>', f"<script>\n{(WEB / 'home.js').read_text()}\n</script>", 1)
    return html.replace('<script src="site_match.js"></script>', f"<script>\n{js}\n</script>", 1).replace('<script src="app.js"></script>\n', "", 1)
