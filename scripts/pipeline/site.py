"""前端：把批次資料整理成一份 JSON，嵌進單一 HTML（黑字白底，按鈕只用綠黃紅）。

缺的資料一律給明確狀態（pending + 由哪個階段產生），頁面不會出現空白欄位。
"""
import csv
import json
from pathlib import Path

from .state import STAGES, load_state

CARD_FIELDS = [
    ("summary", "大意"),
    ("design", "研究設計"),
    ("sample", "研究樣本"),
    ("gap", "研究缺口"),
    ("solves", "解決什麼"),
    ("findings", "發現"),
    ("limitations", "研究限制"),
]
SECTIONS = [
    ("match", "與我的研究比對"),
    ("overview", "總覽"),
    ("profile", "教授總覽"),
    ("decisions", "待你決定"),
    ("coauthors", "合作者"),
    ("topics", "研究領域"),
    ("grants", "研究計畫"),
    ("papers", "文章解析"),
    ("exceptions", "例外紀錄"),
    ("files", "檔案"),
]
STAGE_LABELS = {"setup": "找文章與全文", "stop1": "停 1 確認", "ingest": "轉成文字", "network": "合作與領域", "grants": "研究計畫",
                "cards": "文章解析卡", "profile": "總覽撰寫", "verify": "獨立驗收", "stop2": "停 2 呈現"}
DESIGN_LABELS = {"rct": "隨機對照試驗", "pilot-rct": "先導隨機對照試驗", "quasi-experimental": "準實驗", "single-arm": "單組介入", "cohort": "世代研究",
                 "cross-sectional": "橫斷研究", "case-control": "病例對照", "qualitative": "質性研究", "mixed-methods": "混合方法",
                 "systematic-review": "系統性回顧", "scoping-review": "範疇回顧", "meta-analysis": "統合分析", "secondary-analysis": "次級資料分析",
                 "protocol": "研究計畫書", "modeling": "模型研究", "machine-learning": "機器學習", "text-mining": "文字探勘", "other": "其他"}
INFO_KINDS = {"year_mismatch", "author_not_linked", "owner_decision", "possible_author_split", "name_merge", "title_only"}


def _j(p, default=None):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else default


