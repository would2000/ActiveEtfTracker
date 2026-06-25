# 主動式 ETF 每日持股異動追蹤系統 (ActiveEtfTracker)

每天抓取台股**股票型主動式 ETF**（證券代號第六碼為 `A`）的持股快照，與前一個資料日期比對，
產出「新增 / 出清 / 加碼 / 減碼 / 權重升降」異動清單，並匯出 CSV / Excel 與互動式儀表板。

> 範圍：僅追蹤**股票型 A**；債券型 D（如 00982D / 00983D / 00984D）已自源頭排除，不抓取、不納入。

> 🚀 **第一次使用？** 請先看 **[SETUP.md 上手指南](SETUP.md)**（從零安裝、執行、看結果、每日更新、疑難排解，並附給 AI 模型的快速指引）。

> 核心不是爬蟲，而是：**同一檔 ETF、不同資料日期的持股快照比對**。
> 比對鍵 = `etf_code + data_date + stock_id`；最有意義的訊號是**持有股數變化**（權重變化可能只是股價漲跌）。

## 技術棧
Python 3.10+ ／ Playwright（Chromium 動態渲染）／ BeautifulSoup ／ SQLite ／ pandas。

> 規格原建議 C#，但本機未安裝 .NET，故以 Python 實作（sqlite3 內建、pandas 處理 CSV/Excel 與比對最直接）。
> 模組結構與規格一一對應，日後要移植 C# 也照得到圖。

## 安裝
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # 安裝瀏覽器（首次必跑）
```

## 使用
所有指令前需 `export PYTHONPATH=src`（或 `pip install -e .` 後直接用 `active-etf`）。

```bash
# 1) 一鍵跑完整流程（清單 → 抓股票型 A 完整持股 → 比對 → 共同加減碼 → CSV + Excel）
python -m active_etf_tracker.cli run --limit 5      # --limit 測試用，省略則全部

