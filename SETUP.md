# 上手指南 SETUP（安裝與執行）

> 這份文件給**第一次使用本專案的人或 AI 模型**。照著做即可從零安裝、跑起來、看到結果。
> 專案在做什麼：每天抓台股**股票型主動式 ETF**（代號第六碼 `A`）的持股，與前一個資料日期比對，
> 產出「新增/出清/加碼/減碼/權重升降」異動與「多檔共同加減碼榜」，並提供 CSV / Excel / 互動式網頁儀表板。

---

## 0. 系統需求
- **作業系統**：macOS 或 Linux（Windows 用 WSL 亦可）。每日更新為手動執行。
- **Python 3.10 以上**（開發實測 3.14）。確認：`python3 --version`
- **網路**：需連到 TWSE 與 MoneyDJ。
- **磁碟**：約 400MB（多數是 Playwright 的 Chromium 瀏覽器）。
- 不需要 .NET / Node.js；爬蟲用 Playwright 的 Chromium。

---

## 1. 安裝（一次性）

```bash
# 1) 進入專案根目錄
cd ActiveEtfTracker

# 2) 建立並啟用虛擬環境
python3 -m venv .venv
source .venv/bin/activate          # Windows(WSL 以外): .venv\Scripts\activate

# 3) 安裝 Python 套件
pip install --upgrade pip
pip install -r requirements.txt

# 4) 安裝 Playwright 瀏覽器（首次必跑，約 100~150MB）
playwright install chromium
```

> 套件：playwright、beautifulsoup4、lxml、pandas、openpyxl。

---

## 2. 執行方式（兩種擇一）

本專案未強制 `pip install`，預設用 `PYTHONPATH=src` 直接跑模組：

```bash
export PYTHONPATH=src
python -m active_etf_tracker.cli <子指令>
```

或安裝成可執行指令（之後可直接打 `active-etf`）：

```bash
pip install -e .
active-etf <子指令>
```

> 下文一律以 `python -m active_etf_tracker.cli` 示範（記得先 `export PYTHONPATH=src`）。

---

## 3. 第一次跑（建議流程）

### (A) 快速測試：只抓 3 檔，確認環境 OK
```bash
export PYTHONPATH=src
python -m active_etf_tracker.cli run --limit 3
```
看到每檔印出「✓ 資料日期 …，N 檔完整持股」即代表抓取與解析正常。

### (B) 完整跑：抓全部 27 檔股票型 A
```bash
python -m active_etf_tracker.cli run
```
`run` 會依序做：抓清單 → 抓完整持股 → 比對 → 共同加減碼 → 匯出 CSV/Excel → 更新前端 `web/data.json`。
首次只會有「一個資料日期」，所以**異動與共同榜會是空的**——這是正常的（見第 6 節）。

---

## 4. 看結果

| 形式 | 位置 / 指令 |
|---|---|
| CSV | `data/exports/*.csv`（清單、各檔持股、異動、共同加減碼） |
| Excel | `data/exports/active_etf_report_*.xlsx`（多工作表） |
| **互動式儀表板** | `python -m active_etf_tracker.cli dashboard --serve` → 開瀏覽器 http://localhost:8000 |
| DB 內容 | `python -m active_etf_tracker.cli list` |

儀表板三個畫面：ETF 清單總覽 / 單檔持股+異動 / 共同加碼減碼榜（色彩採台股慣例：紅=加碼漲、綠=減碼跌）。

> **「更新資料」按鈕**：用 `dashboard --serve` 開啟時，頁面右上有按鈕可直接觸發一次完整更新，
> 完成後自動刷新。為避免被來源網站封鎖，後端強制 **30 分鐘冷卻一次**（按鈕會倒數、重啟不重置）。
> 靜態部署（GitHub Pages）無後端時按鈕自動隱藏。

---

## 5. 先預覽完整 UI（可選）
第一天沒有「前一日」可比，異動/共同榜是空的。想**立刻看到完整畫面**，可產生示範前一日資料：

```bash
python scripts/seed_demo.py          # 產生示範前一日 + 更新 data.json
python -m active_etf_tracker.cli dashboard --serve
# 預覽完想還原成真實狀態：
python scripts/seed_demo.py --clean
```
> 示範資料是把當日持股做確定性擾動產生的「假昨天」，僅供預覽，**非真實買賣**。

---

## 6. 真實異動怎麼來（重要觀念）
MoneyDJ 每檔頁面同一時間只揭露「一個」最新資料日期。所以：
- **第 1 天**跑 → 每檔只有一個快照 → 無法比對（diff/共同榜為空）。
- **第 2 個交易日**再跑 → 出現新的資料日期 → 自動以「最新兩天」比對 → 產生**真實異動**。

因此本系統的價值來自**每天累積快照**，建議每個交易日收盤後固定手動跑一次（下一節）。

---

## 7. 每日資料更新（手動執行）
本專案**不使用背景排程**，於每個交易日收盤後手動跑一次即可：
```bash
cd ~/ActiveEtfTracker          # 改成你 clone 的專案路徑
scripts/daily_run.sh            # 啟用 venv → 跑 run → 資料驗證
scripts/daily_run.sh --limit 5  # 測試
tail -f data/daily_run.log      # 看執行紀錄
```
也可直接用前端「更新資料」按鈕觸發一次完整更新（見第 5 節）。

