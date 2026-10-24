# phdeasy

輸入一位教授，產出近五年（2022–2026 出版）所有文章的研究檔案：

- 跟誰合作、跟誰合作最多（以 OpenAlex 作者 id 計數）
- 注重哪些研究領域
- 有哪些研究計畫（NIH、NSF、GRB／國科會、CORDIS、UKRI、論文致謝）
- 每篇文章的解析卡：大意、研究設計、研究樣本、研究缺口、解決什麼、發現、研究限制，每個說法附原文引句與頁碼

設計正本：[docs/design.md](docs/design.md)。

## 流程

| 階段 | stage | skill | 誰 |
|---|---|---|---|
| 停 1：確認身分與文章、找全文 | `setup` → `stop1` | `prof-setup` | 本人確認 |
| 標準化 | `ingest` | `prof-ingest` | 自動 |
| 合作與領域 | `network` | `prof-network` | 自動 |
| 研究計畫 | `grants` | `prof-grants` | 自動 |
| 解析卡 | `cards` | `prof-cards` | 自動 |
| 總覽 | `profile` | `prof-profile` | 自動 |
| 驗收 | `verify` → `stop2` | `prof-verify` | 本人看結果 |

## 開始一批新的

在 Claude Code 裡說：「幫我建教授檔案：<姓名>，<學校>（ORCID 可選）」。`prof-setup` 會在 `runs/<slug>/` 建好批次資料夾，跑到停 1 給你確認。

```bash
uv sync
uv run pytest
```

## 資料夾結構

```
runs/<slug>/
  protocol.md  state.json  progress.md  missing.md
  inbox/            你補的 PDF（不會被改動）
  pdfs/<年>/        全文歸位：<文章id>_<第一作者>_<短標題>.pdf，附 index.csv
  work/             中間產物
  out/              profile.md、papers/、data/*.csv、zotero/*.ris
  verify/           驗收報告
```

`runs/` 含有論文全文，不進版本控制。

## 怎麼確保沒出錯

- 數量（合作者、領域分佈）由腳本算，另派一個 agent 獨立計數比對。
- 每個引句由腳本逐字核對原文該頁。
- 研究設計與樣本由兩個不同模型各自抽取再比對。
- 缺口、發現、限制等推論另派 agent 專門試著推翻。
- 全文找尋鏈試遍 Zotero、OpenAlex、Unpaywall、Europe PMC、PMC、Semantic Scholar、預印本平台、CORE，每次嘗試都記錄。
- 原始 PDF 雜湊值在結尾比對，確認沒被改動。
