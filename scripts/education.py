"""教授學歷（官方個人頁）：UCSF 教授用官方 Profiles API 讀（不用 AI），寫 runs/<slug>/out/education.json。

  uv run python scripts/education.py runs/<slug>

個人頁網址依序找：目標系所的教員名單（runs/_me/targets.json）、basic.json 的網址、博士學程的教員名單出處。
不是 UCSF 的教授由博士學程查詢者一起讀（programs.py 存），這支腳本不處理。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline.education import parse_ucsf, ucsf_name
from pipeline.http import get_json


def profile_urls(run):
    st = json.loads((run / "state.json").read_text())
    name = " ".join(((st.get("professor") or {}).get("name") or "").lower().split())
    urls = []
    tp = run.parent / "_me" / "targets.json"
    if tp.exists():
        for sc in json.loads(tp.read_text()).get("schools") or []:
            for d in sc.get("departments") or []:
                for p in ((d.get("faculty") or {}).get("people") or []):
                    if " ".join((p.get("name") or "").lower().split()) == name and p.get("profile_url"):
                        urls.append(p["profile_url"])
    b = run / "work" / "basic.json"
    if b.exists():
        urls += [u.get("url") for u in json.loads(b.read_text()).get("urls") or [] if u.get("url")]
    pg = run / "out" / "programs.json"
    if pg.exists():
        urls += [p.get("member_src") for p in json.loads(pg.read_text()).get("programs") or [] if p.get("member_src")]
    return urls


def main(argv=None):
    run = Path((argv or sys.argv[1:])[0])
    url = next((u for u in profile_urls(run) if ucsf_name(u)), None)
    if not url:
        print("SKIP 不是 UCSF 個人頁：學歷由博士學程查詢者讀")
        return 0
    items = parse_ucsf(get_json(f"https://api.profiles.ucsf.edu/json/v2/?ProfilesURLName={ucsf_name(url)}&source=phdeasy"), url)
    if not items:
        print(f"SKIP UCSF 個人頁沒有寫學歷：{url}")
        return 0
    (run / "out").mkdir(exist_ok=True)
    (run / "out" / "education.json").write_text(json.dumps({"fetched": datetime.now().astimezone().date().isoformat(), "source": "ucsf_api", "items": items},
                                                           ensure_ascii=False, indent=1))
    print(f"DONE 學歷 {len(items)} 筆（UCSF Profiles）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
