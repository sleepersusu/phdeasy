"""E2E 總檢查：重跑所有可機械核對的項目。每個檢查回傳 {name, pass, detail}。"""
import csv
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from .cards import check_card, validate_card
from .fetch import sha256_file
from .grants import check_mention
from .profile import fact_lookup
from .state import load_state

CHAIN_REQUIRED = ["zotero", "openalex", "landing", "unpaywall", "europepmc", "pmc_oa", "semantic_scholar", "preprints", "core", "inbox"]


def _j(p, d=None):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else d


def _r(name, ok, detail=""):
    return {"name": name, "pass": bool(ok), "detail": detail}


def check_hashes(run):
    hashes = _j(run / "work" / "hashes.json", {})
    bad = [rel for rel, h in hashes.items() if not (run / rel).exists() or sha256_file(run / rel) != h]
    return _r("hashes_unchanged", not bad, f"{len(hashes)} 個原檔；改變 {bad}" if bad else f"{len(hashes)} 個原檔雜湊不變")


def check_works(run, works):
    ids = [w["id"] for w in works]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    years = [w["id"] for w in works if not (2022 <= (w.get("year") or 0) <= 2026)]
    return _r("works_list", not dup and not years, f"{len(ids)} 篇；重複 {dup}；年份超出 {years}")


def check_cards(run, works):
    missing, schema, quotes = [], [], []
    n_cites = 0
    for w in works:
        c = _j(run / "work" / "cards" / w["id"] / "card.json")
        if c is None:
            missing.append(w["id"])
            continue
        errs = validate_card(c, w["kind"])
        if errs:
            schema.append(f"{w['id']}:{errs[0]}")
        text = (run / "work" / "text" / f"{w['id']}.txt")
        fails = check_card(c, text.read_text() if text.exists() else "")
        quotes += [f"{w['id']} {f['path']} {f['why']}" for f in fails]
        n_cites += sum(len(x.get("citations") or []) for x in _cite_holders(c))
    return [
        _r("cards_coverage", not missing, f"{len(works) - len(missing)}/{len(works)} 篇有卡；缺 {missing}"),
        _r("cards_schema", not schema, "7 欄齊全" if not schema else "; ".join(schema[:5])),
        _r("cards_quotes", not quotes, f"引句 {n_cites} 則全數核對通過" if not quotes else "; ".join(quotes[:8])),
    ]


def _cite_holders(c):
    f = c.get("fields") or {}
    for k in ("summary", "design", "sample"):
        if k in f:
            yield f[k]
    for k in ("gap", "solves", "findings"):
        yield from (f.get(k) or {}).get("claims") or []
    lim = f.get("limitations") or {}
    yield from lim.get("author_stated") or []
    yield from lim.get("inferred") or []


def check_network(run):
    diff = _j(run / "work" / "count-diff.json")
    net = _j(run / "work" / "network.json", {})
    ok = diff == [] and bool(net.get("coauthors"))
    return _r("network_counts", ok, "腳本與獨立計數一致" if ok else f"count-diff={diff}")


def check_grants(run):
    grants = _j(run / "work" / "grants" / "grants_final.json")
    if grants is None:
        return _r("grants_evidence", False, "沒有 grants_final.json")
    bad = []
    for g in grants:
        ev = g.get("evidence") or []
        if not ev:
            bad.append(f"{g['key']} 沒有證據")
        for e in ev:
            if e.get("type") == "ack":
                t = run / "work" / "text" / f"{e['work_id']}.txt"
                why = check_mention(t.read_text() if t.exists() else "", {"quote": e["quote"], "loc": e["loc"], "award_id": None})
                if why != "ok":
                    bad.append(f"{g['key']} {e['work_id']} {why}")
    return _r("grants_evidence", not bad, f"{len(grants)} 筆計畫都有證據、致謝引句核對通過" if not bad else "; ".join(bad[:6]))


def check_profile(run, works):
    final = _j(run / "work" / "profile" / "final.json")
    facts = _j(run / "work" / "profile" / "facts.json", {})
    if final is None:
        return _r("profile_traceable", False, "沒有 work/profile/final.json")
    ids = {w["id"] for w in works}
    bad, n = [], 0
    for s in final.get("sections", []):
        for cl in s.get("claims", []):
            n += 1
            refs = cl.get("refs") or []
            if not refs:
                bad.append(f"沒有出處：{cl.get('text', '')[:30]}")
            for r in refs:
                if r.startswith("fact:") and fact_lookup(facts, r[5:]) is None or (not r.startswith("fact:") and r not in ids):
                    bad.append(f"出處不存在 {r}")
    return _r("profile_traceable", not bad, f"總覽 {n} 句都追溯得到出處" if not bad else "; ".join(bad[:6]))


def check_index(run, works):
    p = run / "pdfs" / "index.csv"
    rows = {}
    if p.exists():
        with open(p, newline="") as f:
            rows = {r["id"]: r for r in csv.DictReader(f)}
    missing = [w["id"] for w in works if w["id"] not in rows]
    lazy = []
    for r in rows.values():
        if r["status"] == "no_free_fulltext":
            tried = {t.split(":")[0] for t in (r.get("tried") or "").split("; ") if t}
            if not set(CHAIN_REQUIRED) <= tried:
                lazy.append(f"{r['id']} 缺 {sorted(set(CHAIN_REQUIRED) - tried)}")
    return [
        _r("fulltext_status", not missing, f"{len(rows)} 篇都有全文狀態" if not missing else f"沒有狀態：{missing}"),
        _r("fulltext_tried_all", not lazy, "無免費全文者都試過全文找尋鏈所有來源" if not lazy else "; ".join(lazy[:4])),
    ]


def check_ris(run, works):
    ris = list((run / "out" / "zotero").glob("*.ris"))
    if not ris:
        return _r("ris", False, "沒有 RIS")
    text = ris[0].read_text()
    recs = [r for r in text.split("ER  -") if r.strip()]
    ids = set(re.findall(r"N1  - OpenAlex (W\d+)", text))
    files = re.findall(r"L1  - (file://\S+)", text)
    gone = [f for f in files if not Path(unquote(urlparse(f).path)).exists()]
    ok = len(recs) == len(works) and ids == {w["id"] for w in works} and not gone
    return _r("ris", ok, f"{len(recs)} 筆（文章 {len(works)}），附檔 {len(files)}，檔案不存在 {len(gone)}")


def check_state(run, works):
    st = load_state(run)
    probs = []
    if st.get("works_total") not in (None, len(works)):
        probs.append(f"works_total={st.get('works_total')} 但文章 {len(works)}")
    if st.get("circuit", {}).get("tripped"):
        probs.append("熔斷中")
    site = run / "out" / "site" / "index.html"
    if not site.exists():
        probs.append("沒有前端頁面")
    else:
        html = site.read_text()
        miss = [w["id"] for w in works if f'"id": "{w["id"]}"' not in html]
        if miss:
            probs.append(f"前端缺文章 {miss[:5]}")
    if not (run / "out" / "profile.md").exists():
        probs.append("沒有 out/profile.md")
    return _r("state_consistent", not probs, "state.json、前端、總覽與實際產出一致" if not probs else "; ".join(probs))


def run_all(run):
    run = Path(run)
    works = _j(run / "work" / "works.json", [])
    out = [check_hashes(run), check_works(run, works)]
    out += check_cards(run, works)
    out += [check_network(run), check_grants(run), check_profile(run, works)]
    out += check_index(run, works)
    out += [check_ris(run, works), check_state(run, works)]
    return out
