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

from config import OKX_DEMO
from data_engine import DataEngine
from trade_db import get_stats, get_recent_trades, get_open_trades, get_signal_stats


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
