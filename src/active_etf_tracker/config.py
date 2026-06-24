"""集中設定：路徑、來源 URL 規則、常數。"""
from __future__ import annotations

from pathlib import Path

# 專案根目錄（此檔案位於 src/active_etf_tracker/config.py，往上三層即根目錄）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SQLITE_DIR = DATA_DIR / "sqlite"
EXPORTS_DIR = DATA_DIR / "exports"

DB_PATH = SQLITE_DIR / "active_etf.sqlite"

# 資料來源
TWSE_ACTIVE_LIST_URL = (
    "https://www.twse.com.tw/zh/products/securities/etf/products/active-list.html"
)

# MoneyDJ 持股頁 URL 規則：代號需小寫 + ".tw"
# basic0007  = 前十大持股（概覽）
# basic0007B = 完整持股（「查看全部持股」頁；分頁為純前端 display 切換，
#              所有列其實都已在 DOM 中，一次抓取即可取得完整清單）
# 例：00981A → https://www.moneydj.com/etf/x/basic/basic0007b.xdjhtm?etfid=00981a.tw
MONEYDJ_TOP10_URL = "https://www.moneydj.com/etf/x/basic/basic0007.xdjhtm?etfid={etfid}.tw"
MONEYDJ_FULL_URL = "https://www.moneydj.com/etf/x/basic/basic0007b.xdjhtm?etfid={etfid}.tw"
# 預設用完整持股頁
MONEYDJ_HOLDING_URL = MONEYDJ_FULL_URL

SOURCE_MONEYDJ = "moneydj"
SOURCE_ISSUER = "issuer"
SOURCE_PCF = "pcf"


def moneydj_url(etf_code: str, full: bool = True) -> str:
    """由 ETF 代號產生 MoneyDJ 持股頁 URL。full=True 為完整持股頁 (basic0007B)。"""
    tmpl = MONEYDJ_FULL_URL if full else MONEYDJ_TOP10_URL
    return tmpl.format(etfid=etf_code.strip().lower())


def ensure_dirs() -> None:
    """確保所有資料目錄存在。"""
    for d in (RAW_DIR, SQLITE_DIR, EXPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
