"""profile：教授總覽。

  uv run python scripts/profile.py facts runs/<slug>     # 彙整事實 → work/profile/facts.json；匯出 out/papers/*.md 與含筆記的 RIS
  （派總覽撰寫者 → work/profile/draft.json）
  uv run python scripts/profile.py check runs/<slug>     # 每句要有 refs、refs 存在、數字對得上；有錯 exit 1
  （派總覽推翻者 → work/profile/refute.json）
  uv run python scripts/profile.py assemble runs/<slug>  # 套用推翻 → out/profile.md
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.export import paper_md_name, render_paper_md, to_ris
from pipeline.profile import build_facts, check_draft, render_profile_md
from pipeline.state import load_state


def _j(p, d=None):
    return json.loads(p.read_text()) if p.exists() else d


def _load(run):
    st = load_state(run)
    works = _j(run / "work" / "works.json", [])
    cards = {w["id"]: _j(run / "work" / "cards" / w["id"] / "card.json") for w in works}
    cards = {k: v for k, v in cards.items() if v}
    grants = _j(run / "work" / "grants" / "grants_final.json", [])
    net = _j(run / "work" / "network.json", {})
    return st, works, cards, grants, net


def facts(run):
    st, works, cards, grants, net = _load(run)
    pd = run / "work" / "profile"
    pd.mkdir(parents=True, exist_ok=True)
    with open(run / "pdfs" / "index.csv", newline="") as fh:
        ok = sum(r["status"] == "ok" for r in csv.DictReader(fh))
    f = build_facts(st["professor"], works, net, cards, grants, fulltext_ok=ok)
    (pd / "facts.json").write_text(json.dumps(f, ensure_ascii=False, indent=2))
    papers = run / "out" / "papers"
    papers.mkdir(parents=True, exist_ok=True)
    for w in works:
        if w["id"] in cards:
            (papers / paper_md_name(w)).write_text(render_paper_md(w, cards[w["id"]]))
    with open(run / "pdfs" / "index.csv", newline="") as fh:
        index = {r["id"]: r for r in csv.DictReader(fh)}
    notes = {wid: "phdeasy 解析｜大意：" + ((c.get("fields") or {}).get("summary") or {}).get("text", "") for wid, c in cards.items()}
    (run / "out" / "zotero" / f"{run.name}.ris").write_text(to_ris(works, index, run, tags=[f"phdeasy:{run.name}"], notes=notes))
    print(f"DONE facts：{len(works)} 篇、卡片 {len(cards)}、單篇 md {len(cards)}、RIS 已加筆記；設計類型 {f['design_types']}；本人計畫 {len(f['grants_pi'])}")


def check(run):
    st, works, cards, grants, net = _load(run)
    f = _j(run / "work" / "profile" / "facts.json")
    draft = _j(run / "work" / "profile" / "draft.json")
    fails = check_draft(draft, f, {w["id"] for w in works}, cards=cards, works={w["id"]: w for w in works})
    (run / "work" / "profile" / "check.json").write_text(json.dumps(fails, ensure_ascii=False, indent=2))
    for x in fails:
        print(f"FAIL {x['path']} {x['why']}：{x['text'][:60]}")
    if fails:
        sys.exit(1)
    n = sum(len(s.get("claims", [])) for s in draft["sections"])
    print(f"PASS 總覽 {n} 句全部有出處且數字對得上")


def assemble(run):
    st, works, cards, grants, net = _load(run)
    pd = run / "work" / "profile"
    f, draft = _j(pd / "facts.json"), _j(pd / "draft.json")
    ref = _j(pd / "refute.json", {"verdicts": []})
    verdicts = {v["path"]: v for v in ref.get("verdicts", [])}
    failed = {x["path"] for x in _j(pd / "check.json", [])}
    missing, kept_sections, rejected = [], [], []
    for s in draft["sections"]:
        claims = []
        for i, cl in enumerate(s.get("claims", [])):
            path = f"{s['key']}[{i}]"
            v = verdicts.get(path)
            if v is None:
                missing.append(path)
            if path in failed or (v and v.get("verdict") == "reject"):
                rejected.append({"path": path, "text": cl["text"], "reason": (v or {}).get("reason") or "出處核對不過"})
                continue
            claims.append(cl)
        kept_sections.append({**s, "claims": claims})
    if missing:
        print(f"FAIL 推翻者漏判 {len(missing)} 句：{missing}")
        sys.exit(1)
    final = {"sections": kept_sections}
    (pd / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2))
    (run / "out" / "profile.md").write_text(render_profile_md(st["professor"], f, final))
    if rejected:
        p = run / "out" / "rejected.md"
        with open(p, "a") as fh:
            for r in rejected:
                fh.write(f"## [profile] {r['path']}\n\n- 時間：{datetime.now().astimezone().isoformat(timespec='seconds')}\n- 理由：{r['reason']}\n- 內容：{r['text']}\n\n")
    n = sum(len(s["claims"]) for s in kept_sections)
    print(f"DONE out/profile.md：保留 {n} 句，推翻 {len(rejected)} 句")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["facts", "check", "assemble"])
    ap.add_argument("run")
    a = ap.parse_args()
    {"facts": facts, "check": check, "assemble": assemble}[a.cmd](Path(a.run))


if __name__ == "__main__":
    main()
