"""
AI 自主交易员 — 风控硬检查
在 AI 决策之后、执行之前，用代码强制验证铁律
任何违规直接拒绝，不依赖 AI 自觉

用法: python3 risk_check.py '{"action":"buy_to_enter","coin":"BTC-USDT-SWAP",...}'
输出: PASS 或 REJECT + 原因
"""
import json
import sys
from trade_db import get_open_trades, get_stats

# ── 铁律 ──
MAX_SINGLE_LOSS_PCT = 0.05      # 单笔亏损 ≤ 5%
MAX_DRAWDOWN_PCT = 0.20         # 总回撤 ≤ 20%
MAX_LEVERAGE = 5                # 杠杆 ≤ 5x
MAX_POSITIONS = 3               # 同时持仓 ≤ 3
ALLOWED_COINS = [               # 只做主流币永续
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
]


def check_decision(decision: dict, equity: float) -> tuple[bool, str]:
    """
    检查 AI 决策是否违反铁律.
    返回 (通过, 原因)
    """
    action = decision.get("action", "hold")

    # hold 和 close 不需要检查
    if action in ("hold", "close"):
        return True, "OK"

    # ── 检查币种 ──
    coin = decision.get("coin", "")
    if coin not in ALLOWED_COINS:
        return False, f"REJECT: 币种 {coin} 不在允许列表 {ALLOWED_COINS}"

    # ── 检查杠杆 ──
    leverage = decision.get("leverage", 1)
    if leverage > MAX_LEVERAGE:
        return False, f"REJECT: 杠杆 {leverage}x > 上限 {MAX_LEVERAGE}x"

    # ── 检查单笔风险 ──
    risk_usd = decision.get("risk_usd", 0)
    if risk_usd and equity > 0:
        risk_pct = risk_usd / equity
        if risk_pct > MAX_SINGLE_LOSS_PCT:
            return False, f"REJECT: 单笔风险 ${risk_usd:.2f} = {risk_pct:.1%} > 上限 {MAX_SINGLE_LOSS_PCT:.0%}"

    # ── 检查仓位比例 ──
    size_pct = decision.get("position_size_pct", 0)
    if size_pct > 0.50:
        return False, f"REJECT: 仓位比例 {size_pct:.0%} > 50%，太大了"

    # ── 检查同时持仓数 ──
    open_trades = get_open_trades()
    if len(open_trades) >= MAX_POSITIONS:
        return False, f"REJECT: 已有 {len(open_trades)} 个持仓，上限 {MAX_POSITIONS}"

    # ── 检查是否重复开仓 ──
    for t in open_trades:
        if t["coin"] == coin:
            return False, f"REJECT: {coin} 已有持仓，不能重复开"

    # ── 检查总回撤（峰谷法，与 trade_db.get_stats 一致）──
    stats = get_stats()
    if stats["total"] > 0 and equity > 0:
        max_dd_pct = stats.get("max_drawdown_pct", 0)
        if max_dd_pct >= MAX_DRAWDOWN_PCT * 100:
            return False, f"REJECT: 最大回撤 {max_dd_pct:.1f}% ≥ {MAX_DRAWDOWN_PCT:.0%}，全停！"

    # ── 检查必须有止损 ──
    sl = decision.get("stop_loss", {})
    if not sl or not sl.get("price"):
        return False, "REJECT: 没有设止损！铁律：必须有止损"

    return True, "PASS: 所有风控检查通过"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 risk_check.py '<JSON决策>'")
        print("      python3 risk_check.py '<JSON决策>' <当前权益>")
        sys.exit(1)

    decision = json.loads(sys.argv[1])
    equity = float(sys.argv[2]) if len(sys.argv) > 2 else 3000.0

    passed, reason = check_decision(decision, equity)
    print(reason)
    sys.exit(0 if passed else 1)
