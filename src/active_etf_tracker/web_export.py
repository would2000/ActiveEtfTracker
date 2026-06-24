"""把 SQLite 內容匯出成前端儀表板用的單一 data.json。

前端為零建置靜態頁（web/index.html + ECharts CDN），讀此 JSON 渲染三個畫面：
  1. ETF 清單總覽
  2. 單檔 ETF 持股 + 異動
  3. 共同加碼 / 減碼榜
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from . import config
from .db import SqliteRepository
from .scrapers.base import now_iso
from .services import aggregate, diff_service
from .services.trading_date import latest_two_dates

WEB_DIR = config.PROJECT_ROOT / "web"
DATA_JSON = WEB_DIR / "data.json"


def _round(x: Optional[float], n: int = 2) -> Optional[float]:
    return round(x, n) if isinstance(x, (int, float)) else x


def build_payload(repo: SqliteRepository, etf_type: str = "stock", min_etfs: int = 2) -> dict:
    created = now_iso()
    etfs = repo.get_etfs(etf_type=etf_type)
    etf_meta, holdings, diffs = [], {}, {}
    codes = []

    for e in etfs:
        dates = repo.get_data_dates(e.etf_code)
        if not dates:
            continue
        codes.append(e.etf_code)
        latest = dates[0]
        prev_date, _ = latest_two_dates(repo, e.etf_code)
        items = repo.get_holdings(e.etf_code, latest)
        holdings[e.etf_code] = {
            "data_date": latest,
            "items": [
                {"stock_id": h.stock_id, "stock_name": h.stock_name,
                 "weight_pct": _round(h.weight_pct), "shares": h.shares}
                for h in items
            ],
        }
        etf_meta.append({
            "etf_code": e.etf_code, "etf_name": e.etf_name, "etf_type": e.etf_type,
            "issuer": e.issuer, "latest_date": latest, "prev_date": prev_date,
            "holding_count": len(items), "data_dates": len(dates),
        })

        if prev_date:
            prev = repo.get_holdings(e.etf_code, prev_date)
            ds = diff_service.compute_diffs(e.etf_code, prev_date, latest, prev, items, created)
            ds = [d for d in ds if d.change_type != "無異動"]
            diffs[e.etf_code] = {
                "from_date": prev_date, "to_date": latest,
                "items": [
                    {"stock_id": d.stock_id, "stock_name": d.stock_name,
                     "change_type": d.change_type,
                     "old_shares": d.old_shares, "new_shares": d.new_shares,
                     "shares_diff": d.shares_diff,
                     "old_weight_pct": _round(d.old_weight_pct),
                     "new_weight_pct": _round(d.new_weight_pct),
                     "weight_diff_pct": _round(d.weight_diff_pct)}
                    for d in ds
                ],
            }

    def common(direction):
        return [
            {"stock_id": m.stock_id, "stock_name": m.stock_name, "direction": m.direction,
             "etf_count": m.etf_count, "etf_codes": m.etf_codes,
             "total_shares_diff": m.total_shares_diff}
            for m in aggregate.common_moves(repo, codes, direction, created, min_etfs=min_etfs)
        ]

    return {
        "generated_at": created,
        "etf_type": etf_type,
        "summary": {
            "etf_count": len(etf_meta),
            "with_diff": sum(1 for c in codes if c in diffs),
            "total_holdings": sum(h["holding_count"] for h in etf_meta),
        },
        "etfs": etf_meta,
        "holdings": holdings,
        "diffs": diffs,
        "common_add": common("add"),
        "common_reduce": common("reduce"),
    }


def export_dashboard_data(repo: Optional[SqliteRepository] = None, min_etfs: int = 2) -> Path:
    repo = repo or SqliteRepository()
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload(repo, min_etfs=min_etfs)
    DATA_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return DATA_JSON
