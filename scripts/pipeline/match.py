"""比對推薦：依本人的每個研究興趣與研究計畫的每個研究，從教授的解析卡與計畫中挑出「該先看的文章／計畫」。

LLM（比對者）負責判斷相關、寫理由；腳本負責核對：
- 每個興趣／研究都有一筆回答（沒有相關就寫 fit=none，不硬湊）
- 推薦的文章／計畫都存在
- 每筆理由附 evidence，且 evidence 逐字出現在該文章卡片的文字或計畫的名稱／摘要裡
- 先看清單（read_first）只能是推薦過的文章，不能重複
推翻者逐筆判 keep/reject，組裝時拿掉 reject。
"""
import hashlib
import json
import re

FITS = ("strong", "partial", "none")


def targets_from_me(me):
    """比對的對象：本人的每個研究興趣（i1…）與研究計畫的每個研究（s1…）。"""
    out = []
    for i, it in enumerate((me or {}).get("interests") or [], 1):
        out.append({"id": f"i{i}", "kind": "interest", "label": it.get("en") or it.get("zh"), "label_zh": it.get("zh") or it.get("en")})
    for i, st in enumerate(((me or {}).get("proposal") or {}).get("studies") or [], 1):
        out.append({"id": f"s{i}", "kind": "study", "label": st.get("name"), "label_zh": st.get("name_zh") or st.get("name"),
                    "detail": st.get("detail")})
    return out


def me_fingerprint(me):
    """興趣或研究計畫改了，推薦就過期了（前端會提示重新比對）。"""
    key = json.dumps({"interests": (me or {}).get("interests"), "studies": ((me or {}).get("proposal") or {}).get("studies"),
                      "goal": ((me or {}).get("match") or {}).get("goal")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


MATCH_FIELDS = ("summary", "design", "sample", "gap", "solves", "findings")  # 比對用的欄位（不放引句與限制，給比對者讀的量才小）


def _card_text(card):
    parts = []
    for k in MATCH_FIELDS:
        v = (card.get("fields") or {}).get(k)
        if not isinstance(v, dict):
            continue
        if v.get("text"):
            parts.append(f"[{k}] " + v["text"])
        for c in v.get("claims") or []:
            if c.get("text"):
                parts.append(f"[{k}] " + c["text"])
    return "\n".join(parts)


def build_inputs(me, works, cards, grants):
    papers = {}
    for w in works:
        c = cards.get(w["id"])
        if not c or c.get("basis") == "title_only":
            text = ""
        else:
            text = _card_text(c)
        papers[w["id"]] = {"title": w.get("title"), "year": w.get("year"), "kind": w.get("kind"), "text": (w.get("title") or "") + "\n" + text}
    gs = {}
    for g in grants:
        gs[g["key"]] = {"title": g.get("title") or g.get("funder"), "status": g.get("status"), "role": g.get("target_role"),
                        "text": "\n".join(x for x in (g.get("title"), g.get("funder"), g.get("abstract"), g.get("scheme")) if x)}
    return {"targets": targets_from_me(me), "papers": papers, "grants": gs}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("­", "")).strip().lower()


def check_draft(draft, inputs):
    fails = []
    tids = [t["id"] for t in inputs["targets"]]
    got = {}
    recommended = set()
    for ti, t in enumerate(draft.get("targets") or []):
        tid = t.get("target")
        if tid not in tids:
            fails.append({"path": f"targets[{ti}]", "why": "unknown_target"})
            continue
        got[tid] = t
        fit = t.get("fit")
        if fit not in FITS:
            fails.append({"path": f"targets[{ti}].fit", "why": "bad_fit"})
        items = (t.get("papers") or []) + (t.get("grants") or [])
        if fit == "none" and items:
            fails.append({"path": f"targets[{ti}]", "why": "none_with_items"})
        if fit in ("strong", "partial") and not items:
            fails.append({"path": f"targets[{ti}]", "why": "fit_without_items"})
        if not (t.get("why") or "").strip():
            fails.append({"path": f"targets[{ti}].why", "why": "empty_why"})
        for kind, pool, label in (("papers", inputs["papers"], "paper"), ("grants", inputs["grants"], "grant")):
            for j, it in enumerate(t.get(kind) or []):
                path = f"targets[{ti}].{kind}[{j}]"
                key = it.get("id") if kind == "papers" else it.get("key")
                if key not in pool:
                    fails.append({"path": path, "why": f"unknown_{label}"})
                    continue
                if not (it.get("why") or "").strip():
                    fails.append({"path": path, "why": "empty_why"})
                ev = _norm(it.get("evidence"))
                if len(ev) < 6 or ev not in _norm(pool[key]["text"]):
                    fails.append({"path": path, "why": "evidence_not_in_source"})
                if kind == "papers":
                    recommended.add(key)
    for tid in tids:
        if tid not in got:
            fails.append({"path": f"target:{tid}", "why": "missing_target"})
    rf = draft.get("read_first") or []
    if len(rf) != len(set(rf)):
        fails.append({"path": "read_first", "why": "read_first_duplicate"})
    for x in rf:
        if x not in recommended:
            fails.append({"path": f"read_first:{x}", "why": "read_first_not_recommended"})
    return fails


def item_paths(draft):
    for ti, t in enumerate(draft.get("targets") or []):
        for kind in ("papers", "grants"):
            for j, _ in enumerate(t.get(kind) or []):
                yield f"targets[{ti}].{kind}[{j}]"


def missing_verdicts(draft, verdicts):
    ok = {v["path"] for v in verdicts if v.get("verdict") in ("keep", "reject")}
    return [p for p in item_paths(draft) if p not in ok]


def assemble(draft, verdicts, inputs, fp):
    """拿掉推翻者判 reject 與核對不過的項目；興趣標籤由腳本帶入（不信任 LLM 改寫）。"""
    bad = {f["path"] for f in check_draft(draft, inputs)}
    rej = {v["path"]: v for v in verdicts if v.get("verdict") == "reject"}
    labels = {t["id"]: t for t in inputs["targets"]}
    out, rejected, kept = [], [], set()
    for ti, t in enumerate(draft.get("targets") or []):
        if t.get("target") not in labels:
            continue
        lab = labels[t["target"]]
        row = {"target": t["target"], "kind": lab["kind"], "label": lab["label"], "label_zh": lab["label_zh"],
               "fit": t.get("fit"), "why": t.get("why"), "papers": [], "grants": []}
        for kind in ("papers", "grants"):
            for j, it in enumerate(t.get(kind) or []):
                path = f"targets[{ti}].{kind}[{j}]"
                if path in rej or path in bad:
                    rejected.append({"path": path, "item": it, "reason": (rej.get(path) or {}).get("reason") or "核對不過"})
                    continue
                row[kind].append(it)
                if kind == "papers":
                    kept.add(it["id"])
        if row["fit"] != "none" and not row["papers"] and not row["grants"]:
            row["fit"], row["why"] = "none", (row["why"] or "") + "（推薦的項目都被推翻）"
        out.append(row)
    read_first = [x for x in dict.fromkeys(draft.get("read_first") or []) if x in kept]
    return {"fingerprint": fp, "targets": out, "read_first": read_first}, rejected
