"""
AI 自主交易员 — 看门狗
独立于主系统运行，检测故障并通知

检查项：
1. 最后一轮是否超时（默认 45 分钟无新轮次 = 异常）
2. 是否有"孤儿持仓"（trade_db 有 open 但长时间无轮次）
3. OKX API 是否可达
"""
import sqlite3
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "trades.db"
ROUND_TIMEOUT_MIN = 45  # 超过45分钟没新轮次就告警
ORPHAN_HOURS = 2  # 持仓超过2小时没有轮次检查就告警


def check_round_timeout() -> str | None:
    """检查最后一轮是否超时"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute(
            "SELECT timestamp FROM round_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None  # 没有轮次记录，可能是新系统
        last_ts = datetime.fromisoformat(row[0])
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_ts
        if elapsed > timedelta(minutes=ROUND_TIMEOUT_MIN):
            mins = int(elapsed.total_seconds() / 60)
            return f"系统停摆: 已 {mins} 分钟无新轮次 (上次: {last_ts.strftime('%H:%M UTC')})"
    except Exception as e:
        return f"数据库读取失败: {e}"
    return None


def check_orphan_positions() -> str | None:
    """检查是否有孤儿持仓"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        opens = conn.execute(
            "SELECT id, coin, timestamp FROM trades WHERE status='open'"
        ).fetchall()
        last_round = conn.execute(
            "SELECT timestamp FROM round_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not opens:
            return None
        if not last_round:
            return f"有 {len(opens)} 个持仓但无轮次记录，系统可能未启动"
        last_ts = datetime.fromisoformat(last_round[0])
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_ts
        if elapsed > timedelta(hours=ORPHAN_HOURS):
            coins = ", ".join(row[1] for row in opens)
            hrs = elapsed.total_seconds() / 3600
            return f"孤儿持仓: {coins} — 已 {hrs:.1f}h 无人管理"
    except Exception as e:
        return f"孤儿持仓检查失败: {e}"
    return None


def check_okx_api() -> str | None:
    """检查 OKX API 是否可达"""
    try:
        url = "https://www.okx.com/api/v5/public/time"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        if data.get("code") != "0":
            return f"OKX API 异常: code={data.get('code')}"
    except Exception as e:
        return f"OKX API 不可达: {e}"
    return None


def run():
    if not DB_PATH.exists():
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M UTC')}] 数据库不存在，跳过检查")
        return

    issues = []
    for check in [check_round_timeout, check_orphan_positions, check_okx_api]:
        result = check()
        if result:
            issues.append(result)

    if issues:
        msg = "⚠️ 看门狗告警\n\n" + "\n".join(f"• {i}" for i in issues)
        print(msg)
        try:
            from notify import notify_error
            notify_error(msg)
        except Exception as e:
            print(f"通知发送失败: {e}")
    else:
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M UTC')}] 一切正常")


if __name__ == "__main__":
    run()
