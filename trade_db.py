"""
AI 自主交易员 — 交易数据库
SQLite 存储所有交易记录，结构化数据
"""
import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "trades.db"
logger = logging.getLogger("trade_db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """创建表结构"""
    try:
        conn = get_conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            coin TEXT NOT NULL,
            action TEXT NOT NULL,
            side TEXT,
            entry_price REAL,
            actual_entry_price REAL,
            exit_price REAL,
            actual_exit_price REAL,
            sheets INTEGER,
            leverage INTEGER,
            position_size_pct REAL,
            entry_type TEXT,
            stop_loss REAL,
            stop_loss_method TEXT,
            take_profit REAL,
            take_profit_method TEXT,
            pnl REAL,
            pnl_pct REAL,
            duration_min REAL,
            close_reason TEXT,
            confidence REAL,
            risk_usd REAL,
            risk_reward_ratio REAL,
            indicators_used TEXT,
            reasoning TEXT,
            lessons TEXT,
            market_state TEXT,
            order_id TEXT,
            status TEXT DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            trades_count INTEGER,
            wins INTEGER,
            losses INTEGER,
            total_pnl REAL,
            equity REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS signal_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_combo TEXT NOT NULL,
            used_count INTEGER DEFAULT 0,
            win_count INTEGER DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            last_used TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS round_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            coin TEXT,
            btc_price REAL,
            eth_price REAL,
            summary TEXT,
            market_snapshot TEXT
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            stats_snapshot TEXT,
            key_findings TEXT
        );
        """)
        # Add new columns if missing (backwards compat)
        for col, coltype in [("actual_entry_price", "REAL"), ("actual_exit_price", "REAL")]:
            try:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {coltype}")
            except sqlite3.OperationalError:
                pass  # column already exists

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("init_db 失败: %s", e)
        raise


def record_open(
    coin: str, side: str, entry_price: float, sheets: int,
    leverage: int, position_size_pct: float,
    entry_type: str, stop_loss: float, stop_loss_method: str,
    take_profit: float, take_profit_method: str,
    confidence: float, risk_usd: float, risk_reward_ratio: float,
    indicators_used: str, reasoning: dict, market_state: str,
    order_id: str = "",
    actual_entry_price: float = 0,
) -> int:
    """记录开仓"""
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO trades (
                timestamp, coin, action, side, entry_price, actual_entry_price, sheets,
                leverage, position_size_pct, entry_type,
                stop_loss, stop_loss_method, take_profit, take_profit_method,
                confidence, risk_usd, risk_reward_ratio,
                indicators_used, reasoning, market_state, order_id, status
            ) VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (
            datetime.now(timezone.utc).isoformat(),
            coin, side, entry_price, actual_entry_price, sheets,
            leverage, position_size_pct, entry_type,
            stop_loss, stop_loss_method, take_profit, take_profit_method,
            confidence, risk_usd, risk_reward_ratio,
            indicators_used,
            json.dumps(reasoning, ensure_ascii=False),
            market_state, order_id,
        ))
        trade_id = cur.lastrowid
        conn.commit()
        return trade_id
    except Exception as e:
        conn.rollback()
        logger.error("record_open 失败: %s", e)
        raise
    finally:
        conn.close()


