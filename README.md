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

## 應用程式（看資料＋跑流水線）

Windows：到 [Releases](https://github.com/sleepersusu/phdeasy/releases) 下載 `PhdeasyProfessorFiles-Setup.exe` 安裝。Mac：雙擊 repo 裡的 `開啟教授檔案.command`。

這台電腦要先有：

1. **Google Drive 電腦版**並登入：教授檔案放在 `我的雲端硬碟/phdeasy教授檔案`，每台打開都會同步；登入多個帳號時，第一次打開會問用哪一個。
2. **Claude Code** 並登入：要在這台建新教授才需要；只看資料可以不用。
3. **uv**：沒有的話，首頁「建新教授」那一區會問你要不要自動安裝（從 astral.sh 官方安裝，不用管理員權限）。

打開後是自己的視窗（Windows 用 Edge 的 App 視窗，Mac 用 Chrome；沒有就用瀏覽器），關掉視窗就結束並同步。第一次打開若這台登入多個 Google 帳號，視窗最上方會讓你選一個。


- 首頁：你的 CV 與研究計畫 → 教授比對 → 點進去是教授詳細頁。網頁是做好的 HTML／JS（`web/`），資料從 `runs/` 的 JSON 讀，比對在瀏覽器裡算。
- **建新教授**：填姓名、學校，按「開始建檔」。這台的 Claude Code 在背景跑到停 1；停 1／停 2 的報告和要你決定的事會出現在畫面上，你在框裡回覆就接著跑。各教授列表有「繼續跑」可以從中斷的地方接續。
- 背景執行的權限只開流水線用到的工具（讀寫專案檔、`uv run`、派 subagent、查網頁），其他指令一律拒絕；卡住時畫面上會說卡在哪。
- 開著每 3 分鐘同步一次；另一台電腦正在用時，這台只能看，不能跑流水線。關掉視窗會最後同步一次並釋放。

安裝版第一次打開會把內建的流水線（scripts、skills、web、CLAUDE.md）放到 `使用者\phdeasy`，教授資料在 `使用者\phdeasy\runs`；更新版本時只換流水線，不動教授資料。發新版：推一個 `v*` 版號，GitHub Actions 只打包 Windows。

你的資料放在 `runs/_me/me.json`（不進 git，經雲端硬碟同步）。

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

`runs/` 含有論文全文，不進版本控制；改由 Google 雲端硬碟同步（`<我的雲端硬碟>/phdeasy教授檔案/`），每位教授一個資料夾。兩台都改過的檔案用較新的，舊的收在 `_同步衝突/`；同一時間只讓一台電腦同步（雲端 `_使用中.json`，5 分鐘沒動靜就算放開）。

換一台電腦（Mac 或 Windows）：

1. 安裝 Google Drive 電腦版並登入同一個 Google 帳號。
2. `git clone` 這個 repo，`uv sync`。
3. `uv run python scripts/drive_sync.py runs --setup` 列出帳號，`--account <email>` 選定。
4. `uv run python scripts/drive_sync.py runs` 拉下全部教授檔案。之後在 Claude Code 裡照常說「幫我建教授檔案…」，每段結束會自動同步。
5. 收工時說「收工」，Claude Code 會跑 `--release`，另一台才能接著用。

## 怎麼確保沒出錯

- 數量（合作者、領域分佈）由腳本算，另派一個 agent 獨立計數比對。
- 每個引句由腳本逐字核對原文該頁。
- 研究設計與樣本由兩個不同模型各自抽取再比對。
- 缺口、發現、限制等推論另派 agent 專門試著推翻。
- 全文找尋鏈試遍 Zotero、OpenAlex、Unpaywall、Europe PMC、PMC、Semantic Scholar、預印本平台、CORE，每次嘗試都記錄。
- 原始 PDF 雜湊值在結尾比對，確認沒被改動。
