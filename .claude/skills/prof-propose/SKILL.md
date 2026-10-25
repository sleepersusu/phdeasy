---
name: prof-propose
description: 教授研究檔案流水線的「研究計畫書草稿」階段。prof-match 之後執行，或本人說「幫我擬 <教授> 的研究計畫書／研究構想」、在應用程式按「產生研究計畫書草稿」時。以這位教授的研究方向與目前期間內的經費為主，配合本人的興趣與做得到（或可能做得到）的事，擬 2–3 個不同方向的版本（中英），每版附信心程度；分段照本人與 Liliana 討論、她改過的計畫書。腳本核對引用存在、經費在期間內、中英數字一致、信心「高」要有她主持的經費、不能有誇大用詞，組裝成 out/proposal.json，教授頁「研究計畫書」顯示。是給本人改寫的素材。
---

# prof-propose（研究計畫書草稿）

所有指令在專案根目錄執行。擬稿者用 `model: opus`。

```bash
uv run python scripts/propose.py inputs runs/<slug>
```

派擬稿者：

> 讀 `.claude/skills/prof-propose/proposer.md` 照做。slug=<slug>

```bash
uv run python scripts/propose.py check runs/<slug>
```

`FAIL` → **只修一輪**：把 FAIL 行用 SendMessage 傳給同一個擬稿者。仍失敗 → 照樣組裝：沒過核對的版本不放進頁面，記在 `work/proposal/rejected.json`；一個版本都沒過才停下回報。

重新產生時：先把舊的 `work/proposal/draft.json` 移到 `work/proposal/_old/`（不要刪）。

```bash
uv run python scripts/propose.py assemble runs/<slug>
uv run python scripts/build_site.py runs/<slug>
```

## 規則

- 作者界線（本人 2026-10-26 同意）：這是素材，畫面標「草稿」；寄給教授的版本由本人改寫。
- 經費只能引用腳本算出的「目前期間內」計畫；她沒有期間內的經費就照實寫，不要編。
- 本人跟這位教授已經一起討論過研究計畫（`joint_proposal_with_this_professor`）時，構想要接續那份計畫，不要重複。
