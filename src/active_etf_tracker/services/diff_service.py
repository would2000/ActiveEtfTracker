"""持股異動比對核心。

以 stock_id 做 FULL OUTER JOIN，比較兩個資料日期的持股快照。
判斷優先以「持有股數變化」為主（最接近實際買賣），權重變化僅在股數不變時參考。
"""
from __future__ import annotations

from typing import Iterable, Optional

from ..models import (
    CHANGE_ADD,
    CHANGE_NEW,
    CHANGE_NONE,
    CHANGE_REDUCE,
    CHANGE_REMOVED,
    CHANGE_WEIGHT_DOWN,
    CHANGE_WEIGHT_UP,
    HoldingDiff,
    HoldingSnapshot,
)


def _classify(old: Optional[HoldingSnapshot], new: Optional[HoldingSnapshot]) -> str:
    """依規格第五節判斷異動類型。"""
    old_sh = old.shares if old else None
    new_sh = new.shares if new else None

    if old is None and new is not None:
        return CHANGE_NEW
    if old is not None and new is None:
        return CHANGE_REMOVED

    # 兩天都有：先看股數
    o = old_sh or 0.0
    n = new_sh or 0.0
    if n > o:
        return CHANGE_ADD
    if n < o:
        return CHANGE_REDUCE

    # 股數相同：看權重
    ow = (old.weight_pct if old else None) or 0.0
    nw = (new.weight_pct if new else None) or 0.0
    if nw > ow:
        return CHANGE_WEIGHT_UP
    if nw < ow:
        return CHANGE_WEIGHT_DOWN
    return CHANGE_NONE


def _diff(a: Optional[float], b: Optional[float], ndigits: int = 6) -> Optional[float]:
    if a is None and b is None:
        return None
    return round((b or 0.0) - (a or 0.0), ndigits)


def compute_diffs(
    etf_code: str,
    from_date: str,
    to_date: str,
    prev_holdings: Iterable[HoldingSnapshot],
    curr_holdings: Iterable[HoldingSnapshot],
    created_at: str,
    include_unchanged: bool = False,
) -> list[HoldingDiff]:
    """比較兩個資料日期，產生異動清單。"""
    prev = {h.stock_id: h for h in prev_holdings}
    curr = {h.stock_id: h for h in curr_holdings}
    source = next(iter(curr.values())).source_name if curr else (
        next(iter(prev.values())).source_name if prev else None
    )

    diffs: list[HoldingDiff] = []
    for sid in prev.keys() | curr.keys():
        o = prev.get(sid)
        n = curr.get(sid)
        change = _classify(o, n)
        if change == CHANGE_NONE and not include_unchanged:
            continue
        diffs.append(
            HoldingDiff(
                etf_code=etf_code,
                from_date=from_date,
                to_date=to_date,
                stock_id=sid,
                stock_name=(n.stock_name if n else (o.stock_name if o else None)),
                change_type=change,
                old_weight_pct=o.weight_pct if o else None,
                new_weight_pct=n.weight_pct if n else None,
                weight_diff_pct=_diff(o.weight_pct if o else None, n.weight_pct if n else None),
                old_shares=o.shares if o else None,
                new_shares=n.shares if n else None,
                shares_diff=_diff(o.shares if o else None, n.shares if n else None),
                source_name=source,
                created_at=created_at,
            )
        )

    # 排序：異動類型分組，再依股數變化幅度（大→小）
    order = {
        CHANGE_NEW: 0, CHANGE_ADD: 1, CHANGE_REDUCE: 2, CHANGE_REMOVED: 3,
        CHANGE_WEIGHT_UP: 4, CHANGE_WEIGHT_DOWN: 5, CHANGE_NONE: 6,
    }
    diffs.sort(key=lambda d: (order.get(d.change_type, 9), -abs(d.shares_diff or 0.0)))
    return diffs


def compute_latest_diffs(repo, etf_code: str, created_at: str,
                         include_unchanged: bool = False) -> list[HoldingDiff]:
    """取單檔 ETF「最新兩個資料日期」的異動（即時計算，唯一真相來源）。

    不足兩個資料日期時回傳空清單。被 aggregate / web_export / cli export 共用，
    避免各處各自重撈快照、重算 diff。
    """
    from .trading_date import latest_two_dates  # 延遲匯入避免模組載入順序問題

    prev_date, latest = latest_two_dates(repo, etf_code)
    if not prev_date or not latest:
        return []
    prev = repo.get_holdings(etf_code, prev_date)
    curr = repo.get_holdings(etf_code, latest)
    return compute_diffs(etf_code, prev_date, latest, prev, curr, created_at,
                         include_unchanged=include_unchanged)
