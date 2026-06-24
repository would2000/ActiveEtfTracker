"""資料模型 (dataclasses)，對應規格中的三張表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 異動類型常數
CHANGE_NEW = "新增持股"        # 昨天沒有、今天有
CHANGE_REMOVED = "出清持股"    # 昨天有、今天沒有
CHANGE_ADD = "加碼"           # 今天股數 > 昨天股數
CHANGE_REDUCE = "減碼"        # 今天股數 < 昨天股數
CHANGE_WEIGHT_UP = "權重上升"  # 股數不變，但權重上升
CHANGE_WEIGHT_DOWN = "權重下降"  # 股數不變，但權重下降
CHANGE_NONE = "無異動"        # 股數與權重都相同


@dataclass
class ActiveEtf:
    """主動式 ETF 清單項目。"""
    etf_code: str
    etf_name: str
    etf_type: Optional[str] = None       # "stock" (第六碼 A) / "bond" (第六碼 D)
    issuer: Optional[str] = None
    twse_url: Optional[str] = None
    moneydj_url: Optional[str] = None
    is_active: int = 1
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None


@dataclass
class HoldingSnapshot:
    """單筆每日持股快照。比對鍵：etf_code + data_date + stock_id。"""
    etf_code: str
    data_date: str           # YYYY-MM-DD
    stock_id: str
    stock_name: str
    weight_pct: Optional[float] = None
    shares: Optional[float] = None
    source_name: str = "moneydj"
    source_url: str = ""
    fetched_at: str = ""
    raw_hash: Optional[str] = None


@dataclass
class HoldingDiff:
    """兩個資料日期之間的持股異動。"""
    etf_code: str
    from_date: str
    to_date: str
    stock_id: str
    stock_name: Optional[str]
    change_type: str
    old_weight_pct: Optional[float] = None
    new_weight_pct: Optional[float] = None
    weight_diff_pct: Optional[float] = None
    old_shares: Optional[float] = None
    new_shares: Optional[float] = None
    shares_diff: Optional[float] = None
    source_name: Optional[str] = None
    created_at: str = ""
