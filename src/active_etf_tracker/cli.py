"""命令列入口：串起清單 → 抓持股 → 比對 → 輸出。

子指令：
  update-list                 抓 TWSE 主動式 ETF 清單並寫入 DB
  fetch  [--etf CODE | --all] 抓 MoneyDJ 持股快照
  diff   [--etf CODE | --all] 比對最新兩個資料日期，產生異動
  export [--etf CODE | --all] 匯出 CSV（清單 / 持股 / 異動）
  run    [--limit N]          一鍵跑完整 MVP（股票型 A 為主）
  list                        列出 DB 內已知 ETF
"""
from __future__ import annotations

import argparse
import sys
import time

from . import config
from .db import SqliteRepository
from dataclasses import asdict

import pandas as pd

from .export import (
    export_active_etfs,
    export_common_moves,
    export_diffs,
    export_holdings,
    export_workbook,
)
from .scrapers import moneydj, twse_list
from .scrapers.base import now_iso, today_iso
from .services import aggregate, diff_service
from .services.trading_date import latest_two_dates


_REPO: SqliteRepository | None = None


def _repo() -> SqliteRepository:
    """回傳行程內共用的 Repository，避免 run 內各子指令重複建表/重連。"""
    global _REPO
    if _REPO is None:
        config.ensure_dirs()
        _REPO = SqliteRepository()
    return _REPO


def cmd_update_list(args) -> int:
    repo = _repo()
    raw = config.RAW_DIR / f"twse_active_list_{today_iso()}.html"
    print(f"[update-list] 抓取 TWSE 主動式 ETF 清單 …")
    etfs = twse_list.scrape_active_etfs(save_raw_to=raw)
    for e in etfs:
        repo.upsert_etf(e)
    print(f"[update-list] 共 {len(etfs)} 檔股票型主動式 ETF（第六碼 A）→ 已寫入 DB（債券型 D 不納入）")
    for e in etfs:
        print(f"   {e.etf_code}  {e.etf_type or '?':5s}  {e.etf_name}")
    return 0


def _target_etfs(repo: SqliteRepository, args):
    if getattr(args, "etf", None):
        codes = [c.strip().upper() for c in args.etf.split(",")]
        known = {e.etf_code: e for e in repo.get_etfs(active_only=False)}
        return [known.get(c) or _adhoc(c) for c in codes]
    etfs = repo.get_etfs(etf_type="stock")  # 第一版鎖定股票型 A
    if getattr(args, "limit", None):
        etfs = etfs[: args.limit]
    return etfs


def _adhoc(code: str):
    from .models import ActiveEtf
    ts = now_iso()
    return ActiveEtf(etf_code=code, etf_name=code, etf_type=twse_list.classify_etf_type(code),
                     moneydj_url=config.moneydj_url(code), first_seen_at=ts, last_seen_at=ts)


def cmd_fetch(args) -> int:
    repo = _repo()
    targets = _target_etfs(repo, args)
    if not targets:
        print("[fetch] 沒有可抓取的 ETF；請先執行 update-list 或加 --etf")
        return 1
    print(f"[fetch] 準備抓取 {len(targets)} 檔 ETF 持股 …")
    for e in targets:
        # 確保 ETF 先存在於 active_etfs，避免 --etf 指定的臨時代號其快照變成
        # 查不到母表的孤兒資料（web_export 只列 active_etfs 內的股票型 ETF）。
        repo.upsert_etf(e)
        raw = config.RAW_DIR / f"moneydj_{e.etf_code}_{today_iso()}.html"
        try:
            data_date, snaps, pages = moneydj.scrape_holdings(e.etf_code, save_raw_to=raw)
        except Exception as ex:  # noqa: BLE001
            print(f"   {e.etf_code}  ✗ 抓取失敗：{ex}")
            continue
        if not data_date or not snaps:
            print(f"   {e.etf_code}  ✗ 解析不到持股（data_date={data_date}, rows={len(snaps)}）")
            continue
        n = repo.upsert_snapshots(snaps)
        ok = moneydj.completeness_ok(len(snaps), pages)
        flag = "" if ok else "  ⚠ 列數與頁次不符，可能未完整載入"
        pg = f"/{pages}頁" if pages else ""
        print(f"   {e.etf_code}  ✓ 資料日期 {data_date}，{n} 檔完整持股{pg}{flag}")
        time.sleep(args.sleep)
    return 0


