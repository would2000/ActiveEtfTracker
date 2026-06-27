# 資料來源政策 (Data Source Policy)

## 使用政策與限制（務必遵守）

1. 本工具僅供**低頻、個人、非商業研究**使用。
2. **不保證**資料的完整性、正確性與即時性；資料可能延遲、缺漏或錯誤。
3. **不提供公開 API**。
4. **不提供批次下載第三方資料**的服務。
5. **不鼓勵、不支援**繞過網站限制、驗證碼、登入牆、付費牆或反爬蟲機制。
6. 若資料來源條款**禁止**抓取、重製、改作或散布，使用者**必須遵守**該等條款。
7. 本 repo **不附帶任何第三方資料授權**；公開 repo 與公開站台**不含**第三方抓取後的完整資料
   （詳見 [open_source_safety.md](open_source_safety.md)、[../NOTICE.md](../NOTICE.md)）。

> 抓取行為已內建禮貌間隔（`--sleep`，預設 1 秒）；請勿用於高頻或大量請求而對來源造成負擔。

## 抓取優先順序
| 優先級 | 來源 | 用途 | 狀態 |
|---|---|---|---|
| 1 | TWSE 主動式 ETF 清單 | 取得 ETF universe | ✅ 已實作 |
| 2 | MoneyDJ「查看全部持股」(basic0007B) | **完整**持股 + 資料日期 | ✅ 已實作（預設來源）|
| - | MoneyDJ 概覽頁 (basic0007) | 前十大持股 | ✅ 保留為備援 |
| 3 | 投信官網 / PCF | 官方完整持股交叉驗證 | ⬜ 第二階段 |

## 來源細節

### 1. TWSE 主動式 ETF 清單
- URL：`https://www.twse.com.tw/zh/products/securities/etf/products/active-list.html`
- 表格為 **JavaScript 動態渲染** → 用 Playwright 渲染後解析。
- 兩欄：`證券代號 / 證券簡稱`。
- **代號規則**：第六碼 `A` = 股票型主動式 ETF、`D` = 債券型。
- **範圍**：只保留**股票型 A**；解析時即在源頭濾掉債券型 D（`parse_list(stock_only=True)`），
  D 不寫入 DB、不抓持股。已知 D：00982D、00983D、00984D。

### 2. MoneyDJ 完整持股明細（basic0007B）
- URL 規則：`https://www.moneydj.com/etf/x/basic/basic0007b.xdjhtm?etfid={代號小寫}.tw`
- **憑證問題**：MoneyDJ 伺服器憑證缺 Subject Key Identifier，純 HttpClient 會 SSL 失敗
  → 用 Playwright `ignore_https_errors=True` 渲染。
- 解析欄位：`資料日期`、`個股名稱(代號.TW)`、`投資比例(%)`、`持有股數`。
- **完整持股關鍵**：此頁「頁次 1/N」的分頁是**純前端 `display` 切換**，
  JS 把整張 `.datalist` 全部列載入 DOM（每頁僅顯示 20 列）。BeautifulSoup 忽略
  CSS display，故一次解析整張表即得完整清單，**不需逐頁點選**。
- 完整性檢查：列數應落在 `((N-1)×20, N×20]`；不符則標記可能未完整載入。
- basic0007（概覽頁，前十大）保留為備援：`config.moneydj_url(code, full=False)`。

## 資料正規化
- 資料日期：`YYYY/MM/DD` → 統一存 `YYYY-MM-DD`。
- 股數 / 比例：去除千分位逗號與 `%` 後轉 float。
- 個股代號：由 `台積電(2330.TW)` 拆出 `name=台積電`、`stock_id=2330`；上櫃為 `.TWO`。
  無代號項目（現金 / 其他）以名稱當 `stock_id` 保留。
- `raw_hash`：每列原始值的 SHA256 前 16 碼，供日後偵測來源資料變動。

## 快照原則
- **每日快照，不覆蓋**：同一 `(etf_code, data_date, stock_id, source_name)` 視為同一筆（Upsert）。
- 不同 `data_date` 各自獨立保存，異動比對才有歷史。

## 異動判斷原則
以**持有股數變化**為主（最接近實際買賣）；權重變化僅在股數不變時參考（可能只是股價漲跌）。

| 異動類型 | 判斷 |
|---|---|
| 新增持股 | 昨無、今有 |
| 出清持股 | 昨有、今無 |
| 加碼 | 今股數 > 昨股數 |
| 減碼 | 今股數 < 昨股數 |
| 權重上升 / 下降 | 股數不變、權重變動 |
| 無異動 | 股數與權重皆同 |

## 禮貌抓取
- 每檔之間 `--sleep`（預設 1 秒）間隔，避免對來源造成壓力。
- 渲染後 HTML 落地保存於 `data/raw/`，利於重跑與除錯，減少重複請求。
- 僅供研究／個人使用；如需正式或商用，請確認各來源服務條款。
