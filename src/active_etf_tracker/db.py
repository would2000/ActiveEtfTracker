"""SQLite 儲存層：建表 + Upsert + 查詢。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import config
from .models import ActiveEtf, HoldingSnapshot

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
    shares INTEGER,                       -- 股數本質為整數；INTEGER affinity 會把 1100000.0 無損存成整數
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_hash TEXT,
    PRIMARY KEY (etf_code, data_date, stock_id, source_name)
);

-- idx_snapshot_etf_date 與主鍵 (etf_code, data_date, stock_id, source_name) 的最左
-- 前綴重疊，查詢用不到卻增加每次寫入成本，移除之（DROP 讓既有 DB 也一併清掉）。
DROP INDEX IF EXISTS idx_snapshot_etf_date;

-- diff 已改為即時計算、不再持久化；清掉既有 DB 殘留的舊表（見上方說明）。
DROP TABLE IF EXISTS etf_holdings_diff;
"""

# 註：持股異動 (diff) 不再持久化。歷史上曾有 etf_holdings_diff 表，但 diff 可由
# 兩個資料日期的 snapshot 即時算出（見 services/diff_service.compute_diffs），
# 持久化反而會在 snapshot 重抓後變成過期髒資料、形成雙真相來源，故移除。

# 明列查詢欄位（順序對應 dataclass 欄位），避免 SELECT * 在日後加欄位時把非預期
# 欄位灌進 ActiveEtf(**dict(r)) / HoldingSnapshot(**dict(r)) 而拋 TypeError。
_ETF_COLS = ("etf_code, etf_name, etf_type, issuer, twse_url, moneydj_url, "
             "is_active, first_seen_at, last_seen_at")
_SNAP_COLS = ("etf_code, data_date, stock_id, stock_name, weight_pct, shares, "
              "source_name, source_url, fetched_at, raw_hash")


class SqliteRepository:
    """封裝所有 DB 操作。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # timeout：本機伺服器跑更新（子行程寫入）與手動 CLI 讀取若重疊，
        #          以 busy timeout 等待鎖釋放，避免直接 "database is locked"。
        # synchronous=NORMAL：爬取資料可重抓、可重建，放寬 fsync 換取批次寫入速度。
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=NORMAL")
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
        q = f"SELECT {_ETF_COLS} FROM active_etfs WHERE 1=1"
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
        # 防呆：data_date / etf_code / stock_id 任一為空就跳過，避免空字串日期
        # 污染 get_data_dates 與 latest_two_dates（解析失敗時 data_date 可能為 ""）。
        rows = [
            (s.etf_code, s.data_date, s.stock_id, s.stock_name, s.weight_pct,
             s.shares, s.source_name, s.source_url, s.fetched_at, s.raw_hash)
            for s in snaps
            if s.data_date and s.etf_code and s.stock_id
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
                f"""SELECT {_SNAP_COLS} FROM etf_holdings_snapshot
                    WHERE etf_code=? AND data_date=? AND source_name=?
                    ORDER BY weight_pct DESC""",
                (etf_code, data_date, source_name),
            ).fetchall()
        return [HoldingSnapshot(**dict(r)) for r in rows]
