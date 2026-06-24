"""儀表板本機伺服器：靜態檔 + 更新 API。

提供：
  GET  /api/status  → {running, cooldown_remaining, last_update, last_error}
  POST /api/update  → 觸發背景更新（等同 cli run）；含伺服器端 30 分鐘冷卻

為避免對來源網站（TWSE / MoneyDJ）造成負擔或被封鎖，更新有**伺服器端**節流：
每 COOLDOWN_SEC 秒最多觸發一次。上次觸發時間寫入檔案，重啟伺服器不會重置冷卻。
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
import time

from . import config

COOLDOWN_SEC = 30 * 60                      # 30 分鐘
LAST_RUN_FILE = config.DATA_DIR / ".last_update"
RUN_TIMEOUT = 1800                          # 單次更新最長 30 分鐘

_state = {"running": False, "last_error": None, "last_log": ""}
_lock = threading.RLock()   # 可重入：_handle_update 在持鎖時會再呼叫 _status()
_MIN_ETFS = 2


def _read_last_update() -> float:
    try:
        return float(LAST_RUN_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 0.0


def _write_last_update(ts: float) -> None:
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(str(ts), encoding="utf-8")


def _cooldown_remaining() -> int:
    rem = COOLDOWN_SEC - (time.time() - _read_last_update())
    return max(0, int(rem))


def _run_pipeline() -> None:
    """背景執行 cli run（抓取→比對→匯出→更新 data.json）。"""
    env = dict(os.environ, PYTHONPATH=str(config.PROJECT_ROOT / "src"))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "active_etf_tracker.cli", "run",
             "--min-etfs", str(_MIN_ETFS)],
            cwd=str(config.PROJECT_ROOT), env=env,
            capture_output=True, text=True, timeout=RUN_TIMEOUT,
        )
        _state["last_log"] = (proc.stdout or "")[-4000:]
        _state["last_error"] = None if proc.returncode == 0 else (proc.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        _state["last_error"] = "更新逾時（超過 30 分鐘）"
    except Exception as e:  # noqa: BLE001
        _state["last_error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.PROJECT_ROOT / "web"), **kwargs)

    def log_message(self, fmt, *args):  # 安靜一點
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _status(self) -> dict:
        with _lock:
            running = _state["running"]
        return {
            "running": running,
            "cooldown_remaining": _cooldown_remaining(),
            "cooldown_total": COOLDOWN_SEC,
            "last_update": _read_last_update(),
            "last_error": _state["last_error"],
        }

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/api/status":
            return self._json(200, self._status())
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        if self.path.split("?")[0] == "/api/update":
            return self._handle_update()
        self.send_error(404, "Not Found")

    def _handle_update(self):
        with _lock:
            if _state["running"]:
                return self._json(409, {"error": "running", "message": "更新進行中，請稍候",
                                        **self._status()})
            rem = _cooldown_remaining()
            if rem > 0:
                return self._json(429, {"error": "cooldown", "remaining": rem,
                                        "message": f"冷卻中，還需 {rem // 60} 分 {rem % 60} 秒",
                                        **self._status()})
            # 通過：標記執行中並寫入觸發時間（冷卻自「點擊當下」起算）
            _state["running"] = True
            _state["last_error"] = None
            _write_last_update(time.time())
        threading.Thread(target=_run_pipeline, daemon=True).start()
        return self._json(202, {"status": "started", "message": "已開始更新", **self._status()})


def serve(port: int = 8000, min_etfs: int = 2) -> None:
    global _MIN_ETFS
    _MIN_ETFS = min_etfs
    httpd = http.server.ThreadingHTTPServer(("", port), _Handler)
    url = f"http://localhost:{port}/"
    rem = _cooldown_remaining()
    print(f"[dashboard] 伺服器啟動：{url}  （Ctrl+C 結束）")
    print(f"[dashboard] 更新 API 已啟用：POST /api/update（伺服器端 30 分鐘冷卻）")
    if rem:
        print(f"[dashboard] 目前冷卻中，還需 {rem // 60} 分 {rem % 60} 秒")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] 已停止")
        httpd.shutdown()
