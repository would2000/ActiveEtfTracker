"""TWSE 主動式 ETF 清單爬蟲。

來源頁面為 JavaScript 動態渲染的兩欄表格：證券代號 / 證券簡稱。
第六碼 A → 股票型 (stock)、D → 債券型 (bond)。
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import config
from ..models import ActiveEtf
from .base import fetch_html, now_iso

# 主動式 ETF 代號格式：5 碼數字 + 1 碼英文（A/D...）
ETF_CODE_RE = re.compile(r"^\d{5}[A-Z]$")

# 由簡稱粗略推測投信（issuer），僅供第一版參考
ISSUER_KEYWORDS = {
    "統一": "統一投信", "群益": "群益投信", "野村": "野村投信", "中信": "中國信託投信",
    "復華": "復華投信", "元大": "元大投信", "富邦": "富邦投信", "國泰": "國泰投信",
    "新光": "新光投信", "凱基": "凱基投信", "兆豐": "兆豐投信", "第一金": "第一金投信",
    "永豐": "永豐投信", "安聯": "安聯投信", "保德信": "保德信投信", "日盛": "日盛投信",
    "台新": "台新投信", "華南永昌": "華南永昌投信", "PGIM": "保德信投信",
}


def classify_etf_type(etf_code: str) -> str | None:
    """依第六碼分類：A→stock、D→bond，其餘→None。"""
    if len(etf_code) < 6:
        return None
    c = etf_code[5].upper()
    if c == "A":
        return "stock"
    if c == "D":
        return "bond"
    return None


def guess_issuer(etf_name: str) -> str | None:
    for kw, issuer in ISSUER_KEYWORDS.items():
        if kw in etf_name:
            return issuer
    return None


def parse_list(html: str, stock_only: bool = True) -> list[ActiveEtf]:
    """從 TWSE 清單頁 HTML 解析出 ETF 清單。

    stock_only=True（預設）只保留股票型（第六碼 A）；債券型 D 等不納入，
    從源頭就排除，不會寫入 DB、也不會抓持股。
    """
    soup = BeautifulSoup(html, "lxml")
    ts = now_iso()
    out: list[ActiveEtf] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            code = cells[0].upper()
            name = cells[1]
            if not ETF_CODE_RE.match(code) or code in seen:
                continue
            etf_type = classify_etf_type(code)
            if stock_only and etf_type != "stock":
                continue  # 債券型 D 等：源頭排除，不抓
            seen.add(code)
            out.append(
                ActiveEtf(
                    etf_code=code,
                    etf_name=name,
                    etf_type=etf_type,
                    issuer=guess_issuer(name),
                    twse_url=config.TWSE_ACTIVE_LIST_URL,
                    moneydj_url=config.moneydj_url(code),
                    is_active=1,
                    first_seen_at=ts,
                    last_seen_at=ts,
                )
            )
    return out


def scrape_active_etfs(save_raw_to=None, stock_only: bool = True) -> list[ActiveEtf]:
    """抓取並解析 TWSE 主動式 ETF 清單（預設只保留股票型 A）。"""
    html = fetch_html(
        config.TWSE_ACTIVE_LIST_URL,
        wait_for_selector="table",
        save_raw_to=save_raw_to,
    )
    return parse_list(html, stock_only=stock_only)
