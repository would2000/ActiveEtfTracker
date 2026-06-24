"""Playwright 抓取共用工具。

TWSE 與 MoneyDJ 的表格皆為 JavaScript 動態渲染，且 MoneyDJ 憑證有問題，
因此統一用 Chromium (ignore_https_errors) 渲染後再取 HTML。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_html(
    url: str,
    *,
    wait_ms: int = 3500,
    timeout_ms: int = 45000,
    wait_for_selector: Optional[str] = None,
    save_raw_to: Optional[Path] = None,
) -> str:
    """以 Chromium 渲染頁面並回傳 HTML。

    wait_for_selector 若提供，會等待該 selector 出現（比固定等待更穩）。
    save_raw_to 若提供，會把渲染後的 HTML 落地保存（data/raw 用）。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(ignore_https_errors=True, user_agent=DEFAULT_UA)
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
                except Exception:
                    pass  # 落到固定等待
            page.wait_for_timeout(wait_ms)
            html = page.content()
        finally:
            browser.close()

    if save_raw_to:
        save_raw_to.parent.mkdir(parents=True, exist_ok=True)
        save_raw_to.write_text(html, encoding="utf-8")
    return html


def today_iso() -> str:
    """本機今天日期 YYYY-MM-DD。"""
    return time.strftime("%Y-%m-%d", time.localtime())


def now_iso() -> str:
    """本機現在時間 ISO8601（秒）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
