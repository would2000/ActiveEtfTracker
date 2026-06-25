"""跨 ETF 聚合：多檔主動式 ETF 共同加碼 / 共同減碼清單。

對每檔 ETF 取「最新兩個資料日期」算出異動，再以 stock_id 跨 ETF 聚合：
  - 共同加碼：change_type ∈ {加碼, 新增持股}
  - 共同減碼：change_type ∈ {減碼, 出清持股}
列出有 ≥ min_etfs 檔同向操作的個股，並彙總參與 ETF 與股數變化總和。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..db import SqliteRepository
from ..models import (
    CHANGE_ADD,
    CHANGE_NEW,
    CHANGE_REDUCE,
    CHANGE_REMOVED,
    HoldingDiff,
)
from .diff_service import compute_latest_diffs

ADD_TYPES = {CHANGE_ADD, CHANGE_NEW}
REDUCE_TYPES = {CHANGE_REDUCE, CHANGE_REMOVED}


@dataclass
class EtfMove:
    """單一 ETF 對某股的操作。"""
    etf_code: str
    change_type: str
    shares_diff: Optional[float]
    weight_diff_pct: Optional[float]
    from_date: str
    to_date: str


@dataclass
class CommonMove:
    """某股在多檔 ETF 的共同操作彙總。"""
    stock_id: str
    stock_name: Optional[str]
    direction: str              # "加碼" / "減碼"
    etf_count: int
    etf_codes: list[str]
    total_shares_diff: float
    moves: list[EtfMove] = field(default_factory=list)


def common_moves(
    repo: SqliteRepository,
    etf_codes: Iterable[str],
    direction: str,
    created_at: str,
    min_etfs: int = 2,
    diffs_by_code: Optional[dict[str, list[HoldingDiff]]] = None,
) -> list[CommonMove]:
    """計算共同加碼 (direction='add') 或共同減碼 (direction='reduce') 清單。

    diffs_by_code 若提供，直接使用已算好的「每檔 ETF 最新兩日異動」，避免重撈
    快照、重算 diff（共同加碼/減碼兩個方向、以及 web_export 的每檔異動可共用同一份）。
    未提供時則自行即時計算（CLI common 指令、單元測試走此路徑）。
    """
    types = ADD_TYPES if direction == "add" else REDUCE_TYPES
    label = "加碼" if direction == "add" else "減碼"

    # stock_id -> 聚合
    bucket: dict[str, CommonMove] = {}
    for code in etf_codes:
        diffs = (diffs_by_code.get(code, []) if diffs_by_code is not None
                 else compute_latest_diffs(repo, code, created_at))
        for d in diffs:
            if d.change_type not in types:
                continue
            cm = bucket.get(d.stock_id)
            if cm is None:
                cm = CommonMove(
                    stock_id=d.stock_id, stock_name=d.stock_name, direction=label,
                    etf_count=0, etf_codes=[], total_shares_diff=0.0, moves=[],
                )
                bucket[d.stock_id] = cm
            cm.etf_codes.append(code)
            cm.etf_count += 1
            cm.total_shares_diff += d.shares_diff or 0.0
            if not cm.stock_name:
                cm.stock_name = d.stock_name
            cm.moves.append(EtfMove(
                etf_code=code, change_type=d.change_type, shares_diff=d.shares_diff,
                weight_diff_pct=d.weight_diff_pct, from_date=d.from_date, to_date=d.to_date,
            ))

    result = [cm for cm in bucket.values() if cm.etf_count >= min_etfs]
    # 參與 ETF 數多者優先，其次股數變化幅度大者
    result.sort(key=lambda c: (-c.etf_count, -abs(c.total_shares_diff)))
    return result
