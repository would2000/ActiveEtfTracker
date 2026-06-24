"""持股異動比對單元測試（不需網路）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from active_etf_tracker.models import (  # noqa: E402
    CHANGE_ADD, CHANGE_NEW, CHANGE_REDUCE, CHANGE_REMOVED,
    CHANGE_WEIGHT_DOWN, CHANGE_WEIGHT_UP, HoldingSnapshot,
)
from active_etf_tracker.services import diff_service  # noqa: E402


def snap(stock_id, name, weight, shares):
    return HoldingSnapshot(
        etf_code="00981A", data_date="2026-06-23", stock_id=stock_id,
        stock_name=name, weight_pct=weight, shares=shares, source_name="moneydj",
    )


def run(prev, curr):
    diffs = diff_service.compute_diffs(
        "00981A", "2026-06-22", "2026-06-23", prev, curr, created_at="t",
        include_unchanged=True,
    )
    return {d.stock_id: d for d in diffs}


def test_change_types():
    prev = [
        snap("2330", "台積電", 10.0, 11_800_000),   # 加碼
        snap("2454", "聯發科", 7.0, 5_000_000),      # 減碼
        snap("6415", "矽力*-KY", 0.45, 120_000),     # 出清
        snap("2345", "智邦", 5.0, 6_000_000),        # 股數不變、權重上升
        snap("2383", "台光電", 8.0, 4_000_000),      # 股數不變、權重下降
    ]
    curr = [
        snap("2330", "台積電", 10.13, 11_960_000),   # 加碼
        snap("2454", "聯發科", 6.5, 4_900_000),      # 減碼
        snap("2317", "鴻海", 0.77, 500_000),         # 新增
        snap("2345", "智邦", 5.2, 6_000_000),        # 權重上升
        snap("2383", "台光電", 7.5, 4_000_000),      # 權重下降
    ]
    d = run(prev, curr)
    assert d["2330"].change_type == CHANGE_ADD
    assert d["2330"].shares_diff == 160_000
    assert d["2454"].change_type == CHANGE_REDUCE
    assert d["2317"].change_type == CHANGE_NEW
    assert d["2317"].old_shares is None and d["2317"].new_shares == 500_000
    assert d["6415"].change_type == CHANGE_REMOVED
    assert d["6415"].new_shares is None
    assert d["2345"].change_type == CHANGE_WEIGHT_UP
    assert d["2383"].change_type == CHANGE_WEIGHT_DOWN


if __name__ == "__main__":
    test_change_types()
    print("OK")
