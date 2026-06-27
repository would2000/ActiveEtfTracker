# NOTICE — 授權範圍說明

本檔說明本專案各部分的授權與權利歸屬，釐清「哪些受本專案授權涵蓋、哪些不涵蓋」。

## 本專案授權涵蓋

| 項目 | 授權 |
|---|---|
| 原始碼（`src/`、`scripts/`、`web/app.js`、`web/index.html`、`web/styles.css`） | CC BY-NC 4.0（見 [LICENSE](LICENSE)） |
| 文件（`README.md`、`SETUP.md`、`docs/`） | CC BY-NC 4.0 |
| 範例假資料（`examples/sample_data.json`） | CC BY-NC 4.0；內容為**虛構**，非真實 ETF/個股資料 |

> 著作權人 **TraderXiao**，2026。  
> 本專案採非商業授權，屬於 source-available / non-commercial research project。
> 由於授權限制商業使用，因此嚴格來說不屬於 OSI 定義的 open-source license。

## 不在本專案授權範圍

- **第三方抓取資料**：來自 TWSE、MoneyDJ、投信官網等之 ETF 清單、持股明細、權重、
  資料日期等內容，其著作權與相關權利歸**原資料來源所有**。
  本專案**不主張**任何權利，**不附帶**任何第三方資料授權，且公開 repo **不含**此類資料
  （`web/data.json`、`data/raw/`、`data/sqlite/`、`data/exports/`、CSV/XLSX 等）。
- 使用者自行產生／取得的資料，其使用須遵守各來源之服務條款。

## 第三方元件

| 元件 | 版本 | 授權 | 取得方式 |
|---|---|---|---|
| Apache ECharts | 5.5.0 | Apache License 2.0 | 由 jsdelivr CDN 載入（`web/index.html`，含 SRI 完整性雜湊）；可改為本地 `web/vendor/` 自管 |
| Playwright | >=1.40 | Apache License 2.0 | pip（`requirements.txt`） |
| BeautifulSoup4 / lxml / pandas / openpyxl | 見 `requirements.txt` | 各自開源授權 | pip |

各第三方元件之著作權歸其作者所有，使用須遵守其各自授權條款。
