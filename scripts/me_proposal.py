"""把本人的研究計畫書 Word 檔匯入 runs/_me/（只存本機與本人的雲端硬碟，不進 git）：
依原檔順序保留標題、段落、圖（原始圖檔）、表（真的表格），教授頁「研究計畫書」照這個排版顯示。

  uv run python scripts/me_proposal.py import <計畫書.docx>

圖檔寫到 runs/_me/proposal/figures/；結構寫進 runs/_me/me.json 的 proposal.document（每個區塊的中文由翻譯者另外補 zh）。
"""
import argparse
import json
from pathlib import Path

from pipeline.docx_doc import parse_docx

ME = Path(__file__).resolve().parent.parent / "runs" / "_me"
HEADING_ZH = {"synopsis": "摘要", "rationale": "1. 研究背景與缺口", "aims": "2. 整體目的與目標", "programme": "3. 研究規劃與方法",
              "contribution": "4. 預期貢獻與各研究的整合", "timeline": "5. 時程與里程碑", "resources": "6. 資源、設施與預算概估",
              "references": "參考文獻"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["import"])
    ap.add_argument("docx")
    a = ap.parse_args()
    d = parse_docx(a.docx)
    figdir = ME / "proposal" / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    for name, data in d["media"].items():
        (figdir / name).write_bytes(data)
    mep = ME / "me.json"
    me = json.loads(mep.read_text())
    old = {s.get("key"): s for s in (me.get("proposal") or {}).get("document") or []}
    secs = []
    for s in d["sections"]:
        if s["key"] == "front":
            continue
        for b in s["blocks"]:
            if b["type"] == "figure":
                b["src"] = f"proposal/figures/{b.pop('media')}"  # 相對於 runs/_me/
        secs.append({**s, "heading_zh": HEADING_ZH.get(s["key"]) or (old.get(s["key"]) or {}).get("heading_zh") or s["heading_en"]})
    me.setdefault("proposal", {}).update({"document": secs, "document_src": f"{Path(a.docx).name}（本人與 Liliana 討論、她改過的版本）",
                                          "document_meta": d["meta"]})
    mep.write_text(json.dumps(me, ensure_ascii=False, indent=2))
    n = {t: sum(b["type"] == t for s in secs for b in s["blocks"]) for t in ("p", "figure", "table", "ref")}
    print(f"DONE 計畫書匯入：{len(secs)} 節；段落 {n['p']}、圖 {n['figure']}、表 {n['table']}、參考文獻 {n['ref']}；圖檔在 runs/_me/proposal/figures/")


if __name__ == "__main__":
    main()
