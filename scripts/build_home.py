"""產生個人首頁 runs/index.html，並重建每位教授的詳細頁（讓它們帶入本人的比對內容）。

  uv run python scripts/build_home.py runs   # 結尾會同步到 Google 雲端硬碟（drive_sync.py）
"""
import argparse
import json
from pathlib import Path

from drive_sync import run as drive_sync
from pipeline.home import build_home_data, professors_index, render_home
from pipeline.site import build_site_data, render_html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default="runs")
    runs = Path(ap.parse_args().runs)
    for d in sorted(runs.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "work" / "works.json").exists():
            out = d / "out" / "site" / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            data = build_site_data(d)
            (out.parent / "data.json").write_text(json.dumps(data, ensure_ascii=False))
            out.write_text(render_html(data))
    (runs / "professors.json").write_text(json.dumps(professors_index(runs), ensure_ascii=False, indent=1))
    data = build_home_data(runs)
    (runs / "index.html").write_text(render_home(data))
    me = data["me"]["name"] if data["me"] else "（尚無本人資料）"
    print(f"DONE {runs / 'index.html'}：{me}；教授 {len(data['professors'])} 位：" +
          "、".join(f"{p['name']}（重疊 {p['n_overlap_papers']} 篇）" for p in data["professors"]))
    drive_sync(runs)  # 每次重建首頁就同步到雲端硬碟


if __name__ == "__main__":
    main()
