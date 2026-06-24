"""產生「前一交易日」示範快照，讓儀表板在累積真實多日資料前也能預覽完整 UI。

用途：第一天只有一個資料日期時，diff / 共同加減碼都是空的。此腳本會依現有最新
快照，造一個確定性擾動的前一日快照（預設日期 2026-06-20），方便預覽前端。

  python scripts/seed_demo.py          # 寫入示範前一日 + 匯出 data.json
  python scripts/seed_demo.py --clean  # 移除示範資料（還原為真實狀態）

注意：這是「示範資料」，非真實持股。正式使用時，連續兩個交易日各跑一次
`fetch` 即可得到真實異動，再跑 `dashboard` 即可。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from active_etf_tracker import config, web_export  # noqa: E402
from active_etf_tracker.db import SqliteRepository  # noqa: E402

DEMO_PREV = "2026-06-20"


def _rng(seed: str) -> float:
    return (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 1000) / 1000.0


def seed() -> None:
    repo = SqliteRepository()
    c = sqlite3.connect(config.DB_PATH)
    etfs = [r[0] for r in c.execute("SELECT DISTINCT etf_code FROM etf_holdings_snapshot")]
    c.execute("DELETE FROM etf_holdings_snapshot WHERE data_date=?", (DEMO_PREV,))
    c.commit()
    c.close()
    for code in etfs:
        dates = repo.get_data_dates(code)
        if not dates:
            continue
        curr = repo.get_holdings(code, dates[0])
        rows = []
        for idx, h in enumerate(curr):
            r = _rng(f"{code}{h.stock_id}")
            if r < 0.12 and idx > 3:        # 約 12% 視為今天新增（昨天沒有）
                continue
            s = copy.copy(h)
            s.data_date = DEMO_PREV
            if h.shares:
                s.shares = round(h.shares * (1 + (r - 0.5) * 0.16))  # ±8% 擾動當昨天值
            rows.append(s)
        repo.upsert_snapshots(rows)
    print(f"已寫入示範前一日快照（{DEMO_PREV}），ETF {len(etfs)} 檔")
    path = web_export.export_dashboard_data(repo)
    print(f"已匯出 → {path}")


def clean() -> None:
    c = sqlite3.connect(config.DB_PATH)
    c.execute("DELETE FROM etf_holdings_snapshot WHERE data_date=?", (DEMO_PREV,))
    c.commit()
    c.close()
    print(f"已移除示範資料（{DEMO_PREV}）")
    path = web_export.export_dashboard_data()
    print(f"已重新匯出 → {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    clean() if a.clean else seed()
