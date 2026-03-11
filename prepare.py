"""
AI 自主交易员 — 数据准备（一键拉取）
合并 data_engine + stats + 账户信息，一次输出完整报告
自动匹配模拟盘/实盘

用法: python3 prepare.py
输出: latest_report.txt（AI 直接读取决策）
"""
import asyncio
import json
import urllib.request
from datetime import datetime, timezone

from pathlib import Path
from config import OKX_DEMO
from data_engine import DataEngine
from trade_db import get_stats, get_recent_trades, get_open_trades, get_signal_stats, get_recent_rounds

MEMORY_DIR = Path.home() / ".claude/projects/-Users-crypto/memory"


def fetch_account_summary() -> str:
    """通过 trades.db 获取账户摘要（余额由 MCP 查，这里只出统计）"""
    stats = get_stats()
    open_trades = get_open_trades()
    recent = get_recent_trades(3)
    signals = get_signal_stats()

    lines = ["## 账户 & 交易统计", ""]
    lines.append(f"- 模式: {'模拟盘' if OKX_DEMO else '⚠️ 实盘'}")
    lines.append("")

    if stats["total"] == 0:
        lines.append("暂无已平仓交易记录")
    else:
        lines.append("### 核心指标")
        lines.append(f"- 总交易: {stats['total']}笔 (赢{stats['wins']} 亏{stats['losses']})")
        lines.append(f"- 胜率: {stats['win_rate']:.1%}")
        lines.append(f"- 总盈亏: ${stats['total_pnl']:.2f}")
        lines.append(f"- 盈亏因子: {stats['profit_factor']}")
        lines.append(f"- 最大回撤: ${stats['max_drawdown']:.2f} ({stats['max_drawdown_pct']:.1f}%)")
        lines.append(f"- 当前连胜/连亏: {stats['current_streak']}")
        lines.append("")

        if recent:
            lines.append("### 最近3笔")
            for t in recent:
                pnl = t.get("pnl", 0) or 0
                lines.append(f"- {t['coin']} {t['side']} → ${pnl:+.2f} ({t.get('close_reason', '')})")
            lines.append("")

    if open_trades:
        lines.append(f"### 当前持仓 ({len(open_trades)}个)")
        for t in open_trades:
            lines.append(f"- {t['coin']} {t['side']} 入场{t['entry_price']} "
                         f"SL:{t.get('stop_loss', '--')} TP:{t.get('take_profit', '--')} "
                         f"杠杆{t.get('leverage', '--')}x {t.get('sheets', '--')}张")
        lines.append("")
    else:
        lines.append("### 当前持仓: 无")
        lines.append("")

    if signals:
        top = sorted(signals, key=lambda s: s.get("used_count", 0), reverse=True)[:3]
        if top:
            lines.append("### 信号组合 Top 3")
            for s in top:
                wr = s["win_count"] / s["used_count"] * 100 if s["used_count"] else 0
                lines.append(f"- {s['indicator_combo']}: 用{s['used_count']}次 胜率{wr:.0f}% 盈亏${s['total_pnl']:.2f}")
            lines.append("")

    return "\n".join(lines)


def fetch_trading_log() -> str:
    """读取 trading-log.md，最近5笔交易的关键教训"""
    log_path = MEMORY_DIR / "trading-log.md"
    if not log_path.exists():
        return ""
    content = log_path.read_text().strip()
    if not content or "暂无" in content:
        return ""
    return f"## 最近交易教训（避免重蹈覆辙）\n\n{content}\n"


def fetch_strategy_notes() -> str:
    """读取 strategy-notes.md，AI 的核心经验库"""
    notes_path = MEMORY_DIR / "strategy-notes.md"
    if not notes_path.exists():
        return ""
    content = notes_path.read_text().strip()
    if not content or "暂无" in content.split("当前有效规则")[1].split("##")[0] if "当前有效规则" in content else True:
        return ""
    return f"## 你的策略经验（必须参考）\n\n{content}\n"


def fetch_recent_context() -> str:
    """获取最近几轮的决策摘要，让 AI 知道上轮留下了什么观察"""
    data = get_recent_rounds(n=5, offset=0)
    items = data.get("items", [])
    if not items:
        return ""

    lines = ["## 最近轮次记录（你上几轮的决策，请关联）", ""]
    for r in reversed(items):  # 从旧到新
        ts = r.get("timestamp", "")[:16]
        action = r.get("action", "")
        summary = r.get("summary", "")
        btc = r.get("btc_price", 0)
        eth = r.get("eth_price", 0)
        prices = f"BTC:{btc:.0f} ETH:{eth:.1f}" if btc else ""
        lines.append(f"- [{ts}] **{action}** {prices}")
        if summary:
            lines.append(f"  > {summary}")
    lines.append("")
    lines.append("⚠️ 如果上轮提到了要关注的价位/信号/条件，本轮必须跟进检查是否成立。")
    lines.append("")
    return "\n".join(lines)


async def main():
    mode = "模拟盘" if OKX_DEMO else "实盘"
    print(f"[{mode}] 正在拉取数据...")

    # 并行: 行情数据 + 统计
    engine = DataEngine()
    await engine.update()

    if not engine.is_ready:
        print("❌ 数据未就绪，请检查网络")
        return

    # 合并报告
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# AI 交易员数据报告 — {now_str}",
        f"# 模式: {mode}",
        "",
        fetch_recent_context(),
        fetch_strategy_notes(),
        fetch_trading_log(),
        engine.generate_report(),
        fetch_account_summary(),
    ]
    report = "\n".join(parts)

    with open("latest_report.txt", "w") as f:
        f.write(report)

    # 打印摘要（不打印完整报告，太长）
    # 提取关键价格
    for pair in engine.pairs:
        tk = engine.get_ticker(pair)
        if tk:
            coin = pair.replace("-USDT-SWAP", "")
            chg = ((tk["last"] - tk["open24h"]) / tk["open24h"] * 100) if tk.get("open24h") else 0
            print(f"  {coin}: ${tk['last']:,.1f} ({chg:+.2f}%)")

    print(f"✅ 报告已保存 latest_report.txt ({len(report)} 字符)")


if __name__ == "__main__":
    asyncio.run(main())