def _index(run):
    p = run / "pdfs" / "index.csv"
    if not p.exists():
        return {}
    with open(p, newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def _en_list(tr, *keys):
    v = (tr or {}).get("en") or {}
    for k in keys:
        v = (v or {}).get(k) if isinstance(v, dict) else None
    return v if isinstance(v, list) else []


def _card(run, wid, kind, source_type):
    c = _j(run / "work" / "cards" / wid / "card.json")
    tr = _j(run / "work" / "cards" / wid / "i18n.json")
    en = (tr or {}).get("en") or {}
    fields = []
    for key, label in CARD_FIELDS:
        v = ((c or {}).get("fields") or {}).get(key)
        if v is None:
            fields.append({"key": key, "label": label, "state": "pending"})
        elif key == "limitations":
            sub = lambda s: [{**x, "text_en": (_en_list(tr, "limitations", s) + [None] * 99)[i]} for i, x in enumerate(v.get(s) or [])]
            fields.append({"key": key, "label": label, "state": v.get("status", "ok"),
                           "author_stated": sub("author_stated"), "inferred": sub("inferred")})
        elif key in ("gap", "solves", "findings"):
            ens = _en_list(tr, key) + [None] * 99
            fields.append({"key": key, "label": label, "state": v.get("status", "ok"),
                           "claims": [{**x, "text_en": ens[i]} for i, x in enumerate(v.get("claims") or [])]})
        else:
            facts = {}
            if key == "design" and v.get("type"):
                facts["設計類型"] = f"{DESIGN_LABELS.get(v['type'], v['type'])}（{v['type']}）"
            if key == "sample":
                for k, lab in (("population", "對象"), ("n_enrolled", "納入人數"), ("n_analyzed", "分析人數"), ("country", "國家"), ("setting", "場域"), ("period", "期間")):
                    if v.get(k) not in (None, ""):
                        facts[lab] = v[k]
            fields.append({"key": key, "label": label, "state": v.get("status", "ok"), "text": v.get("text"),
                           "text_en": en.get(key) if isinstance(en.get(key), str) else None, "citations": v.get("citations") or [], "facts": facts})
    note = "由「文章解析卡（cards）」階段產生，尚未執行" if c is None else None
    if kind == "short":
        note = (note + "；" if note else "") + "短卡：會議摘要或社論只填大意"
    if source_type == "abstract":
        note = (note + "；" if note else "") + "沒有全文，只依摘要解析"
    return {"exists": c is not None, "pending_note": note, "fields": fields,
            "title_zh": (tr or {}).get("title_zh"), "keywords_zh": (tr or {}).get("keywords_zh") or [], "keywords_en": (tr or {}).get("keywords_en") or []}


def match_docs(works, grants):
    """首頁與教授頁共用的比對文件：每篇文章與每筆計畫一段文字（中英都放）。"""
    docs = []
    for w in works:
        f = {x["key"]: x for x in w["card"]["fields"]}
        parts = [w["title"], w.get("title_zh"), *w.get("keywords_zh", []), *w.get("keywords_en", []),
                 (w.get("topic") or {}).get("name"), (w.get("topic") or {}).get("subfield"), (w.get("topic") or {}).get("field")]
        for k in ("summary", "design", "sample"):
            if k in f:
                parts += [f[k].get("text"), f[k].get("text_en")]
        for k in ("gap", "solves", "findings"):
            for c in (f.get(k) or {}).get("claims") or []:
                parts += [c.get("text"), c.get("text_en")]
        docs.append({"id": w["id"], "kind": "paper", "text": " ".join(p for p in parts if p)})
    for g in grants:
        if g.get("status") != "other":
            docs.append({"id": g["key"], "kind": "grant", "text": " ".join(p for p in (g.get("title"), g.get("title_zh"), g.get("summary_en"),
                                                                                        g.get("summary_zh"), g.get("funder"), g.get("funder_zh")) if p)})
    return docs


def _ex_state(e):
    return "resolved" if e.get("resolved") else ("info" if e["kind"] in INFO_KINDS else "open")


def build_site_data(run):
    run = Path(run)
    st = load_state(run)
    wd = run / "work"
    works = _j(wd / "works.json", [])
    idx = _index(run)
    ing = _j(wd / "ingest.json", {})
    net = _j(wd / "network.json", {}) or {}
    cands = _j(wd / "author_candidates.json", []) or []
    me = next((a for a in cands if a["id"] == st.get("author_id")), cands[0] if cands else {})
    flog = _j(wd / "grants" / "fetch_log.json", {}) or {}
    final = _j(wd / "grants" / "grants_final.json")
    grants = final if final is not None else (_j(wd / "grants" / "grants.json", []) or [])
    gtr = _j(wd / "grants" / "i18n.json", {}) or {}
    grants = [{**g, "title_zh": (gtr.get(g["key"]) or {}).get("title_zh"), "summary_en": (gtr.get(g["key"]) or {}).get("summary_en"),
               "summary_zh": (gtr.get(g["key"]) or {}).get("summary_zh"), "funder_zh": (gtr.get(g["key"]) or {}).get("funder_zh")} for g in grants]
    grants_reviewed = final is not None
    exc = st.get("exceptions", [])

    by_work_exc = {}
    for e in exc:
        by_work_exc.setdefault(e["id"], []).append(e)
    grants_by_work = {}
    for g in grants:
        for w in g.get("works", []):
            grants_by_work.setdefault(w, []).append(g["key"])

    wlist = []
    for w in sorted(works, key=lambda w: (-(w.get("year") or 0), w["id"])):
        r = idx.get(w["id"], {})
        stype = (ing.get(w["id"]) or {}).get("source_type")
        card = _card(run, w["id"], w["kind"], stype)
        wlist.append({
            "title_zh": card.pop("title_zh"), "keywords_zh": card.pop("keywords_zh"), "keywords_en": card.pop("keywords_en"),
            "id": w["id"], "title": w["title"], "year": w["year"], "type": w["type"], "kind": w["kind"], "venue": w.get("venue"),
            "doi": w.get("doi"), "authors": [{"name": a.get("name"), "id": a.get("id"), "position": a.get("position"),
                                               "corresponding": a.get("is_corresponding")} for a in w.get("authors") or []],
            "target_position": w.get("target_position"), "target_corresponding": w.get("target_corresponding"),
            "abstract": w.get("abstract"), "topic": w.get("topic") or {},
            "fulltext": r.get("status") or "unknown", "fulltext_source": r.get("source"), "text_source": stype,
            "pdf_href": f"../../{r['path']}" if r.get("status") == "ok" and r.get("path") else None,
            "grants": sorted(grants_by_work.get(w["id"], [])),
            "exceptions": [{"kind": e["kind"], "detail": e["detail"], "resolved": e.get("resolved"), "state": _ex_state(e)} for e in by_work_exc.get(w["id"], [])],
            "added_by_owner": bool(w.get("added_by_owner")),
            "card": card,
        })

    ex_list = [{**e, "state": _ex_state(e)} for e in exc]

    decisions = []
    for g in net.get("possible_splits", []):
        decisions.append({"kind": "split", "text": "可能是同一人、被 OpenAlex 拆成多個 id：" + " ／ ".join(f"{n}（{c} 篇）" for n, c in zip(g["names"], g["counts"])),
                          "action": f"確認是否合併；合併後最多 {g['combined_n_max']} 篇"})
    for g in grants:
        if g.get("status") == "pending":
            decisions.append({"kind": "grant", "text": f"研究計畫待確認：{g.get('award_id') or g.get('funder')}", "action": (g.get("refute") or {}).get("reason") or "判不出是否為本人計畫"})
    missing = [w for w in wlist if w["kind"] == "full" and w["fulltext"] == "no_free_fulltext"]
    if missing:
        decisions.append({"kind": "pdf", "text": f"{len(missing)} 篇找不到免費全文，目前只依摘要解析",
                          "action": "從圖書館下載 PDF 放進 inbox/，重跑即可升級成全文解析", "works": [w["id"] for w in missing]})

    owner = _j(run.parent / "_me" / "me.json")  # 本人（使用者）資料，不是教授
    full = [w for w in wlist if w["kind"] == "full"]
    done_idx = STAGES.index(st["stage"]) if st["stage"] in STAGES else -1
    return {
        "generated": st.get("updated"),
        "professor": {"name": st["professor"].get("name"), "author_id": st.get("author_id"), "orcid": me.get("orcid"),
                      "institution": flog.get("institution") or "; ".join(me.get("institutions") or []) or st["professor"].get("institution"),
                      "country": flog.get("country"), "years": "2022–2026"},
        "pipeline": {"stage": st["stage"], "halted": st["stage"] == "halted", "circuit": st.get("circuit"),
                     "stages": [{"key": s, "label": STAGE_LABELS.get(s, s), "state": "done" if i < done_idx else ("current" if i == done_idx else "todo")}
                                for i, s in enumerate(STAGES)]},
        "counts": {
            "works": len(wlist), "full": len(full), "short": len(wlist) - len(full),
            "fulltext_ok": sum(w["fulltext"] == "ok" for w in full), "fulltext_missing": len(missing),
            "coauthors": net.get("coauthors_total", 0), "coauthors_linked": net.get("coauthors_linked", 0),
            "grants_pi": sum(g.get("status") == "confirmed" and g.get("target_role") in ("pi", "co_pi") for g in grants),
            "grants_total": len(grants), "cards_done": sum(w["card"]["exists"] for w in wlist),
            "exceptions_open": sum(e["state"] == "open" for e in ex_list),
        },
        "roles": net.get("roles") or {}, "years": net.get("years") or {}, "topics": net.get("topics") or {},
        "coauthors": net.get("coauthors") or [], "possible_splits": net.get("possible_splits") or [],
        "grants": grants, "grants_reviewed": grants_reviewed,
        "match_docs": match_docs(wlist, grants),
        "me_query": (owner or {}).get("match"),
        "home_href": "../../../index.html",
        "profile": (_j(wd / "profile" / "final.json") or {}).get("sections", []),
        "works": wlist, "exceptions": ex_list, "decisions": decisions,
        "files": [
            {"label": "停 1 報告", "href": "../../stop1-report.md"}, {"label": "規格（protocol）", "href": "../../protocol.md"},
            {"label": "找不到全文清單", "href": "../../missing.md"}, {"label": "全文索引 index.csv", "href": "../../pdfs/index.csv"},
            {"label": "文章 works.csv", "href": "../data/works.csv"}, {"label": "合作者 coauthors.csv", "href": "../data/coauthors.csv"},
            {"label": "領域 topics.csv", "href": "../data/topics.csv"}, {"label": "計畫 grants.csv", "href": "../data/grants.csv"},
            {"label": f"Zotero 匯入檔 {run.name}.ris", "href": f"../zotero/{run.name}.ris"},
            {"label": "例外紀錄 exceptions.md", "href": "../../exceptions.md"}, {"label": "被推翻的內容 rejected.md", "href": "../rejected.md"},
            {"label": "進度紀錄 progress.md", "href": "../../progress.md"},
        ],
    }


def render_html(data):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    nav = "".join(f'<a href="#{sid}">{label}</a>' for sid, label in SECTIONS)
    sections = "".join(f'<section id="{sid}" aria-labelledby="h-{sid}"><h2 id="h-{sid}">{label}</h2><div class="body"></div></section>' for sid, label in SECTIONS)
    field_labels = "".join(f"<!-- {label} -->" for _, label in CARD_FIELDS)
    match_js = Path(__file__).with_name("site_match.js").read_text()
    return TEMPLATE.replace("__MATCHJS__", match_js).replace("__NAV__", nav).replace("__SECTIONS__", sections).replace("__FIELDS__", field_labels).replace("__DATA__", payload).replace("__NAME__", data["professor"]["name"] or "")


TEMPLATE = (Path(__file__).with_name("site_template.html")).read_text() if Path(__file__).with_name("site_template.html").exists() else ""
