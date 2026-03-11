"""
AI 自主交易员 — Dashboard API
提供 JSON 数据给前端页面
"""
import json
import time
import base64
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from trade_db import get_conn, get_stats, get_recent_trades, get_open_trades, get_signal_stats, get_recent_rounds, get_reviews, get_trades_paged
from config import OKX_DEMO
from pathlib import Path
import urllib.request

DASH_USER = "admin"
DASH_PASS = "taoli2"
DASH_TOKEN = "taoli2"

_price_cache = {}
_price_cache_time = 0
MEMORY_DIR = Path.home() / ".claude/projects/-Users-crypto/memory"
PORT = 8888


class DashboardHandler(SimpleHTTPRequestHandler):
    def _check_auth(self):
        # Cookie auth
        cookie = self.headers.get("Cookie", "")
        for c in cookie.split(";"):
            c = c.strip()
            if c.startswith("dash_auth=") and c.split("=", 1)[1] == DASH_TOKEN:
                return True
        return False

    def _serve_login(self, error=False):
        msg = '<p style="color:#ff4757;margin-bottom:12px">密码错误</p>' if error else ''
        html = f'''<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>AI Trader Login</title>
<style>
  body{{background:#0a0a0f;color:#e0e0e0;font-family:'Manrope',sans-serif;display:flex;
    justify-content:center;align-items:center;min-height:100vh;margin:0}}
  .box{{background:#111118;border:1px solid #1c1c2c;border-radius:16px;padding:40px;
    width:min(340px,90vw);text-align:center}}
  h2{{margin-bottom:6px;font-size:1.4em;background:linear-gradient(135deg,#00d4aa,#4a9eff);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
  .sub{{color:#6b7280;font-size:0.8em;margin-bottom:24px}}
  input{{width:100%;padding:12px 16px;background:#1a1a28;border:1px solid #1c1c2c;
    border-radius:8px;color:#e0e0e0;font-size:1em;margin-bottom:14px;outline:none;
    font-family:'JetBrains Mono',monospace}}
  input:focus{{border-color:#00d4aa}}
  button{{width:100%;padding:12px;background:linear-gradient(135deg,#00d4aa,#4a9eff);
    border:none;border-radius:8px;color:#0a0a0f;font-weight:700;font-size:1em;cursor:pointer}}
  button:active{{opacity:0.8}}
</style></head><body>
<div class="box">
  <h2>AI Trader</h2>
  <div class="sub">Autonomous Trading Dashboard</div>
  {msg}
  <form method="POST" action="/login">
    <input type="password" name="password" placeholder="输入密码" autofocus>
    <button type="submit">登录</button>
  </form>
</div></body></html>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = parse_qs(body)
            pwd = params.get("password", [""])[0]
            if pwd == DASH_PASS:
                self.send_response(302)
                self.send_header("Set-Cookie", f"dash_auth={DASH_TOKEN}; Path=/; Max-Age=2592000; SameSite=Lax")
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self._serve_login(error=True)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self._serve_login()
            return
        if not self._check_auth():
            # API 请求返回 401 JSON，页面请求跳转登录
            if parsed.path.startswith("/api/"):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
            else:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
            return

        path = parsed.path

        if path == "/api/stats":
            self._json_response(get_stats())
        elif path == "/api/trades":
            params = parse_qs(parsed.query)
            n = self._safe_int(params.get("n", [15])[0], 15)
            offset = self._safe_int(params.get("offset", [0])[0], 0)
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
            n = self._safe_int(params.get("n", [20])[0], 20)
            offset = self._safe_int(params.get("offset", [0])[0], 0)
            self._json_response(get_recent_rounds(n, offset))
        elif path == "/api/reviews":
            params = parse_qs(parsed.query)
            n = self._safe_int(params.get("n", [5])[0], 5)
            offset = self._safe_int(params.get("offset", [0])[0], 0)
            self._json_response(get_reviews(n, offset))
        elif path == "/api/today":
            self._json_response(self._get_today())
        elif path == "/api/prices":
            self._json_response(self._get_prices())
        elif path == "/api/calendar":
            self._json_response(self._get_calendar())
        elif path == "/api/mode":
            self._json_response({"demo": OKX_DEMO})
        elif path == "/mobile" or path == "/mobile.html":
            self._serve_file("mobile.html")
        elif path == "/" or path == "/index.html":
            self._serve_html()
        else:
            super().do_GET()

    @staticmethod
    def _safe_int(val, default: int) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        origin = self.headers.get("Origin", "")
        allowed = origin if origin else "*"
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _serve_html(self):
        self._serve_file("dashboard.html")

    def _serve_file(self, filename):
        file_path = Path(__file__).parent / filename
        if file_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(f"{filename} not found".encode())

    def _get_all_closed(self):
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT id, timestamp, coin, side, entry_price, exit_price, "
                "pnl, pnl_pct, sheets, leverage, close_reason, duration_min, confidence "
                "FROM trades WHERE status='closed' ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def _get_prices(self):
        """从 OKX 公共 API 实时拉取 BTC/ETH 价格（自动匹配模拟/实盘），60秒缓存"""
        global _price_cache, _price_cache_time
        if _price_cache and time.time() - _price_cache_time < 5:
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
        try:
            conn = get_conn()
            closed = conn.execute(
                "SELECT pnl FROM trades WHERE status='closed' AND timestamp >= ?",
                (today,)
            ).fetchall()
            rounds = conn.execute(
                "SELECT COUNT(*) FROM round_logs WHERE timestamp >= ?",
                (today,)
            ).fetchone()[0]
        except Exception:
            return {"trades": 0, "wins": 0, "losses": 0, "pnl": 0, "best": 0, "worst": 0, "rounds": 0}
        finally:
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
        """每日PnL热力图数据"""
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT date(timestamp) as day, COUNT(*) as trades, "
                "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, "
                "SUM(pnl) as pnl "
                "FROM trades WHERE status='closed' "
                "GROUP BY date(timestamp) ORDER BY day"
            ).fetchall()
            rounds = conn.execute(
                "SELECT date(timestamp) as day, COUNT(*) as rounds "
                "FROM round_logs GROUP BY date(timestamp)"
            ).fetchall()
        except Exception:
            return []
        finally:
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
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT id, timestamp, coin, side, reasoning, market_state, indicators_used, lessons, status, pnl "
                "FROM trades ORDER BY id DESC LIMIT 5"
            ).fetchall()
        except Exception:
            return []
        finally:
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
    import os
    bind = os.environ.get("DASH_BIND", "127.0.0.1")
    server = HTTPServer((bind, PORT), DashboardHandler)
    server.serve_forever()
