"""SQLite 儲存層：建表 + Upsert + 查詢。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import config
from .models import ActiveEtf, HoldingDiff, HoldingSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS active_etfs (
    etf_code TEXT PRIMARY KEY,
    etf_name TEXT NOT NULL,
    etf_type TEXT,
    issuer TEXT,
    twse_url TEXT,
    moneydj_url TEXT,
    is_active INTEGER DEFAULT 1,
    first_seen_at TEXT,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS etf_holdings_snapshot (
    etf_code TEXT NOT NULL,
    data_date TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    weight_pct REAL,
    shares REAL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_hash TEXT,
    PRIMARY KEY (etf_code, data_date, stock_id, source_name)
);

CREATE TABLE IF NOT EXISTS etf_holdings_diff (
    etf_code TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    change_type TEXT NOT NULL,
    old_weight_pct REAL,
    new_weight_pct REAL,
    weight_diff_pct REAL,
    old_shares REAL,
    new_shares REAL,
    shares_diff REAL,
    source_name TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (etf_code, from_date, to_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_etf_date
    ON etf_holdings_snapshot (etf_code, data_date);
"""


class SqliteRepository:
    """封裝所有 DB 操作。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    # ---------- active_etfs ----------
    def upsert_etf(self, etf: ActiveEtf) -> None:
        """寫入/更新 ETF；first_seen_at 只在初次寫入時設定。"""
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO active_etfs
                    (etf_code, etf_name, etf_type, issuer, twse_url, moneydj_url,
                     is_active, first_seen_at, last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(etf_code) DO UPDATE SET
                    etf_name=excluded.etf_name,
                    etf_type=excluded.etf_type,
                    issuer=excluded.issuer,
                    twse_url=excluded.twse_url,
                    moneydj_url=excluded.moneydj_url,
                    is_active=excluded.is_active,
                    last_seen_at=excluded.last_seen_at
                """,
                (etf.etf_code, etf.etf_name, etf.etf_type, etf.issuer, etf.twse_url,
                 etf.moneydj_url, etf.is_active, etf.first_seen_at, etf.last_seen_at),
            )

    def get_etfs(self, etf_type: Optional[str] = None, active_only: bool = True) -> list[ActiveEtf]:
        q = "SELECT * FROM active_etfs WHERE 1=1"
        args: list = []
        if active_only:
            q += " AND is_active=1"
        if etf_type:
            q += " AND etf_type=?"
            args.append(etf_type)
        q += " ORDER BY etf_code"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [ActiveEtf(**dict(r)) for r in rows]

    # ---------- snapshots ----------
    def upsert_snapshots(self, snaps: Iterable[HoldingSnapshot]) -> int:
        rows = [
            (s.etf_code, s.data_date, s.stock_id, s.stock_name, s.weight_pct,
             s.shares, s.source_name, s.source_url, s.fetched_at, s.raw_hash)
            for s in snaps
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(
                """
                INSERT INTO etf_holdings_snapshot
                    (etf_code, data_date, stock_id, stock_name, weight_pct, shares,
                     source_name, source_url, fetched_at, raw_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(etf_code, data_date, stock_id, source_name) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    weight_pct=excluded.weight_pct,
                    shares=excluded.shares,
                    source_url=excluded.source_url,
                    fetched_at=excluded.fetched_at,
                    raw_hash=excluded.raw_hash
                """,
                rows,
            )
        return len(rows)

    def get_data_dates(self, etf_code: str, source_name: str = config.SOURCE_MONEYDJ) -> list[str]:
        """回傳該 ETF 已有的資料日期（新→舊）。"""
        with self._conn() as c:
            rows = c.execute(
                """SELECT DISTINCT data_date FROM etf_holdings_snapshot
                   WHERE etf_code=? AND source_name=? ORDER BY data_date DESC""",
                (etf_code, source_name),
            ).fetchall()
        return [r["data_date"] for r in rows]

    def get_holdings(self, etf_code: str, data_date: str,
                     source_name: str = config.SOURCE_MONEYDJ) -> list[HoldingSnapshot]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM etf_holdings_snapshot
                   WHERE etf_code=? AND data_date=? AND source_name=?
                   ORDER BY weight_pct DESC""",
                (etf_code, data_date, source_name),
            ).fetchall()
        return [HoldingSnapshot(**dict(r)) for r in rows]

    # ---------- diffs ----------
    def upsert_diffs(self, diffs: Iterable[HoldingDiff]) -> int:
        rows = [
            (d.etf_code, d.from_date, d.to_date, d.stock_id, d.stock_name, d.change_type,
             d.old_weight_pct, d.new_weight_pct, d.weight_diff_pct,
             d.old_shares, d.new_shares, d.shares_diff, d.source_name, d.created_at)
            for d in diffs
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(
                """
                INSERT INTO etf_holdings_diff
                    (etf_code, from_date, to_date, stock_id, stock_name, change_type,
                     old_weight_pct, new_weight_pct, weight_diff_pct,
                     old_shares, new_shares, shares_diff, source_name, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(etf_code, from_date, to_date, stock_id) DO UPDATE SET
                    stock_name=excluded.stock_name,
                    change_type=excluded.change_type,
                    old_weight_pct=excluded.old_weight_pct,
                    new_weight_pct=excluded.new_weight_pct,
                    weight_diff_pct=excluded.weight_diff_pct,
                    old_shares=excluded.old_shares,
                    new_shares=excluded.new_shares,
                    shares_diff=excluded.shares_diff,
                    source_name=excluded.source_name,
                    created_at=excluded.created_at
                """,
                rows,
            )
        return len(rows)

    def get_diffs(self, etf_code: str, from_date: str, to_date: str) -> list[HoldingDiff]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM etf_holdings_diff
                   WHERE etf_code=? AND from_date=? AND to_date=?
                   ORDER BY change_type, ABS(COALESCE(shares_diff,0)) DESC""",
                (etf_code, from_date, to_date),
            ).fetchall()
        return [HoldingDiff(**dict(r)) for r in rows]
