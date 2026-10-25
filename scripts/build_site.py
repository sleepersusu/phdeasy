"""產生前端資料：runs/<slug>/out/site/data.json（應用程式的 web/professor.html 讀它），
以及離線單檔版 index.html（資料內嵌，雙擊就能開）。

  uv run python scripts/build_site.py runs/<slug>

每個階段收尾後都可以重跑；缺的欄位會顯示「尚未產生」與由哪個階段補上。
"""
import argparse
import json
from pathlib import Path

from pipeline.site import build_site_data, render_html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    run = Path(ap.parse_args().run)
    data = build_site_data(run)
    out = run / "out" / "site" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    out.write_text(render_html(data))
    c = data["counts"]
    print(f"DONE {out}：文章 {c['works']}、合作者 {c['coauthors']}、計畫 {c['grants_total']}、解析卡 {c['cards_done']}/{c['works']}、待決定 {len(data['decisions'])}")


if __name__ == "__main__":
    main()
