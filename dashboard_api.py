"""
AI 自主交易员 — Dashboard API
提供 JSON 数据给前端页面
"""
import json
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from trade_db import get_stats, get_recent_trades, get_open_trades, get_signal_stats, get_recent_rounds, get_reviews, get_trades_paged
from config import OKX_DEMO
from pathlib import Path
import sqlite3
import urllib.request

DB_PATH = Path(__file__).parent / "trades.db"
_price_cache = {}
_price_cache_time = 0
MEMORY_DIR = Path.home() / ".claude/projects/-Users-crypto/memory"
PORT = 8888


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/stats":
            self._json_response(get_stats())
        elif path == "/api/trades":
            params = parse_qs(parsed.query)
            n = int(params.get("n", [15])[0])
            offset = int(params.get("offset", [0])[0])
            self._json_response(get_trades_paged(n, offset))
        elif path == "/api/open":
            self._json_response(get_open_trades())
        elif path == "/api/signals":
            self._json_response(get_signal_stats())
        elif path == "/api/all-trades":
            self._json_response(self._get_all_closed())
        elif path == "/api/strategy-notes":
            notes_path = MEMORY_DIR / "strategy-notes.md"
            content = notes_path.read_text() if notes_path.exists() else "暂无"
            self._json_response({"content": content})
        elif path == "/api/recent-reasoning":
            self._json_response(self._get_recent_reasoning())
        elif path == "/api/rounds":
            params = parse_qs(parsed.query)
            n = int(params.get("n", [20])[0])
            offset = int(params.get("offset", [0])[0])
            self._json_response(get_recent_rounds(n, offset))
        elif path == "/api/reviews":
            params = parse_qs(parsed.query)
            n = int(params.get("n", [5])[0])
            offset = int(params.get("offset", [0])[0])
            self._json_response(get_reviews(n, offset))
        elif path == "/api/today":
            self._json_response(self._get_today())
        elif path == "/api/prices":
            self._json_response(self._get_prices())
        elif path == "/api/calendar":
            self._json_response(self._get_calendar())
        elif path == "/api/mode":
            self._json_response({"demo": OKX_DEMO})
        elif path == "/" or path == "/index.html":
            self._serve_html()
        else:
            super().do_GET()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _serve_html(self):
        html_path = Path(__file__).parent / "dashboard.html"
        if html_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"dashboard.html not found")

    def _get_all_closed(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, timestamp, coin, side, entry_price, exit_price, "
            "pnl, pnl_pct, sheets, leverage, close_reason, duration_min, confidence "
            "FROM trades WHERE status='closed' ORDER BY id"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _get_prices(self):
        """从 OKX 公共 API 实时拉取 BTC/ETH 价格（自动匹配模拟/实盘），60秒缓存"""
        global _price_cache, _price_cache_time
        if _price_cache and time.time() - _price_cache_time < 60:
            return _price_cache
        result = {"btc": {}, "eth": {}}
        _headers = {"User-Agent": "Mozilla/5.0"}
        if OKX_DEMO:
            _headers["x-simulated-trading"] = "1"
        try:
            url = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
            req = urllib.request.Request(url, headers=_headers)
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            for t in data.get("data", []):
                inst = t.get("instId", "")
                if inst == "BTC-USDT-SWAP":
                    key = "btc"
                elif inst == "ETH-USDT-SWAP":
                    key = "eth"
                else:
                    continue
                last = float(t.get("last", 0))
                open24 = float(t.get("open24h", 0))
                chg = ((last - open24) / open24 * 100) if open24 else 0
                result[key] = {
                    "price": last,
                    "change": f"{'+' if chg >= 0 else ''}{chg:.2f}%",
                    "high": float(t.get("high24h", 0)),
                    "low": float(t.get("low24h", 0)),
                    "vol": t.get("vol24h", "0"),
                }
        except Exception:
            pass
        # 补充 funding rate
        try:
            for pair, key in [("BTC-USDT-SWAP", "btc"), ("ETH-USDT-SWAP", "eth")]:
                url = f"https://www.okx.com/api/v5/public/funding-rate?instId={pair}"
                req = urllib.request.Request(url, headers=_headers)
                resp = urllib.request.urlopen(req, timeout=3)
                data = json.loads(resp.read())
                fr = data.get("data", [{}])[0].get("fundingRate", "")
                if fr and key in result:
                    result[key]["funding"] = fr
        except Exception:
            pass
        _price_cache = result
        _price_cache_time = time.time()
        return result

    def _get_today(self):
        """今日统计"""
        from datetime import datetime, timezone  # noqa: local import OK
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # 今日已平仓
        closed = conn.execute(
            "SELECT pnl FROM trades WHERE status='closed' AND timestamp >= ?",
            (today,)
        ).fetchall()
        # 今日轮次
        rounds = conn.execute(
            "SELECT COUNT(*) FROM round_logs WHERE timestamp >= ?",
            (today,)
        ).fetchone()[0]
        conn.close()
        pnls = [r["pnl"] or 0 for r in closed]
        wins = sum(1 for p in pnls if p > 0)
        return {
            "trades": len(pnls),
            "wins": wins,
            "losses": len(pnls) - wins,
            "pnl": round(sum(pnls), 2),
            "best": round(max(pnls), 2) if pnls else 0,
            "worst": round(min(pnls), 2) if pnls else 0,
            "rounds": rounds,
        }

    def _get_calendar(self):
        """每日PnL热力图数据：最近90天"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT date(timestamp) as day, COUNT(*) as trades, "
            "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, "
            "SUM(pnl) as pnl "
            "FROM trades WHERE status='closed' "
            "GROUP BY date(timestamp) ORDER BY day"
        ).fetchall()
        # Also get round counts per day
        rounds = conn.execute(
            "SELECT date(timestamp) as day, COUNT(*) as rounds "
            "FROM round_logs GROUP BY date(timestamp)"
        ).fetchall()
        conn.close()
        rounds_map = {r["day"]: r["rounds"] for r in rounds}
        return [
            {
                "date": r["day"],
                "trades": r["trades"],
                "wins": r["wins"],
                "pnl": round(r["pnl"] or 0, 2),
                "rounds": rounds_map.get(r["day"], 0),
            }
            for r in rows
        ]

    def _get_recent_reasoning(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, timestamp, coin, side, reasoning, market_state, indicators_used, lessons, status, pnl "
            "FROM trades ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["reasoning"] = json.loads(d["reasoning"]) if d["reasoning"] else {}
            except (json.JSONDecodeError, TypeError):
                d["reasoning"] = {}
            # indicators_used is a plain string like "EMA+MACD+RSI"
            d["indicators_used"] = d.get("indicators_used") or ""
            result.append(d)
        return result

    def log_message(self, format, *args):
        pass  # 静默日志


if __name__ == "__main__":
    print(f"Dashboard running at http://localhost:{PORT}")
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    server.serve_forever()
