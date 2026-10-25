---
name: prof-network
description: 教授研究檔案流水線的合作與領域階段（自動段）。當某批次 runs/<slug>/state.json 的 stage 為 network，或 prof-ingest 交棒時使用。用腳本以作者 id 算合作者排名、作者序角色、年度與領域分佈並由腳本自我核對，寫 out/data/ 的 CSV，然後交給 prof-grants。
---

# prof-network（自動段：合作與領域）

數量一律由腳本算；LLM 只做獨立計數，用來抓腳本的錯。所有指令在專案根目錄執行。

## 0. 開工檢查

```bash
uv sync -q && uv run pytest -q -p no:warnings
uv run python scripts/state_cli.py show runs/<slug>
```

- 測試沒過 → 停下回報。
- `stage` 不是 `network` → 改用對應 skill（`CLAUDE.md` 階段表）。

## 1. 準備

- `work/count-diff.json` 已存在且為 `[]` → 這段已完成，直接跳到第 3 步。

## 2. 主流程

1. **腳本計算**
   ```bash
   uv run python scripts/network.py build runs/<slug>
   ```
   產出 `work/network.json`、`work/author_lists.md`、`out/data/{works,coauthors,topics}.csv`。
   - 合作者以 OpenAlex 作者 id 計數。沒 id 的作者，「姓氏＋名字首字母」只對得上唯一一位有 id 的人才合併（記在 `merged_names`）；對得上多位就維持分開。
2. **自我核對**
   ```bash
   uv run python scripts/network.py check runs/<slug>
   ```
   核對每位合作者的篇數＝文章清單、文章都存在、年度加總、依篇數排序。`FAIL` → 腳本有錯：先寫一個會失敗的測試、修 `scripts/pipeline/network.py`、重跑 build 與 check。
   （本人 2026-10-26 拿掉獨立計數 agent：合作者由作者 id 機械計算，重數同一份資料抓不到新錯。）
3. **抽看結果**：`head -12 runs/<slug>/out/data/coauthors.csv`、`cat runs/<slug>/out/data/topics.csv | head -20`，確認沒有本人出現在合作者裡、沒有明顯同一人被拆成兩個。發現拆分 → 同第 2 步「腳本錯」的處理。

## 3. 收尾

```bash
uv run python scripts/state_cli.py progress runs/<slug> network "<篇數> 篇；合作者 <人數>（有 id <x>，姓名合併 <m>）；前 3：<姓名 n>…；計數比對 PASS／例外"
uv run python scripts/state_cli.py stage runs/<slug> grants
```

接著執行 `prof-grants`；該 skill 還不存在時，停下並回報本段數字。

## 規則

- 不手改 `work/network.json` 或 CSV，一律改腳本重跑。
- 研究領域的「敘述」不在這段寫，留給 `prof-profile`；這段只產出分佈數字。