def cmd_diff(args) -> int:
    repo = _repo()
    targets = _target_etfs(repo, args)
    created = now_iso()
    any_done = False
    for e in targets:
        prev_date, latest = latest_two_dates(repo, e.etf_code)
        if not latest:
            print(f"   {e.etf_code}  ✗ 無快照")
            continue
        if not prev_date:
            print(f"   {e.etf_code}  · 只有一個資料日期（{latest}），尚無法比對")
            continue
        prev = repo.get_holdings(e.etf_code, prev_date)
        curr = repo.get_holdings(e.etf_code, latest)
        diffs = diff_service.compute_diffs(
            e.etf_code, prev_date, latest, prev, curr, created,
            include_unchanged=args.include_unchanged,
        )
        changed = [d for d in diffs if d.change_type != "無異動"]
        print(f"   {e.etf_code}  ✓ {prev_date} → {latest}：{len(changed)} 筆異動")
        for d in changed[:20]:
            sd = f"{d.shares_diff:+,.0f}" if d.shares_diff is not None else "-"
            wd = f"{d.weight_diff_pct:+.2f}%" if d.weight_diff_pct is not None else "-"
            print(f"        {d.stock_id:>6} {d.stock_name:<10} {d.change_type:<6} 股數{sd:>14}  權重{wd}")
        any_done = True
    if not any_done:
        print("[diff] 沒有任何 ETF 具備兩個以上資料日期；明天再抓一次即可比對。")
    return 0


def _print_common(moves, direction: str, top: int = 25) -> None:
    label = "共同加碼" if direction == "add" else "共同減碼"
    if not moves:
        print(f"   ({label}：無符合 min-etfs 門檻的個股)")
        return
    print(f"   === {label}清單（{len(moves)} 檔）===")
    for m in moves[:top]:
        sd = f"{m.total_shares_diff:+,.0f}"
        print(f"      {m.stock_id:>6} {m.stock_name or '':<10} {m.etf_count} 檔  "
              f"股數合計{sd:>16}  [{','.join(m.etf_codes)}]")


def cmd_common(args) -> int:
    repo = _repo()
    targets = _target_etfs(repo, args)
    codes = [e.etf_code for e in targets if e]
    created = now_iso()
    tag = today_iso()
    directions = ["add", "reduce"] if args.direction == "both" else [args.direction]
    for d in directions:
        moves = aggregate.common_moves(repo, codes, d, created, min_etfs=args.min_etfs)
        _print_common(moves, d)
        p = export_common_moves(moves, d, tag)
        print(f"   → {p}")
    return 0


def cmd_export(args) -> int:
    repo = _repo()
    tag = today_iso()
    etfs = repo.get_etfs(active_only=False)
    if etfs:
        p = export_active_etfs(etfs, tag)
        print(f"[export] ETF 清單 → {p}")

    targets = _target_etfs(repo, args)
    for e in targets:
        dates = repo.get_data_dates(e.etf_code)
        if dates:
            holdings = repo.get_holdings(e.etf_code, dates[0])
            p = export_holdings(e.etf_code, dates[0], holdings)
            print(f"[export] {e.etf_code} 持股({dates[0]}) → {p}")
        prev_date, latest = latest_two_dates(repo, e.etf_code)
        if prev_date and latest:
            prev = repo.get_holdings(e.etf_code, prev_date)
            curr = repo.get_holdings(e.etf_code, latest)
            diffs = [d for d in diff_service.compute_diffs(
                         e.etf_code, prev_date, latest, prev, curr, now_iso())
                     if d.change_type != "無異動"]
            p = export_diffs(e.etf_code, prev_date, latest, diffs)
            print(f"[export] {e.etf_code} 異動({prev_date}→{latest}) → {p}")
    return 0


def cmd_report(args) -> int:
    """產生單一 Excel 報表：清單 / 最新持股 / 異動彙總 / 共同加碼 / 共同減碼。"""
    repo = _repo()
    targets = _target_etfs(repo, args)
    codes = [e.etf_code for e in targets if e]
    created = now_iso()
    tag = today_iso()

    etfs = repo.get_etfs(active_only=False)
    holdings_rows, diff_rows = [], []
    for code in codes:
        dates = repo.get_data_dates(code)
        if dates:
            holdings_rows += [asdict(h) for h in repo.get_holdings(code, dates[0])]
        prev_date, latest = latest_two_dates(repo, code)
        if prev_date and latest:
            prev = repo.get_holdings(code, prev_date)
            curr = repo.get_holdings(code, latest)
            ds = diff_service.compute_diffs(code, prev_date, latest, prev, curr, created)
            diff_rows += [asdict(d) for d in ds if d.change_type != "無異動"]

    def _common_df(direction):
        moves = aggregate.common_moves(repo, codes, direction, created, min_etfs=args.min_etfs)
        return pd.DataFrame([{
            "stock_id": m.stock_id, "stock_name": m.stock_name, "direction": m.direction,
            "etf_count": m.etf_count, "etf_codes": ",".join(m.etf_codes),
            "total_shares_diff": m.total_shares_diff,
        } for m in moves])

    sheets = {
        "主動式ETF清單": pd.DataFrame([asdict(e) for e in etfs]),
        "最新持股": pd.DataFrame(holdings_rows),
        "異動彙總": pd.DataFrame(diff_rows),
        "共同加碼": _common_df("add"),
        "共同減碼": _common_df("reduce"),
    }
    path = export_workbook(sheets, tag)
    print(f"[report] Excel 報表 → {path}")
    for name, df in sheets.items():
        print(f"   工作表「{name}」：{len(df)} 列")
    return 0


