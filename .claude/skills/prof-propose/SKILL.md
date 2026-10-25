---
name: prof-propose
description: 教授研究檔案流水線的「研究構想草稿」階段。prof-match 之後執行，或本人說「幫我擬 <教授> 的研究構想」時。依本人的 CV（做過、會的）與這位教授目前期間內的經費，擬一份小型、可執行的研究構想（中英），每段附依據（她的文章 id、計畫 key、本人 CV 段落）；腳本核對引用存在、經費在期間內、中英數字一致，組裝成 out/proposal.json，教授頁「研究構想草稿」顯示。是給本人改寫的素材。
---

# prof-propose（研究構想草稿）

所有指令在專案根目錄執行。擬稿者用 `model: opus`。

```bash
uv run python scripts/propose.py inputs runs/<slug>
```

派擬稿者：

> 讀 `.claude/skills/prof-propose/proposer.md` 照做。slug=<slug>

```bash
uv run python scripts/propose.py check runs/<slug>
```

`FAIL` → **只修一輪**：把 FAIL 行用 SendMessage 傳給同一個擬稿者。仍失敗 → 停下回報，不組裝。

```bash
uv run python scripts/propose.py assemble runs/<slug>
uv run python scripts/build_site.py runs/<slug>
```

## 規則

- 作者界線（本人 2026-10-26 同意）：這是素材，畫面標「草稿」；寄給教授的版本由本人改寫。
- 經費只能引用腳本算出的「目前期間內」計畫；她沒有期間內的經費就照實寫，不要編。
- 本人跟這位教授已經一起討論過研究計畫（`joint_proposal_with_this_professor`）時，構想要接續那份計畫，不要重複。
