"""跨 ETF 共同加碼/減碼聚合測試（用暫存 SQLite，不需網路）。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from active_etf_tracker.db import SqliteRepository  # noqa: E402
from active_etf_tracker.models import HoldingSnapshot  # noqa: E402
from active_etf_tracker.services import aggregate  # noqa: E402


def snap(etf, date, sid, name, shares, weight=1.0):
    return HoldingSnapshot(etf_code=etf, data_date=date, stock_id=sid, stock_name=name,
                           weight_pct=weight, shares=shares, source_name="moneydj")


def _repo():
    tmp = Path(tempfile.mkdtemp()) / "t.sqlite"
    return SqliteRepository(db_path=tmp)


def test_common_moves():
    repo = _repo()
    prev, today = "2026-06-20", "2026-06-23"
    rows = []
    for etf in ("00980A", "00981A", "00982A"):
        # 昨天
        rows += [snap(etf, prev, "2330", "台積電", 1_000_000),
                 snap(etf, prev, "2454", "聯發科", 1_000_000)]
        # 今天：2330 三檔都加碼、2454 三檔都減碼、3017 兩檔新增
        rows += [snap(etf, today, "2330", "台積電", 1_100_000),
                 snap(etf, today, "2454", "聯發科", 900_000)]
    # 3017 只在兩檔今天新增
    rows += [snap("00980A", today, "3017", "奇鋐", 500_000),
             snap("00981A", today, "3017", "奇鋐", 300_000)]
    repo.upsert_snapshots(rows)

    codes = ["00980A", "00981A", "00982A"]
    add = {m.stock_id: m for m in aggregate.common_moves(repo, codes, "add", "t", min_etfs=2)}
    red = {m.stock_id: m for m in aggregate.common_moves(repo, codes, "reduce", "t", min_etfs=2)}

    assert add["2330"].etf_count == 3
    assert add["2330"].total_shares_diff == 300_000      # 3 × +100,000
    assert add["3017"].etf_count == 2 and add["3017"].direction == "加碼"
    assert "2454" not in add
    assert red["2454"].etf_count == 3
    assert red["2454"].total_shares_diff == -300_000     # 3 × -100,000
    assert "2330" not in red

    # min_etfs=3 時，只在兩檔新增的 3017 應被濾掉
    add3 = {m.stock_id for m in aggregate.common_moves(repo, codes, "add", "t", min_etfs=3)}
    assert "3017" not in add3 and "2330" in add3


if __name__ == "__main__":
    test_common_moves()
    print("OK")
