"""MoneyDJ 持股明細爬蟲。

預設使用「查看全部持股」頁 (basic0007B)，可取得**完整**持股清單。

頁面結構：
  - 文字「資料日期：YYYY/MM/DD」
  - table.datalist，表頭：個股名稱 / 投資比例(%) / 持有股數
  - 個股名稱格式：「台積電(2330.TW)」、上櫃為 .TWO
  - 文字「頁次：1/N」表示前端分頁數（每頁 20 列）

重要：basic0007B 的分頁是**純前端 display 切換**——所有持股列在首次載入時
即全部存在於 .datalist 的 DOM 中，JS 只是 hide/show 每頁 20 列。因此用
BeautifulSoup（忽略 CSS display）解析整張表，一次抓取即可拿到完整清單，
不需逐頁點選。會以「頁次 N」做完整性檢查（列數應 ≤ N×20 且 > (N-1)×20）。
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from bs4 import BeautifulSoup

from .. import config
from ..models import HoldingSnapshot
from .base import fetch_html, now_iso

DATA_DATE_RE = re.compile(r"資料日期[:：]\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})")
PAGE_COUNT_RE = re.compile(r"頁次[:：]\s*\d+\s*/\s*(\d+)")
PAGE_SIZE = 20  # basic0007B 每頁 20 列
# 「個股名稱(代號.TW)」或「(代號.TWO)」；代號可能含英文（KY 股等）
STOCK_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<id>[0-9A-Za-z]+)\.(?:TW|TWO)\)\s*$")


def _to_float(text: str) -> Optional[float]:
    t = (text or "").replace(",", "").replace("%", "").strip()
    if not t or t in {"-", "--", "N/A"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_data_date(html: str) -> Optional[str]:
    """解析「資料日期」並正規化為 YYYY-MM-DD。"""
    soup = BeautifulSoup(html, "lxml")
    m = DATA_DATE_RE.search(soup.get_text())
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _split_name_id(raw: str) -> tuple[str, str]:
    """從「台積電(2330.TW)」拆出 (name, stock_id)。無法解析時 id 回退為名稱。"""
    m = STOCK_RE.match(raw)
    if m:
        return m.group("name").strip(), m.group("id").upper()
    return raw, raw  # 現金/其他等無代號項目


def parse_page_count(html: str) -> Optional[int]:
    """解析「頁次：1/N」中的 N（前端分頁數，每頁 20 列）。"""
    m = PAGE_COUNT_RE.search(BeautifulSoup(html, "lxml").get_text())
    return int(m.group(1)) if m else None


def _find_holdings_table(soup: BeautifulSoup):
    # 優先 class=datalist，其次以表頭文字判斷
    for table in soup.find_all("table", class_="datalist"):
        if "投資比例" in table.get_text():
            return table
    for table in soup.find_all("table"):
        header = table.find("tr")
        if header and "投資比例" in header.get_text() and (
            "持有股數" in header.get_text() or "個股名稱" in header.get_text()
        ):
            return table
    return None


def parse_holdings(html: str, etf_code: str, source_url: str) -> tuple[Optional[str], list[HoldingSnapshot]]:
    """解析持股明細表，回傳 (data_date, snapshots)。

    basic0007B 的所有持股列皆已在 DOM 中（分頁僅前端 display），故一次解析即完整。
    以 stock_id 去重，保留第一筆（權重最高者排在前）。
    """
    data_date = parse_data_date(html)
    soup = BeautifulSoup(html, "lxml")
    fetched_at = now_iso()
    snaps: list[HoldingSnapshot] = []
    seen: set[str] = set()

    target = _find_holdings_table(soup)
    if target is None:
        return data_date, snaps

    for tr in target.find_all("tr")[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3 or not cells[0]:
            continue
        name, stock_id = _split_name_id(cells[0])
        if stock_id in seen:
            continue
        seen.add(stock_id)
        weight = _to_float(cells[1])
        shares = _to_float(cells[2])
        raw = f"{etf_code}|{data_date}|{stock_id}|{name}|{weight}|{shares}"
        snaps.append(
            HoldingSnapshot(
                etf_code=etf_code,
                data_date=data_date or "",
                stock_id=stock_id,
                stock_name=name,
                weight_pct=weight,
                shares=shares,
                source_name=config.SOURCE_MONEYDJ,
                source_url=source_url,
                fetched_at=fetched_at,
                raw_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
            )
        )
    return data_date, snaps


def completeness_ok(n_rows: int, page_count: Optional[int]) -> bool:
    """以頁次數驗證完整性：列數應落在 ((N-1)*20, N*20]。無頁次資訊則視為 OK。"""
    if not page_count:
        return True
    return (page_count - 1) * PAGE_SIZE < n_rows <= page_count * PAGE_SIZE


def scrape_holdings(etf_code: str, save_raw_to=None) -> tuple[Optional[str], list[HoldingSnapshot], Optional[int]]:
    """抓取單檔 ETF 的 MoneyDJ 完整持股明細。

    回傳 (data_date, snapshots, page_count)。page_count 供 CLI 做完整性檢查。
    """
    url = config.moneydj_url(etf_code, full=True)
    html = fetch_html(url, wait_for_selector="table.datalist tbody tr", save_raw_to=save_raw_to)
    data_date, snaps = parse_holdings(html, etf_code, url)
    return data_date, snaps, parse_page_count(html)