def cmd_run(args) -> int:
    """一鍵 MVP：清單 → 抓股票型 A 持股 → 比對 → 匯出。"""
    print("=" * 60)
    cmd_update_list(args)
    print("-" * 60)
    cmd_fetch(args)
    print("-" * 60)
    cmd_diff(args)
    print("-" * 60)
    cmd_common(args)
    print("-" * 60)
    cmd_export(args)
    print("-" * 60)
    cmd_report(args)
    print("-" * 60)
    from . import web_export
    path = web_export.export_dashboard_data(_repo(), min_etfs=getattr(args, "min_etfs", 2))
    print(f"[dashboard] 前端資料 → {path}（用 `dashboard --serve` 開啟頁面）")
    print("=" * 60)
    print("完成。輸出檔在 data/exports/；前端在 web/")
    return 0


def cmd_dashboard(args) -> int:
    """匯出儀表板 data.json；--serve 則啟動本機伺服器開啟前端。"""
    from . import web_export
    repo = _repo()
    path = web_export.export_dashboard_data(repo, min_etfs=args.min_etfs)
    print(f"[dashboard] 資料已匯出 → {path}")
    print(f"            前端頁面：{web_export.WEB_DIR / 'index.html'}")
    if args.serve:
        from . import server
        server.serve(port=args.port, min_etfs=args.min_etfs)
    return 0


def cmd_list(args) -> int:
    repo = _repo()
    etfs = repo.get_etfs(active_only=False)
    if not etfs:
        print("DB 內尚無 ETF，請先 update-list")
        return 0
    for e in etfs:
        dates = repo.get_data_dates(e.etf_code)
        d = f"（{len(dates)} 個資料日期，最新 {dates[0]}）" if dates else "（尚無快照）"
        print(f"{e.etf_code}  {e.etf_type or '?':5s}  {e.etf_name}  {d}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="active-etf", description="主動式 ETF 每日持股異動追蹤")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_targets(sp):
        sp.add_argument("--etf", help="指定 ETF 代號，逗號分隔，如 00981A,00982A")
        sp.add_argument("--all", action="store_true", help="全部股票型 A（預設行為）")
        sp.add_argument("--limit", type=int, help="限制檔數（測試用）")

    sp = sub.add_parser("update-list", help="抓 TWSE 主動式 ETF 清單")
    sp.set_defaults(func=cmd_update_list)

    sp = sub.add_parser("fetch", help="抓 MoneyDJ 持股快照")
    add_targets(sp)
    sp.add_argument("--sleep", type=float, default=1.0, help="每檔間隔秒數")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("diff", help="比對最新兩個資料日期")
    add_targets(sp)
    sp.add_argument("--include-unchanged", action="store_true", help="包含無異動項目")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("common", help="多檔 ETF 共同加碼／減碼清單")
    add_targets(sp)
    sp.add_argument("--direction", choices=["add", "reduce", "both"], default="both",
                    help="加碼 / 減碼 / 兩者")
    sp.add_argument("--min-etfs", type=int, default=2, dest="min_etfs",
                    help="至少幾檔 ETF 同向才列入（預設 2）")
    sp.set_defaults(func=cmd_common)

    sp = sub.add_parser("export", help="匯出 CSV")
    add_targets(sp)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("report", help="產生單一 Excel 報表（多工作表）")
    add_targets(sp)
    sp.add_argument("--min-etfs", type=int, default=2, dest="min_etfs")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("run", help="一鍵跑完整 MVP")
    add_targets(sp)
    sp.add_argument("--sleep", type=float, default=1.0)
    sp.add_argument("--include-unchanged", action="store_true")
    sp.add_argument("--direction", choices=["add", "reduce", "both"], default="both")
    sp.add_argument("--min-etfs", type=int, default=2, dest="min_etfs")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("dashboard", help="匯出前端 data.json（--serve 開本機伺服器）")
    sp.add_argument("--min-etfs", type=int, default=2, dest="min_etfs")
    sp.add_argument("--serve", action="store_true", help="啟動本機伺服器")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("list", help="列出 DB 內 ETF")
    sp.set_defaults(func=cmd_list)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
