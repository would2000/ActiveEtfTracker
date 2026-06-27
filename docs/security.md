# 前端安全說明 (Frontend Security)

公開站台為純靜態頁，無後端、無登入、無使用者輸入儲存。以下記錄已處理的風險與現況。

## 1. XSS（跨站腳本）— 已處理

前端 `web/app.js` 以 `innerHTML` 組畫面，所有**來自資料檔的欄位**
（ETF 名稱／代號、個股名稱／代號、投信、資料日期、權重、異動類型等）在塞入前
都會經過 `escapeHtml()` 轉義；數字欄位先以 `num()` 轉型再格式化，不直接信任來源字串。
ECharts tooltip 的 HTML formatter 同樣已對資料欄位轉義。

> 維護注意：日後新增任何 `innerHTML` 模板時，資料欄位一律用 `esc(...)`／`escNum(...)`；
> 能用 `textContent` 就優先用 `textContent`。

## 2. CDN 完整性（SRI）— 已處理

`web/index.html` 以 jsdelivr CDN 載入 **ECharts 5.5.0（Apache-2.0）**，已加上
`integrity`（SHA-384 SRI）與 `crossorigin="anonymous"`，避免 CDN 內容遭竄改後被執行。

- 目前雜湊：`sha384-o5uz97et3bErHvpKfD4Jz4n0JfhJDWABFuF4NP+iEEDxE1VwMWJ19QGR0lqFZnr6`
- **升級版本時務必重新產生 SRI**：

  ```bash
  curl -sS https://cdn.jsdelivr.net/npm/echarts@<版本>/dist/echarts.min.js \
    | openssl dgst -sha384 -binary | openssl base64 -A
  ```

- 若要**完全離線／自管**，可改為本地 vendor：下載上述檔案到 `web/vendor/echarts.min.js`，
  將 `index.html` 改為 `<script src="vendor/echarts.min.js"></script>`，並在 [NOTICE.md](../NOTICE.md)
  記錄來源與版本。（目前選擇 CDN + SRI，repo 不必夾帶 ~1MB 第三方檔。）

## 3. 更新 API（本機限定）

`/api/update`、`/api/status` 僅存在於本機 `dashboard --serve`，含伺服器端 30 分鐘冷卻。
公開靜態站台不含此後端，前端偵測不到 `/api/status` 時會自動隱藏「更新資料」按鈕。

## 待處理 / 已知風險

- 目前無已知未處理項。日後若引入新的第三方 CDN 資源，需比照加上 SRI 或改本地 vendor。
