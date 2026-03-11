"""
AI 自主交易员 — 统计脚本
从 trades.db 读取数据，输出摘要给 AI 读

用法:
  python3 stats.py           → 输出统计摘要（喂给 AI）
  python3 stats.py --update  → 更新 memory 文件
"""
import sys
import json
from trade_db import get_stats, get_recent_trades, get_open_trades, get_signal_stats


def generate_summary() -> str:
    """生成统计摘要文本"""
    stats = get_stats()
    recent = get_recent_trades(5)
    open_trades = get_open_trades()
    signals = get_signal_stats()

    lines = ["## 交易统计摘要", ""]

    if stats["total"] == 0:
        lines.append("暂无已平仓交易记录")
        lines.append("")
    else:
        lines.append(f"### 核心指标")
        lines.append(f"- 总交易: {stats['total']}笔 (赢{stats['wins']} 亏{stats['losses']})")
        lines.append(f"- 胜率: {stats['win_rate']:.1%}")
        lines.append(f"- 总盈亏: ${stats['total_pnl']:.2f}")
        lines.append(f"- 盈亏比: {stats['pnl_ratio']:.2f}")
        lines.append(f"- 利润因子: {stats['profit_factor']:.2f}")
        lines.append(f"- 最大连亏: {stats['max_consecutive_loss']}笔")
        lines.append("")

        # 按币种
        lines.append(f"### 按币种")
        for coin, data in stats["by_coin"].items():
            wr = data["wins"] / data["total"] if data["total"] else 0
            lines.append(f"- {coin}: {data['total']}笔 胜率{wr:.0%} 盈亏${data['pnl']:.2f}")
        lines.append("")

        # 按方向
        lines.append(f"### 按方向")
        for side, data in stats["by_side"].items():
            wr = data["wins"] / data["total"] if data["total"] else 0
            lines.append(f"- {side}: {data['total']}笔 胜率{wr:.0%} 盈亏${data['pnl']:.2f}")
        lines.append("")

    # 未平仓
    if open_trades:
        lines.append(f"### 当前未平仓 ({len(open_trades)}笔)")
        for t in open_trades:
            lines.append(f"- #{t['id']} {t['coin']} {t['side']} @ {t['entry_price']} "
                         f"SL={t['stop_loss']} TP={t['take_profit']} "
                         f"({t['leverage']}x, {t['sheets']}张)")
        lines.append("")

    # 最近5笔
    if recent:
        lines.append(f"### 最近5笔交易")
        for t in recent:
            pnl_str = f"${t['pnl']:+.2f}" if t['pnl'] else "?"
            lines.append(f"- #{t['id']} {t['coin']} {t['side']} "
                         f"入{t['entry_price']}→出{t['exit_price']} "
                         f"{pnl_str} ({t['close_reason']})")
            if t.get("lessons"):
                lines.append(f"  教训: {t['lessons']}")
        lines.append("")

    # 信号统计
    if signals:
        lines.append(f"### 信号组合统计")
        for s in signals:
            wr = s["win_count"] / s["used_count"] if s["used_count"] else 0
            lines.append(f"- {s['indicator_combo']}: {s['used_count']}次 "
                         f"胜率{wr:.0%} 盈亏${s['total_pnl']:.2f}")
        lines.append("")

    return "\n".join(lines)


def update_memory():
    """更新 memory 文件中的统计数据"""
    from pathlib import Path

    memory_dir = Path.home() / ".claude/projects/-Users-crypto/memory"
    stats = get_stats()

    if stats["total"] == 0:
        print("暂无交易数据，无需更新")
        return

    # 更新 performance.md
    perf_path = memory_dir / "performance.md"
    content = f"""# 业绩追踪

> 自动更新，来源: trades.db

## 核心指标

| 指标 | 值 |
|------|-----|
| 总交易 | {stats['total']}笔 |
| 胜率 | {stats['win_rate']:.1%} |
| 总盈亏 | ${stats['total_pnl']:.2f} |
| 盈亏比 | {stats['pnl_ratio']:.2f} |
| 利润因子 | {stats['profit_factor']:.2f} |
| 最大连亏 | {stats['max_consecutive_loss']}笔 |
| 最佳单笔 | ${stats.get('best_trade', {}).get('pnl', 0):.2f} ({stats.get('best_trade', {}).get('coin', '--')}) |
| 最差单笔 | ${stats.get('worst_trade', {}).get('pnl', 0):.2f} ({stats.get('worst_trade', {}).get('coin', '--')}) |
"""

    # 按币种
    content += "\n## 按币种\n\n"
    for coin, data in stats["by_coin"].items():
        wr = data["wins"] / data["total"] if data["total"] else 0
        content += f"- {coin}: {data['total']}笔 胜率{wr:.0%} 盈亏${data['pnl']:.2f}\n"

    # 按方向
    content += "\n## 按方向\n\n"
    for side, data in stats["by_side"].items():
        wr = data["wins"] / data["total"] if data["total"] else 0
        content += f"- {side}: {data['total']}笔 胜率{wr:.0%} 盈亏${data['pnl']:.2f}\n"

    perf_path.write_text(content)

    # 更新 signal-scores.md
    signals = get_signal_stats()
    if signals:
        sig_path = memory_dir / "signal-scores.md"
        sig_content = "# 信号胜率统计\n\n> 自动更新，来源: trades.db\n\n"
        sig_content += "| 组合 | 使用次数 | 胜率 | 总盈亏 |\n"
        sig_content += "|------|---------|------|--------|\n"
        for s in signals:
            wr = s["win_count"] / s["used_count"] if s["used_count"] else 0
            sig_content += f"| {s['indicator_combo']} | {s['used_count']} | {wr:.0%} | ${s['total_pnl']:.2f} |\n"
        sig_path.write_text(sig_content)

    print("memory 文件已更新")


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_memory()
    else:
        print(generate_summary())
