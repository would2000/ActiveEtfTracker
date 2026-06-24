"""CSV / Excel 輸出層。"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import pandas as pd

from . import config
from .models import ActiveEtf, HoldingDiff, HoldingSnapshot
from .services.aggregate import CommonMove


def _df(rows: Sequence) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in rows])


def export_workbook(sheets: "dict[str, pd.DataFrame]", date_tag: str,
                    filename: str = "active_etf_report") -> Path:
    """把多個 DataFrame 寫成單一 Excel 活頁簿（每個 key 一張工作表）。

    工作表名稱長度上限 31 字，並自動加寬欄位。空 DataFrame 也會建立工作表。
    """
    config.ensure_dirs()
    path = config.EXPORTS_DIR / f"{filename}_{date_tag}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            sheet = (name or "Sheet")[:31]
            if df is None or df.empty:
                df = pd.DataFrame({"(無資料)": []})
            df.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            for col_cells in ws.columns:
                width = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(width + 2, 10), 48)
    return path


def export_active_etfs(etfs: Sequence[ActiveEtf], date_tag: str) -> Path:
    config.ensure_dirs()
    path = config.EXPORTS_DIR / f"active_etfs_{date_tag}.csv"
    _df(etfs).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_holdings(etf_code: str, data_date: str, holdings: Sequence[HoldingSnapshot]) -> Path:
    config.ensure_dirs()
    path = config.EXPORTS_DIR / f"holdings_{etf_code}_{data_date}.csv"
    _df(holdings).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_diffs(etf_code: str, from_date: str, to_date: str, diffs: Sequence[HoldingDiff]) -> Path:
    config.ensure_dirs()
    path = config.EXPORTS_DIR / f"diff_{etf_code}_{from_date}_to_{to_date}.csv"
    if diffs:
        df = _df(diffs)
        # 友善欄位順序
        cols = [
            "etf_code", "from_date", "to_date", "stock_id", "stock_name", "change_type",
            "old_shares", "new_shares", "shares_diff",
            "old_weight_pct", "new_weight_pct", "weight_diff_pct", "source_name",
        ]
        df = df[[c for c in cols if c in df.columns]]
    else:
        df = pd.DataFrame(columns=["etf_code", "from_date", "to_date", "stock_id",
                                   "stock_name", "change_type"])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_common_moves(moves: Sequence[CommonMove], direction: str, date_tag: str) -> Path:
    """匯出共同加碼 / 共同減碼清單。"""
    config.ensure_dirs()
    name = "common_add" if direction == "add" else "common_reduce"
    path = config.EXPORTS_DIR / f"{name}_{date_tag}.csv"
    rows = [
        {
            "stock_id": m.stock_id,
            "stock_name": m.stock_name,
            "direction": m.direction,
            "etf_count": m.etf_count,
            "etf_codes": ",".join(m.etf_codes),
            "total_shares_diff": m.total_shares_diff,
        }
        for m in moves
    ]
    cols = ["stock_id", "stock_name", "direction", "etf_count", "etf_codes", "total_shares_diff"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
