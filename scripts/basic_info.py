"""教授基本資訊：抓 ORCID 公開紀錄與 OpenAlex 作者資料，寫 work/basic.json（教授首頁頂端讀它）。

  uv run python scripts/basic_info.py runs/<slug>
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from pipeline.basic import parse_openalex_author, parse_orcid
from pipeline.http import get_json, openalex_params
from pipeline.works import strip_prefix


def professor_orcid(run):
    """本人填的 ORCID 優先；沒填就用 OpenAlex 鎖定的那位作者的 ORCID（從教員名單勾選建檔時通常沒填）。"""
    st = json.loads((run / "state.json").read_text())
    orcid = strip_prefix((st.get("professor") or {}).get("orcid") or "")
    if orcid:
        return orcid
    p = run / "work" / "author_candidates.json"
    cands = json.loads(p.read_text()) if p.exists() else []
    me = next((c for c in cands if c.get("id") == st.get("author_id")), None)
    return strip_prefix((me or {}).get("orcid") or "") or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    run = Path(ap.parse_args().run)
    st = json.loads((run / "state.json").read_text())
    orcid = professor_orcid(run)
    out = {"fetched": datetime.now().date().isoformat(), "orcid": orcid or None, "author_id": st.get("author_id"), "sources": {}}
    if orcid:
        try:
            out.update(parse_orcid(get_json(f"https://pub.orcid.org/v3.0/{orcid}/record")))
            out["sources"]["orcid"] = f"https://orcid.org/{orcid}"
        except RuntimeError as e:
            out["sources"]["orcid"] = f"failed: {e}"
    if st.get("author_id"):
        try:
            out["metrics"] = parse_openalex_author(get_json(f"https://api.openalex.org/authors/{st['author_id']}?" + openalex_params().lstrip("&")))
            out["sources"]["openalex"] = f"https://openalex.org/{st['author_id']}"
        except RuntimeError as e:
            out["sources"]["openalex"] = f"failed: {e}"
    (run / "work" / "basic.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    pos = out.get("position") or {}
    print(f"DONE 基本資訊：{pos.get('title') or '職稱未提及'}｜{pos.get('institution') or '機構未提及'}；"
          f"h-index {(out.get('metrics') or {}).get('h_index')}；經歷 {len(out.get('employments') or [])}、學歷 {len(out.get('educations') or [])}")


if __name__ == "__main__":
    main()
