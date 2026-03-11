# AI Autonomous Trader — OKX AI 松第二期参赛作品

## 一句话介绍

**全自主 AI 交易员**：Claude + OKX Agent Trade Kit，从数据分析到下单执行到策略进化，全程零人工干预。

---

## 它能做什么？

每 30 分钟自动执行一轮完整交易决策：

```
拉数据 → 多时间框架分析 → 风控检查 → 开仓/平仓/观望 → 记录 → 复盘学习 → 策略进化
```

**不是简单的信号机器人**——它会自我学习：追踪哪些指标组合赚钱、哪些亏钱，每天复盘总结经验，每周淘汰失效策略，自主进化。

---

## 核心架构

```
Claude Code (AI 大脑)
    ↕ MCP 协议
OKX Agent Trade Kit (82个交易工具)
    ↕
┌──────────────────────────────┐
│  data_engine.py  数据引擎     │  20+ 技术指标 × 4 时间框架
│  risk_check.py   风控硬墙     │  铁律不可绕过
│  trade_db.py     交易数据库   │  SQLite 全量记录
│  dashboard.html  实时仪表盘   │  AI 推理过程可视化
│  watchdog.py     故障看门狗   │  Telegram 告警
│  notify.py       消息推送     │  开仓/平仓/异常通知
└──────────────────────────────┘
```

---

## 五大亮点

### 1. AI 完全自主决策

没有硬编码的交易策略。AI 自己看数据、自己判断、自己选择用哪些指标组合。从 20+ 指标中自由搭配（EMA、MACD、RSI、VWAP、CMF、Pivot Points...），根据实战表现自动优胜劣汰。

### 2. 风控铁律不可绕过

`risk_check.py` 是 AI 无法绕过的硬墙：
- 单笔亏损 ≤ 5% 权益
- 最大回撤 ≤ 20%
- 杠杆 ≤ 5x
- 必须设止损
- 同时持仓 ≤ 3 个

AI 有充分的交易自由，但在风险控制上零容忍。

### 3. 自我学习闭环

```
signal_stats 表追踪指标组合表现
         ↓
每日复盘：对比预期 vs 结果
         ↓
strategy-notes.md 更新策略经验
         ↓
下一轮 AI 读到新经验 → 决策进化
```

不是跑一套固定策略，而是**持续进化**的交易系统。

### 4. 全透明 Dashboard

单页面实时仪表盘（localhost:8888）：
- 权益曲线 + 实时持仓浮动盈亏
- AI 每笔交易的完整推理过程（为什么开仓、看了哪些指标、担心什么）
- 信号组合胜率排名
- 每日/每周复盘记录
- 中英文切换

### 5. 生产级可靠性

- **增量报告** — 只输出变化的内容，节省 token
- **灵活 MCP 调用** — 无持仓时跳过仓位查询
- **数据库事务** — 所有写操作 try/except + rollback
- **看门狗** — 独立进程监控系统健康，故障自动 Telegram 告警
- **自动备份** — 每日备份交易数据库

---

## 技术栈

| 组件 | 技术 |
|------|------|
| AI 大脑 | Claude Code (Anthropic) |
| 交易接口 | OKX Agent Trade Kit (MCP) |
| 数据引擎 | Python + pandas + pandas_ta |
| 数据库 | SQLite (WAL 模式) |
| 前端 | 原生 HTML/CSS/JS（零依赖） |
| 通知 | Telegram Bot API |

---

## 交易流程详解

**每 30 分钟一轮：**

1. `prepare.py` 拉取 BTC/ETH 行情 + 计算 20+ 指标 × 4 时间框架
2. MCP 查询账户余额、持仓状态
3. 有持仓 → 重新评估：当初开仓逻辑还成立吗？不成立就主动平仓
4. 读取历史经验（strategy-notes.md + 最近交易教训）
5. AI 多时间框架分析：日线定方向 → 4H 定趋势 → 1H/15m 找入场
6. `risk_check.py` 硬检查（不通过就不开仓）
7. 执行：MCP 调用 swap_set_leverage + swap_place_order
8. 记录到 trade_db（完整 reasoning + 指标组合）
9. 每日 00:00 UTC 自动复盘，提炼策略更新

---

## 可用指标（20+）

| 类别 | 指标 |
|------|------|
| 趋势 | EMA(7/25/99), SMA(50/200), SuperTrend, MACD |
| 动量 | RSI, MFI, StochK/D, ROC |
| 波动 | ATR, ADX, Bollinger Bands |
| 量价 | OBV, CMF, 量比, VWAP |
| 支撑阻力 | Pivot Points (S1/P/R1) |
| 链上 | 资金费率(趋势), 多空比, 盘口买卖比, OI |

AI 自由组合，实战数据反馈淘汰。

---

## GitHub

https://github.com/cyptokoz-svg/ai-autonomous-trader

---

## 免责声明

本项目仅供学习研究和比赛展示。加密货币交易存在高风险，使用本系统的风险由用户自行承担。
