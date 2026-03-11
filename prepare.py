"""
AI 自主交易员 — 数据准备（一键拉取）
合并 data_engine + stats + 账户信息，一次输出完整报告
自动匹配模拟盘/实盘
智能控制报告体积：有持仓=详细模式，无持仓=精简模式

用法: python3 prepare.py
输出: latest_report.txt（AI 直接读取决策）
"""
import asyncio
import json
import os
from datetime import datetime, timezone

from pathlib import Path
from config import OKX_DEMO
from data_engine import DataEngine
from trade_db import get_stats, get_recent_trades, get_open_trades, get_signal_stats, get_recent_rounds

MEMORY_DIR = Path.home() / ".claude/projects/-Users-crypto/memory"
STATE_FILE = Path(__file__).parent / ".last_report_state.json"


def _load_last_state() -> dict:
    """读取上轮状态（用于增量判断）"""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    """保存本轮状态"""
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def _file_changed(path: Path, last_state: dict) -> bool:
    """检查文件是否有变化（基于修改时间）"""
    if not path.exists():
        return False
    mtime = os.path.getmtime(path)
    return mtime != last_state.get(str(path), 0)


def fetch_account_summary(has_positions: bool) -> str:
    """通过 trades.db 获取账户摘要"""
    stats = get_stats()
    open_trades = get_open_trades()

    lines = [f"## 账户 | {'模拟盘' if OKX_DEMO else '⚠️ 实盘'}"]

    if stats["total"] == 0:
        lines.append("暂无已平仓记录")
    else:
        recent = get_recent_trades(3)
        signals = get_signal_stats()
        lines.append(f"共{stats['total']}笔 胜率{stats['win_rate']:.0%} "
                     f"盈亏${stats['total_pnl']:.2f} "
                     f"盈亏因子{stats['profit_factor']} "
                     f"回撤{stats['max_drawdown_pct']:.1f}% "
                     f"连{stats['current_streak']}")

        if recent:
            for t in recent:
                pnl = t.get("pnl", 0) or 0
                lines.append(f"  近: {t['coin']} {t['side']} ${pnl:+.2f} ({t.get('close_reason', '')})")

        if signals:
            top = sorted(signals, key=lambda s: s.get("used_count", 0), reverse=True)[:3]
            for s in top:
                wr = s["win_count"] / s["used_count"] * 100 if s["used_count"] else 0
                lines.append(f"  信号: {s['indicator_combo']} {s['used_count']}次 {wr:.0f}% ${s['total_pnl']:.2f}")

    if open_trades:
        lines.append(f"持仓({len(open_trades)}):")
        for t in open_trades:
            lines.append(f"  {t['coin']} {t['side']} 入{t['entry_price']} "
                         f"SL:{t.get('stop_loss', '--')} TP:{t.get('take_profit', '--')} "
                         f"{t.get('leverage', '--')}x {t.get('sheets', '--')}张")
    else:
        lines.append("持仓: 无")

    return "\n".join(lines)


def fetch_trading_log(last_state: dict) -> str:
    """读取 trading-log.md（仅在文件有变化时输出）"""
    log_path = MEMORY_DIR / "trading-log.md"
    if not _file_changed(log_path, last_state):
        return ""
    if not log_path.exists():
        return ""
    content = log_path.read_text().strip()
    if not content or "暂无" in content:
        return ""
    return f"## 交易教训\n{content}\n"


def fetch_strategy_notes(last_state: dict) -> str:
    """读取 strategy-notes.md（仅在文件有变化时输出完整内容）"""
    notes_path = MEMORY_DIR / "strategy-notes.md"
    if not notes_path.exists():
        return ""
    content = notes_path.read_text().strip()
    if not content:
        return ""

    # 检查"当前有效规则"部分是否只有"暂无"
    if "当前有效规则" in content:
        parts = content.split("当前有效规则")
        if len(parts) > 1:
            section = parts[1].split("##")[0] if "##" in parts[1] else parts[1]
            if "暂无" in section and len(section.strip()) < 20:
                return ""

    # 文件没变化时只输出提醒，不重复全文
    if not _file_changed(notes_path, last_state):
        return "## 策略经验: 同上轮，未变化。请继续遵守已有规则。\n"

    return f"## 策略经验（必须参考）\n{content}\n"


def fetch_recent_context(has_positions: bool) -> str:
    """获取最近几轮的决策摘要"""
    n = 5 if has_positions else 3
    data = get_recent_rounds(n=n, offset=0)
    items = data.get("items", [])
    if not items:
        return ""

    lines = ["## 最近轮次", ""]
    for r in reversed(items):
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
    lines.append("⚠️ 上轮提到的价位/信号/条件，本轮必须跟进。")
    lines.append("")
    return "\n".join(lines)


async def main():
    mode = "模拟盘" if OKX_DEMO else "实盘"
    print(f"[{mode}] 正在拉取数据...")

    report_path = Path(__file__).parent / "latest_report.txt"
    last_state = _load_last_state()

    # 自动同步 Claude 记忆（DB → memory 文件）
    try:
        from stats import update_memory
        update_memory()
    except Exception as e:
        print(f"⚠️ 记忆同步跳过: {e}")

    # 检查是否有持仓
    open_trades = get_open_trades()
    has_positions = len(open_trades) > 0

    # 拉行情数据
    engine = DataEngine()
    try:
        await engine.update()
    except Exception as e:
        print(f"⚠️ 数据拉取异常: {e}")

    if not engine.is_ready:
        print("❌ 数据未就绪，请检查网络")
        if report_path.exists():
            report_path.unlink()
            print("⚠️ 已删除旧报告，防止 AI 基于过期数据决策")
        return

    # 合并报告
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# AI 交易员数据报告 — {now_str} | {mode}",
        "",
        fetch_recent_context(has_positions),
        fetch_strategy_notes(last_state),
        fetch_trading_log(last_state),
        engine.generate_report(),
        fetch_account_summary(has_positions),
    ]
    report = "\n".join(parts)

    try:
        with open(report_path, "w") as f:
            f.write(report)
    except IOError as e:
        print(f"❌ 写入报告失败: {e}")
        return

    # 保存本轮状态（记忆文件的 mtime）
    new_state = {}
    for name in ["strategy-notes.md", "trading-log.md"]:
        p = MEMORY_DIR / name
        if p.exists():
            new_state[str(p)] = os.path.getmtime(p)
    _save_state(new_state)

    # 打印摘要
    for pair in engine.pairs:
        tk = engine.get_ticker(pair)
        if tk:
            coin = pair.replace("-USDT-SWAP", "")
            chg = ((tk["last"] - tk["open24h"]) / tk["open24h"] * 100) if tk.get("open24h", 0) else 0
            print(f"  {coin}: ${tk['last']:,.1f} ({chg:+.2f}%)")

    print(f"✅ 报告已保存 latest_report.txt ({len(report)} 字符)")


if __name__ == "__main__":
    asyncio.run(main())