> ℹ️ **為何不用 launchd / cron？** 早期曾排程於交易日 18:00 自動跑，但專案放在 `~/Desktop`
> 等 macOS 隱私保護（TCC）目錄時，launchd 背景程序無權存取，排程會以
> `Operation not permitted`（結束碼 126）失敗。改為手動執行後此限制不再適用
> （互動式 Terminal session 有完整權限），專案因此可放在 `~/Desktop/Project/` 下。

---

## 8. 驗證資料正確性
`daily_run.sh` 跑完會自動驗證；也可手動執行：
```bash
python scripts/verify_run.py        # 報告寫到 data/verify_report.txt
```
檢查：ETF 檔數、資料日期是否推進、各檔持股數/權重總和合理性、負股數/重複代號/缺名稱、可比對檔數、異動分佈。
（註：持有期貨/選擇權的 ETF 權重總和會 >100%，屬正常，腳本已會識別。）

---

## 9. 常見問題（Troubleshooting）

| 症狀 | 原因 / 解法 |
|---|---|
| `playwright` 找不到瀏覽器 | 沒跑 `playwright install chromium`，補跑即可 |
| MoneyDJ SSL 憑證錯誤 | 已用 Playwright `ignore_https_errors` 解決；勿改用純 requests 抓 MoneyDJ |
| `ModuleNotFoundError: active_etf_tracker` | 忘了 `export PYTHONPATH=src`（或改用 `pip install -e .`） |
| diff / 共同榜是空的 | 正常：該 ETF 還只有一個資料日期，明日再跑即可（見第 6 節）。要先預覽用第 5 節 |
| 儀表板顯示「無法載入 data.json」 | 需經由伺服器開啟：用 `dashboard --serve`，不要直接雙擊 index.html |
| 抓取很慢 | 27 檔逐一用瀏覽器渲染，約數分鐘屬正常；`--sleep` 控制每檔間隔 |
| 只顯示部分 ETF | 前端只顯示「已有持股快照」的 ETF；跑過 `fetch`（或 `run`）即會補齊 |

---

## 10. 給 AI 模型的快速指引

**技術棧**：Python（Playwright + BeautifulSoup 爬蟲、SQLite 儲存、pandas 匯出、原生 JS + ECharts 前端）。

**資料流**：
```
TWSE 清單 → active_etfs 表
MoneyDJ basic0007B（完整持股）→ etf_holdings_snapshot 表（每日快照，不覆蓋）
比對最新兩個 data_date → etf_holdings_diff 表
跨 ETF 聚合 → 共同加碼/減碼
匯出 → CSV / Excel / web/data.json（儀表板）
```

**關鍵設計**：
- 比對鍵 `etf_code + data_date + stock_id`；最有意義的訊號是**持有股數變化**（權重變化可能只是股價漲跌）。
- 持股顯示以**張**為單位（1 張 = 1000 股）。
- 只追蹤股票型 A；債券型 D 在 `parse_list(stock_only=True)` 於源頭排除。
- MoneyDJ `basic0007B` 分頁是純前端 display 切換，整張表已在 DOM，一次解析即完整。

**重要檔案**：
- `src/active_etf_tracker/cli.py`：所有指令入口
- `src/active_etf_tracker/scrapers/`：`twse_list.py`、`moneydj.py`
- `src/active_etf_tracker/services/`：`diff_service.py`（異動分類）、`aggregate.py`（共同加減碼）
- `src/active_etf_tracker/db.py`：SQLite schema 與存取
- `src/active_etf_tracker/web_export.py` + `web/`：前端
- `scripts/`：`daily_run.sh`（每日更新，手動）、`verify_run.py`（驗證）、`seed_demo.py`（示範資料）
- 測試：`python tests/test_diff_service.py`、`python tests/test_aggregate.py`（不需網路）

**最常用指令**：`run`（一鍵全跑）、`dashboard --serve`（看網頁）、`list`（看 DB）、`verify_run.py`（驗證）。

---

## 指令速查
```bash
export PYTHONPATH=src
python -m active_etf_tracker.cli update-list           # 抓 ETF 清單
python -m active_etf_tracker.cli fetch                 # 抓全部完整持股
python -m active_etf_tracker.cli fetch --etf 00981A    # 抓單檔
python -m active_etf_tracker.cli diff                  # 比對
python -m active_etf_tracker.cli common --min-etfs 2   # 共同加減碼
python -m active_etf_tracker.cli export                # 匯出 CSV
python -m active_etf_tracker.cli report                # 匯出 Excel
python -m active_etf_tracker.cli dashboard --serve     # 啟動儀表板
python -m active_etf_tracker.cli run                   # 一鍵全跑
python -m active_etf_tracker.cli list                  # 列出 DB 內 ETF
python scripts/verify_run.py                           # 驗證資料
python scripts/seed_demo.py [--clean]                  # 示範資料 / 還原
```

更多細節見 [README.md](README.md) 與 [docs/data_source_policy.md](docs/data_source_policy.md)。
