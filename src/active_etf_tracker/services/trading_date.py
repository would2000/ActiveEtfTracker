"""資料日期工具：取「最新」與「上一個」資料日期。

本專案的比對不依賴交易日曆，而是直接用 DB 中實際存在的資料日期，
因此「上一個資料日期」= 已落地快照中、比最新日期更早的最近一天。
"""
from __future__ import annotations

from typing import Optional

from ..db import SqliteRepository


def latest_two_dates(repo: SqliteRepository, etf_code: str) -> tuple[Optional[str], Optional[str]]:
    """回傳 (previous_date, latest_date)。不足兩天時 previous 為 None。"""
    dates = repo.get_data_dates(etf_code)  # 新→舊
    if not dates:
        return None, None
    if len(dates) == 1:
        return None, dates[0]
    return dates[1], dates[0]
