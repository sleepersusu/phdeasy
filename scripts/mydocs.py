"""本人的文件（Research Proposal、Personal Statement、Statement of Purpose）：上傳、版本、每段 AI 編修、翻譯。

  uv run python scripts/mydocs.py upload <ps|sop|proposal> <檔案.docx|.pdf> [--for <教授>]   # 新版本
  uv run python scripts/mydocs.py block <文件> --version N --block i       # 給編修者：這一段與前後文
  uv run python scripts/mydocs.py apply-edit <文件> --version N --block i --edit <edit.json>   # 編修結果存成新版本
  uv run python scripts/mydocs.py check <文件> --version N                # 翻譯者寫完 zh 後核對（每段都有中文、數字一致）
  uv run python scripts/mydocs.py index                                    # 更新 runs/_me/docs/index.json（首頁讀它）
  uv run python scripts/mydocs.py migrate                                  # 一次性：把 me.json 裡的計畫書與 Personal Statement 轉成第 1 版

<文件> 是 ps、sop、proposal 或 proposal--<教授>。檔案只存在 runs/_me/docs/（雲端硬碟同步，不進 git）。
"""
import argparse
import json
import sys
from pathlib import Path

from pipeline.i18n import numbers_match
from pipeline.mydocs import apply_edit, blocks_of, doc_key, index, list_versions, load, new_version, parse_upload, _write

ME = Path(__file__).resolve().parent.parent / "runs" / "_me"
ROOT = ME / "docs"


def write_index():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.json").write_text(json.dumps(index(ROOT), ensure_ascii=False, indent=1))


def migrate():
    """me.json 已有的計畫書（跟 Liliana 定案的）與 Personal Statement → 第 1 版（已有版本就不重做）。"""
    me = json.loads((ME / "me.json").read_text())
    done = []
    st = (me.get("statements") or {}).get("ps")
    if st and not list_versions(ROOT, "ps"):
        new_version(ROOT, "ps", {"title": st.get("title"), "title_zh": st.get("title_zh"), "author": st.get("author"), "blocks": st["blocks"]},
                    note=f"從 {st.get('src')} 匯入")
        done.append("ps")
    p = me.get("proposal") or {}
    key = doc_key("proposal", me.get("proposal_with")) if me.get("proposal_with") else "proposal"
    if p.get("document") and not list_versions(ROOT, key):
        secs = p["document"]  # 圖的 src 已經是相對於 runs/_me/ 的路徑（proposal/figures/…），沿用
        _write(ROOT, key, {"title": p.get("title"), "title_zh": p.get("title_zh"), "subtitle": p.get("subtitle"),
                           "meta": p.get("document_meta") or [], "sections": secs},
               {"origin": "upload", "note": f"從 {p.get('document_src') or 'Word'} 匯入（跟 Liliana 定案的版本）", "file": None})
        done.append(key)
    write_index()
    print(f"DONE 轉成第 1 版：{', '.join(done) or '（都已經有版本）'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["upload", "block", "apply-edit", "check", "index", "migrate"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--for", dest="slug")
    ap.add_argument("--version", type=int)
    ap.add_argument("--block", type=int)
    ap.add_argument("--edit")
    a = ap.parse_args()
    if a.cmd == "index":
        write_index()
        print("DONE runs/_me/docs/index.json")
        return
    if a.cmd == "migrate":
        migrate()
        return
    if a.cmd == "upload":
        kind, path = a.args
        key = doc_key(kind, a.slug)
        v = new_version(ROOT, key, parse_upload(path), source=path, note=f"上傳 {Path(path).name}")
        write_index()
        n = len(blocks_of(load(ROOT, key, v["n"])))
        print(f"DONE {key} 第 {v['n']} 版：{n} 段（還沒有中文，請翻譯者補）")
        return
    key = a.args[0]
    if a.cmd == "block":
        items = blocks_of(load(ROOT, key, a.version))
        ctx = lambda i: items[i][1].get("en") if 0 <= i < len(items) else None
        print(json.dumps({"key": key, "version": a.version, "block": a.block, "en": ctx(a.block), "zh": items[a.block][1].get("zh"),
                          "before": ctx(a.block - 1), "after": ctx(a.block + 1), "total": len(items)}, ensure_ascii=False, indent=1))
        return
    if a.cmd == "apply-edit":
        e = json.loads(Path(a.edit).read_text())
        v = apply_edit(ROOT, key, a.version, a.block, e.get("en"), e.get("zh"), note=e.get("note"))
        write_index()
        print(f"DONE {key} 第 {v['n']} 版（從第 {a.version} 版改第 {a.block + 1} 段）")
        return
    if a.cmd == "check":
        fails = []
        for i, (_, b) in enumerate(blocks_of(load(ROOT, key, a.version))):
            if not (b.get("zh") or "").strip():
                fails.append(f"第 {i + 1} 段沒有中文")
            elif not numbers_match(b["zh"], b["en"]):
                fails.append(f"第 {i + 1} 段中英數字對不上")
        for f in fails:
            print("FAIL", f)
        if fails:
            sys.exit(1)
        write_index()
        print(f"PASS {key} 第 {a.version} 版每段都有中文、數字一致")


if __name__ == "__main__":
    main()
