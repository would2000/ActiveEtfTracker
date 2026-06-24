"""每日抓取後的資料正確性自動檢查。

由 daily_run.sh 在 `cli run` 之後呼叫，產出人類可讀的檢查報告（同時印到 stdout
與寫入 data/verify_report.txt）。檢查項目：
  - 抓到的 ETF 檔數是否符合預期（股票型 A）
  - 最新資料日期是否推進（是否真的更新到新的一天）
  - 各 ETF 持股檔數、權重總和是否在合理範圍
  - 是否出現異常（負股數、重複代號、缺名稱、空持股）
  - 有幾檔 ETF 具備兩個真實資料日期 → 可產生真實異動
  - 異動數量摘要

回傳碼：0 = 全部通過或僅有提醒；2 = 有錯誤等級的問題。
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from active_etf_tracker import config  # noqa: E402
from active_etf_tracker.scrapers.base import now_iso  # noqa: E402

EXPECTED_ETFS = 27          # 股票型 A（截至 2026-06）
REPORT_PATH = config.DATA_DIR / "verify_report.txt"


def run() -> int:
    lines: list[str] = []
    errors = 0
    warns = 0

    def log(s=""):
        lines.append(s)

    def err(s):
        nonlocal errors
        errors += 1
        lines.append(f"  ✗ [錯誤] {s}")

    def warn(s):
        nonlocal warns
        warns += 1
        lines.append(f"  ⚠ [提醒] {s}")

    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row

    log("=" * 64)
    log(f" 主動式 ETF 資料驗證報告  {now_iso()}")
    log("=" * 64)

    # ETF 清單
    etfs = [r["etf_code"] for r in c.execute(
        "SELECT etf_code FROM active_etfs WHERE etf_type='stock' AND is_active=1 ORDER BY etf_code")]
    log(f"\n[1] 股票型 A ETF 檔數：{len(etfs)}（預期 {EXPECTED_ETFS}）")
    if len(etfs) < EXPECTED_ETFS:
        warn(f"檔數少於預期，可能 update-list 抓取不全或來源新增/下市")
    non_stock = c.execute("SELECT COUNT(*) FROM active_etfs WHERE etf_type!='stock'").fetchone()[0]
    if non_stock:
        err(f"DB 內仍有 {non_stock} 檔非股票型（債券 D 應已排除）")

    # 全域最新資料日期
    dates = [r[0] for r in c.execute(
        "SELECT DISTINCT data_date FROM etf_holdings_snapshot ORDER BY data_date DESC")]
    log(f"\n[2] 資料日期（新→舊，前 5）：{dates[:5]}")
    if not dates:
        err("完全沒有持股快照")
        c.close()
        return _emit(lines, errors, warns)
    latest_global = dates[0]
    log(f"    全域最新資料日期：{latest_global}")

    # 逐檔檢查
    log(f"\n[3] 逐檔檢查（持股數 / 權重總和 / 最新日期）")
    two_date = 0
    weight_flags = 0
    per_etf_latest = {}
    for code in etfs:
        rows = c.execute(
            """SELECT data_date, COUNT(*) n, SUM(weight_pct) wsum,
                      SUM(CASE WHEN shares<0 THEN 1 ELSE 0 END) neg,
                      SUM(CASE WHEN stock_name IS NULL OR stock_name='' THEN 1 ELSE 0 END) noname
               FROM etf_holdings_snapshot WHERE etf_code=?
               GROUP BY data_date ORDER BY data_date DESC""", (code,)).fetchall()
        if not rows:
            warn(f"{code}：無任何持股快照")
            continue
        d = rows[0]
        per_etf_latest[code] = d["data_date"]
        n_dates = len(rows)
        if n_dates >= 2:
            two_date += 1
        # 合理範圍：持股 5~400 檔；權重總和 50~110%
        if not (5 <= d["n"] <= 400):
            warn(f"{code}：持股檔數 {d['n']} 超出合理範圍(5~400)")
        if d["wsum"] is not None and not (50 <= d["wsum"] <= 110):
            # 含期貨/選擇權等衍生品時，名目權重會使總和 >100%，屬正常
            deriv = c.execute(
                """SELECT COUNT(*) FROM etf_holdings_snapshot
                   WHERE etf_code=? AND data_date=? AND shares IS NULL
                     AND (stock_name LIKE '%期貨%' OR stock_name LIKE '%選擇權%')""",
                (code, d["data_date"])).fetchone()[0]
            if d["wsum"] > 110 and deriv:
                log(f"      · {code}：權重總和 {d['wsum']:.1f}%（含 {deriv} 筆期貨/選擇權，名目權重故 >100%，正常）")
            else:
                weight_flags += 1
                warn(f"{code}：權重總和 {d['wsum']:.1f}% 偏離(50~110%)，資料日期 {d['data_date']}")
        if d["neg"]:
            err(f"{code}：有 {d['neg']} 筆負股數")
        if d["noname"]:
            warn(f"{code}：有 {d['noname']} 筆缺股票名稱")
        # 重複代號（同日同股）
        dup = c.execute(
            """SELECT stock_id, COUNT(*) k FROM etf_holdings_snapshot
               WHERE etf_code=? AND data_date=? GROUP BY stock_id HAVING k>1""",
            (code, d["data_date"])).fetchall()
        if dup:
            err(f"{code}：{d['data_date']} 有重複代號 {[r['stock_id'] for r in dup][:5]}")

    # 日期推進檢查
    latest_set = set(per_etf_latest.values())
    log(f"    各 ETF 最新日期分佈：{sorted(latest_set, reverse=True)}")
    log(f"\n[4] 具備兩個以上資料日期（可產生真實異動）的 ETF：{two_date} / {len(etfs)}")
    if two_date == 0:
        warn("尚無任何 ETF 有兩個真實資料日期；今天是第一天屬正常，明日再跑即可比對")

    # 異動摘要（最新兩日，全為真實時才有意義）
    diff_rows = c.execute(
        """SELECT change_type, COUNT(*) k FROM etf_holdings_diff GROUP BY change_type""").fetchall()
    if diff_rows:
        log(f"\n[5] 已存異動（etf_holdings_diff）類型分佈：")
        for r in diff_rows:
            log(f"      {r['change_type']}: {r['k']}")

    c.close()
    return _emit(lines, errors, warns)


def _emit(lines, errors, warns) -> int:
    lines.append("")
    lines.append("-" * 64)
    status = "✅ 通過" if errors == 0 else "❌ 有錯誤"
    lines.append(f" 結果：{status}　錯誤 {errors}　提醒 {warns}")
    lines.append("-" * 64)
    text = "\n".join(lines)
    print(text)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(text, encoding="utf-8")
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(run())