# 或分步執行：
python -m active_etf_tracker.cli update-list                  # 抓 TWSE 清單
python -m active_etf_tracker.cli fetch  --etf 00981A,00982A   # 抓指定 ETF 完整持股
python -m active_etf_tracker.cli fetch                        # 抓全部股票型 A
python -m active_etf_tracker.cli diff   --etf 00981A          # 比對最新兩個資料日期
python -m active_etf_tracker.cli common --min-etfs 2          # 多檔 ETF 共同加碼/減碼
python -m active_etf_tracker.cli export --etf 00981A          # 匯出 CSV
python -m active_etf_tracker.cli report                       # 產生單一 Excel 報表
python -m active_etf_tracker.cli list                         # 列出 DB 內 ETF 與資料日期
```

> 第一天只有一個資料日期，`diff` / `common` 會提示「尚無法比對」；**隔天再 `fetch` 一次**即可產生異動。

## 互動式儀表板（前端）
零建置靜態頁（`web/index.html` + 原生 JS + ECharts CDN），三個畫面：
**ETF 清單總覽**、**單檔持股 + 異動**、**共同加碼/減碼榜**。色彩採台股慣例（紅＝加碼/漲、綠＝減碼/跌）。

```bash
python -m active_etf_tracker.cli dashboard --serve   # 匯出 data.json 並開 http://localhost:8000
# 或只匯出資料（部署到 GitHub Pages 等靜態主機）：
python -m active_etf_tracker.cli dashboard
```

### 頁面上的「更新資料」按鈕
`dashboard --serve` 啟動的伺服器附帶更新 API，頁面右上的**「更新資料」按鈕**可直接觸發
一次完整更新（等同 `cli run`），完成後自動刷新畫面。為避免對來源網站造成負擔或被封鎖，
更新有**伺服器端 30 分鐘冷卻**：
- 冷卻期間按鈕顯示倒數「可更新 mm:ss」並停用；後端對重複請求回 `429`。
- 冷卻時間記錄於 `data/.last_update`，**重啟伺服器不會重置**（無法用重新整理或重啟繞過）。
- 部署到無後端的靜態主機（如 GitHub Pages）時，按鈕會**自動隱藏**（偵測不到 `/api/status`）。

> API：`GET /api/status`（狀態/冷卻秒數）、`POST /api/update`（觸發更新，含冷卻檢查）。
> 手動的 `scripts/daily_run.sh` 與此按鈕的冷卻互不影響。

> `web/data.json` 是由 SQLite 產生的資料檔。第一天只有一個資料日期時，異動/共同榜為空；
> 想先預覽完整 UI，可跑 `python scripts/seed_demo.py` 產生示範前一日資料（`--clean` 還原）。

## 每日資料更新（手動執行）
台股收盤後，於交易日跑 `scripts/daily_run.sh`（會自動啟用 venv、跑 `run`，再做資料驗證）：
```bash
cd ~/ActiveEtfTracker          # 改成你 clone 的專案路徑
scripts/daily_run.sh            # 全部股票型 A
scripts/daily_run.sh --limit 5  # 測試
tail -f data/daily_run.log      # 看執行紀錄
```
或直接在前端「立即更新」按鈕觸發（見下方說明）。

> 本系統的價值來自**每天累積快照**，建議交易日收盤後固定手動跑一次。

> ℹ️ **本專案不使用背景排程（launchd / cron）。**
> 早期曾用 launchd 排程，但放在 `~/Desktop` 等 macOS 隱私保護（TCC）目錄時，
> launchd 背景程序無權存取，排程會以 `Operation not permitted`（結束碼 126）失敗。
> 改為手動執行後此限制不再適用（互動式 Terminal session 有完整權限），
> 專案因此可放在 `~/Desktop/Project/` 下。

## 輸出（data/exports/）
```
active_etfs_2026-06-24.csv                 # ETF 清單
holdings_00981A_2026-06-23.csv             # 某檔某日完整持股快照
diff_00981A_2026-06-22_to_2026-06-23.csv   # 兩日異動清單
common_add_2026-06-24.csv                  # 多檔 ETF 共同加碼
common_reduce_2026-06-24.csv               # 多檔 ETF 共同減碼
active_etf_report_2026-06-24.xlsx          # 單一 Excel：清單/最新持股/異動彙總/共同加碼/共同減碼
```

## 專案結構
```
src/active_etf_tracker/
├─ config.py              # 路徑、URL 規則
├─ models.py              # ActiveEtf / HoldingSnapshot / HoldingDiff
├─ db.py                  # SqliteRepository（建表 + Upsert + 查詢）
├─ scrapers/
│  ├─ base.py             # Playwright 抓取共用工具
│  ├─ twse_list.py        # TWSE 主動式 ETF 清單（第六碼 A=stock / D=bond）
│  └─ moneydj.py          # MoneyDJ 持股明細（資料日期 + 個股 + 比例 + 股數）
├─ services/
│  ├─ trading_date.py     # 取最新與上一個資料日期
│  ├─ diff_service.py     # 異動比對核心（以股數變化為主）
│  └─ aggregate.py        # 跨 ETF 共同加碼/減碼聚合
├─ export.py              # CSV / Excel 匯出
├─ web_export.py          # 匯出前端 data.json
└─ cli.py                 # 命令列入口
web/                      # 互動式儀表板（index.html / app.js / styles.css / data.json）
scripts/daily_run.sh      # 每日更新腳本（手動執行）
scripts/seed_demo.py      # 產生示範前一日資料以預覽前端
data/{raw,sqlite,exports} # 原始 HTML / SQLite / 輸出
tests/test_diff_service.py、tests/test_aggregate.py
```

## 完整持股的取得方式
已改用 MoneyDJ **`basic0007B`（查看全部持股）** 頁取得**完整**持股清單。
該頁分頁是純前端 `display` 切換——所有持股列在首次載入時即全部存在於 DOM，
故用 BeautifulSoup（忽略 CSS display）一次解析即取得完整清單，無需逐頁點選。
抓取時以「頁次 N」做完整性檢查（列數應 ≤ N×20）。

## 已知限制 / 下一步
- 各 ETF 在 MoneyDJ 的資料日期可能不同步（有的較舊），比對以該檔自身的最新兩天為準。
- 第二來源（投信官網 / PCF）尚未實作，`source_name` 欄位已預留以利日後交叉驗證。
- 比對 `etf_holdings_diff` PK 為單一 `source_name` 隱含值；若日後多來源並存，diff 需納入來源維度。

詳見 [docs/data_source_policy.md](docs/data_source_policy.md)。

## 免責聲明
本專案為個人技術研究與學習用途，所有內容**僅供參考，不構成任何投資建議、要約或招攬**。
資料可能有延遲、缺漏或錯誤，使用者應自行向官方來源查證。權重變化可能僅反映股價漲跌，
實際買賣應以「持有股數（張數）變化」為準。依本專案資訊所為之任何投資決策與後果，
概由使用者自行承擔，開發者不負任何責任。

## 資料來源
- ETF 清單：[臺灣證券交易所（TWSE）主動式 ETF](https://www.twse.com.tw/zh/products/securities/etf/products/active-list.html)
- 持股明細：[MoneyDJ 理財網](https://www.moneydj.com/etf/)

各項資料之著作權與商標歸原來源所有，本專案不主張任何權利，使用時須遵守各來源之服務條款。

## 使用政策（不得商業使用）
本專案以**非商業（non-commercial）研究目的**釋出，**嚴禁任何商業用途**，
包含但不限於販售、付費訂閱、廣告營利或併入商業產品。轉載或衍生使用須註明出處、
維持非商業性質，並遵守上述資料來源之服務條款。抓取行為已內建禮貌間隔（`--sleep`），
請勿用於高頻或大量請求而對來源造成負擔。

## 授權
著作權人 **TraderXiao**。本專案採 **[CC BY-NC 4.0](LICENSE)**（姓名標示-非商業性）授權，
使用時須標示著作權人 TraderXiao 並維持非商業性質，詳見 [LICENSE](LICENSE)。
第三方資料（TWSE、MoneyDJ）之權利歸原來源所有，不在本授權範圍內。