def record_close(
    trade_id: int, exit_price: float, pnl: float, pnl_pct: float,
    duration_min: float, close_reason: str, lessons: str = "",
    actual_exit_price: float = 0,
):
    """记录平仓"""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE trades SET
                exit_price = ?, actual_exit_price = ?, pnl = ?, pnl_pct = ?,
                duration_min = ?, close_reason = ?,
                lessons = ?, status = 'closed'
            WHERE id = ?
        """, (exit_price, actual_exit_price, pnl, pnl_pct, duration_min, close_reason, lessons, trade_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("record_close 失败 (trade_id=%s): %s", trade_id, e)
        raise
    finally:
        conn.close()


def get_open_trades() -> list[dict]:
    """查询所有未平仓交易"""
    try:
        conn = get_conn()
        rows = conn.execute("SELECT * FROM trades WHERE status = 'open'").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_open_trades 失败: %s", e)
        return []


def get_recent_trades(n: int = 5) -> list[dict]:
    """查询最近 n 笔已平仓交易"""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_recent_trades 失败: %s", e)
        return []


def get_trades_paged(n: int = 15, offset: int = 0) -> dict:
    """分页查询已平仓交易"""
    try:
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM trades WHERE status='closed'").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ? OFFSET ?", (n, offset)
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows], "total": total}
    except Exception as e:
        logger.error("get_trades_paged 失败: %s", e)
        return {"items": [], "total": 0}


def get_stats() -> dict:
    """计算核心统计指标"""
    try:
        conn = get_conn()
        closed = conn.execute("SELECT * FROM trades WHERE status = 'closed'").fetchall()
        conn.close()
    except Exception as e:
        logger.error("get_stats 查询失败: %s", e)
        return {"total": 0}

    if not closed:
        return {"total": 0}

    trades = [dict(r) for r in closed]
    total = len(trades)
    wins = [t for t in trades if (t["pnl"] or 0) > 0]
    losses = [t for t in trades if (t["pnl"] or 0) <= 0]

    total_pnl = sum(t["pnl"] or 0 for t in trades)
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    # 按币种
    by_coin = {}
    for t in trades:
        c = t["coin"]
        if c not in by_coin:
            by_coin[c] = {"total": 0, "wins": 0, "pnl": 0}
        by_coin[c]["total"] += 1
        if (t["pnl"] or 0) > 0:
            by_coin[c]["wins"] += 1
        by_coin[c]["pnl"] += t["pnl"] or 0

    # 按方向
    by_side = {}
    for t in trades:
        s = t["side"] or "unknown"
        if s not in by_side:
            by_side[s] = {"total": 0, "wins": 0, "pnl": 0}
        by_side[s]["total"] += 1
        if (t["pnl"] or 0) > 0:
            by_side[s]["wins"] += 1
        by_side[s]["pnl"] += t["pnl"] or 0

    # 连亏/连赢
    max_consec_loss = 0
    cur_loss = 0
    cur_streak = 0  # positive = wins, negative = losses
    for t in trades:
        if (t["pnl"] or 0) <= 0:
            cur_loss += 1
            max_consec_loss = max(max_consec_loss, cur_loss)
        else:
            cur_loss = 0
    # 当前连胜/连亏（从最后一笔往回数）
    for t in reversed(trades):
        if cur_streak == 0:
            cur_streak = 1 if (t["pnl"] or 0) > 0 else -1
        elif cur_streak > 0 and (t["pnl"] or 0) > 0:
            cur_streak += 1
        elif cur_streak < 0 and (t["pnl"] or 0) <= 0:
            cur_streak -= 1
        else:
            break

    # 最大回撤
    equity = 0
    peak = 0
    max_dd = 0
    max_dd_pct = 0
    for t in trades:
        equity += t["pnl"] or 0
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        if peak > 0:
            dd_pct = dd / peak * 100
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    return {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / total if total else 0,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else 9999,
        "pnl_ratio": round(avg_win / avg_loss, 4) if avg_loss > 0 else 9999,
        "max_consecutive_loss": max_consec_loss,
        "current_streak": cur_streak,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "by_coin": by_coin,
        "by_side": by_side,
        "best_trade": max(trades, key=lambda t: t["pnl"] or 0),
        "worst_trade": min(trades, key=lambda t: t["pnl"] or 0),
    }


def update_signal_stat(indicator_combo: str, won: bool, pnl: float):
    """更新信号组合统计"""
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM signal_stats WHERE indicator_combo = ?", (indicator_combo,)
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if existing:
            conn.execute("""
                UPDATE signal_stats SET
                    used_count = used_count + 1,
                    win_count = win_count + ?,
                    total_pnl = total_pnl + ?,
                    last_used = ?
                WHERE indicator_combo = ?
            """, (1 if won else 0, pnl, now, indicator_combo))
        else:
            conn.execute("""
                INSERT INTO signal_stats (indicator_combo, used_count, win_count, total_pnl, last_used)
                VALUES (?, 1, ?, ?, ?)
            """, (indicator_combo, 1 if won else 0, pnl, now))

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("update_signal_stat 失败: %s", e)
        raise
    finally:
        conn.close()


def get_signal_stats() -> list[dict]:
    """获取所有信号组合统计"""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM signal_stats ORDER BY used_count DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_signal_stats 失败: %s", e)
        return []


def record_round(
    action: str, summary: str,
    coin: str = "", btc_price: float = 0, eth_price: float = 0,
    market_snapshot: str = "",
) -> int:
    """记录每轮决策（包括 HOLD）"""
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO round_logs (timestamp, action, coin, btc_price, eth_price, summary, market_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            action, coin, btc_price, eth_price, summary, market_snapshot,
        ))
        rid = cur.lastrowid
        conn.commit()
        return rid
    except Exception as e:
        conn.rollback()
        logger.error("record_round 失败: %s", e)
        raise
    finally:
        conn.close()


def get_recent_rounds(n: int = 20, offset: int = 0) -> dict:
    """获取轮次日志（分页）"""
    try:
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM round_logs").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM round_logs ORDER BY id DESC LIMIT ? OFFSET ?", (n, offset)
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows], "total": total}
    except Exception as e:
        logger.error("get_recent_rounds 失败: %s", e)
        return {"items": [], "total": 0}


def record_review(
    review_type: str, content: str,
    stats_snapshot: str = "", key_findings: str = "",
) -> int:
    """记录复盘（daily / weekly）"""
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO reviews (timestamp, type, content, stats_snapshot, key_findings)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            review_type, content, stats_snapshot, key_findings,
        ))
        rid = cur.lastrowid
        conn.commit()
        return rid
    except Exception as e:
        conn.rollback()
        logger.error("record_review 失败: %s", e)
        raise
    finally:
        conn.close()


def get_reviews(n: int = 5, offset: int = 0) -> dict:
    """获取复盘记录（分页）"""
    try:
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY id DESC LIMIT ? OFFSET ?", (n, offset)
        ).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows], "total": total}
    except Exception as e:
        logger.error("get_reviews 失败: %s", e)
        return {"items": [], "total": 0}


# 初始化
init_db()
