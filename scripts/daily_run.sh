#!/usr/bin/env bash
# 每日抓取 + 比對 + 報表。於台股收盤後「手動」執行（本專案不使用背景排程）。
#
# 用法：
#   scripts/daily_run.sh            # 全部股票型 A
#   scripts/daily_run.sh --limit 5  # 測試
set -euo pipefail

# 專案根目錄（此腳本位於 scripts/ 下）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 啟用 venv（若存在）
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export PYTHONPATH="$ROOT/src"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 開始每日更新 ====="
python -m active_etf_tracker.cli run "$@"
echo "----- 資料正確性驗證 -----"
python scripts/verify_run.py || echo "（驗證發現錯誤等級問題，請見上方報告）"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
