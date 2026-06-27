# 安全公開指南 (Open-Source Safety)

本專案可公開**程式碼、文件、前端頁面、範例假資料**，但**不應公開**第三方網站抓取後的
完整資料集。本檔說明原因、哪些檔案不能 commit、使用者如何在本機產生資料，以及
萬一已不小心 commit 資料該如何清除。

## 1. 為何不公開 `web/data.json`

- `web/data.json` 是由 SQLite 匯出的**完整持股資料集**，內容衍生自 TWSE / MoneyDJ 等
  第三方來源；其著作權歸原來源所有，公開散布可能違反來源服務條款。
- 公開站台只需要**展示 UI**，用 `examples/sample_data.json`（虛構假資料）即可達成。
- 因此公開 repo 與公開站台一律**不含**真實資料；真實資料只留在本機。

## 2. 哪些檔案不能 commit

以下皆已列入 [.gitignore](../.gitignore)，請勿用 `git add -f` 等方式強制加入：

- `web/data.json`
- `data/raw/`（抓取後的原始 HTML）
- `data/sqlite/`、`data/*.db`、`data/*.sqlite`、`data/*.sqlite3`（SQLite DB）
- `data/exports/`、`*.csv`、`*.xlsx`、`*.xls`（匯出報表）
- `data/*.log`、`data/.last_update`（log / 本機執行狀態）
- `.env`、`.env.*`（密鑰 / 本機設定）

> 可保留的：各資料夾的 `.gitkeep`（維持骨架）、`examples/sample_data.json`（虛構假資料）。

**提交前自我檢查**（應無輸出）：

```bash
git ls-files | grep -E '(^web/data\.json$|^data/raw/|^data/sqlite/|^data/exports/|\.sqlite$|\.db$|\.csv$|\.xlsx$)'
```

## 3. 使用者如何在本機產生資料

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
export PYTHONPATH=src

# 抓取 → 比對 → 產生 web/data.json（本機檔，不會被版控）
python -m active_etf_tracker.cli run --limit 5     # 測試；省略 --limit 為全部

# 開啟儀表板（有 data.json 顯示真實資料；沒有則自動 fallback 範例假資料）
python -m active_etf_tracker.cli dashboard --serve
```

## 4. 如果已經不小心 commit 了資料

`.gitignore` 只能擋**未來**的提交；若資料**已存在於 Git 歷史**，需要改寫歷史才能真正移除。

先把目前工作目錄中的追蹤移除（保留本機檔案）：

```bash
git rm --cached web/data.json
git rm --cached -r data/raw data/sqlite data/exports
git commit -m "chore: stop tracking scraped data"
```

> ⚠️ 上一步只讓「之後」不再追蹤；**舊的 commit 仍含資料**。若要從歷史徹底清除，
> 需使用下列**破壞性**指令之一（本指南僅提供，請自行評估後手動執行，勿盲目套用）：

```bash
# 方式一：git filter-repo（需先安裝 git-filter-repo）
git filter-repo --path web/data.json --invert-paths
git filter-repo --path data/raw --invert-paths
git filter-repo --path data/sqlite --invert-paths
git filter-repo --path data/exports --invert-paths

# 方式二：BFG Repo-Cleaner
bfg --delete-files data.json
bfg --delete-folders raw
bfg --delete-folders sqlite
bfg --delete-folders exports
```

> ⚠️ **history rewrite 會改變 git commit history。**
> 如果 repo 已經被其他人 fork 或 clone，需協調後再 force push。
> 改寫後需 `git push --force`（並通知協作者重新 clone 或 rebase）。

> 補充：若曾把資料推上 GitHub 公開 repo，即使改寫歷史，舊內容仍可能殘存於
> 既有的 fork、PR、或快取中。涉及敏感／受限資料時，請一併評估是否需要聯繫平台。
