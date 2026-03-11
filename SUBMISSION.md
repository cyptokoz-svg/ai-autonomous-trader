科崽 参赛作品：《AI 自主交易员》#OKXAI松
（安装步骤放评论区）

让 AI 替你盯盘、分析、下单、复盘、进化策略。每 30 分钟自动跑一轮完整交易决策：20+ 技术指标 × 4 时间框架多维分析，风控铁律锁死风险，交易完自动复盘总结经验，下一轮直接用上新学到的规律。全部交给 Claude Code + OKX Agent Trade Kit 这套 AI 自动化组合拳。

## 1. 它能做什么？

 • **全自主交易决策**：同时扫描 BTC/ETH 的日线、4H、1H、15m 四个时间框架，综合 EMA、MACD、RSI、VWAP、CMF、Pivot Points 等 20+ 指标，AI 自主判断开仓、平仓还是观望——没有硬编码策略，AI 自己选指标组合，自己决定怎么打。

 • **风控铁律不可绕过**：risk_check.py 是 AI 无法突破的硬墙——单笔亏损 ≤5% 权益、最大回撤 ≤20%、杠杆 ≤5x、必须设止损、同时持仓 ≤3 个。AI 有充分的交易自由，但在风险控制上零容忍。

 • **自我学习进化**：每笔交易记录完整推理过程（为什么开仓、看了哪些指标、担心什么），平仓后自动统计哪些指标组合赚钱、哪些亏钱。每天 UTC 00:00 自动复盘，淘汰失效策略，强化有效规则，写入经验笔记供下一轮读取——越跑越聪明。

 • **全透明 Dashboard**：单页面实时仪表盘，权益曲线、持仓浮动盈亏、AI 每笔推理过程、信号组合胜率排名、每日/每周复盘记录，全部可视化。支持中英文切换，Demo/Live 模式一键切换。

 • **生产级可靠性**：看门狗独立监控系统健康（停摆告警、孤儿持仓告警、API 可达性检测），Telegram 实时推送开仓/平仓/异常通知，数据库自动备份，增量报告节省 token。

## 2. 为什么选它？

 1. **真正的 AI 自主**：不是 if-else 信号机器人，是让 AI 像人类交易员一样思考——看盘、分析、决策、反思、进化。策略不是写死的，是 AI 自己从实战中学出来的。

 2. **闭环到底**：数据拉取 → AI 分析 → 风控检查 → MCP 下单 → 数据库记录 → 每日复盘 → 策略更新 → 下一轮读取新经验。不是做完分析让你手动操作，是从头到尾全自动。

 3. **安全可控**：风控硬编码无法绕过，所有交易记录完整留痕（包括 AI 的思考过程），持仓异常自动告警。AI 有自由但有边界。

 4. **即插即用**：基于 OKX Agent Trade Kit 的 MCP 协议，82 个交易工具开箱即用。模拟盘验证满意后，改一行配置切实盘。Dashboard 零依赖单文件，打开浏览器就能监控。

## 3. 核心架构

```
Claude Code (AI 大脑)
    ↕ MCP 协议
OKX Agent Trade Kit (82个交易工具)
    ↕
┌──────────────────────────────────┐
│  data_engine.py   数据引擎       │ 20+ 指标 × 4 时间框架
│  risk_check.py    风控硬墙       │ 铁律不可绕过
│  trade_db.py      交易数据库     │ SQLite 全量记录
│  prepare.py       智能报告       │ 增量输出省 token
│  dashboard.html   实时仪表盘     │ AI 推理可视化
│  watchdog.py      故障看门狗     │ Telegram 告警
│  notify.py        消息推送       │ 开仓/平仓/异常
└──────────────────────────────────┘
```

## 4. 可用指标（20+）

| 类别 | 指标 |
|------|------|
| 趋势 | EMA(7/25/99), SMA(50/200), SuperTrend, MACD |
| 动量 | RSI, MFI, StochK/D, ROC |
| 波动 | ATR, ADX, Bollinger Bands |
| 量价 | OBV, CMF, 量比, VWAP |
| 支撑阻力 | Pivot Points (S1/P/R1) |
| 链上/盘口 | 资金费率(趋势), 多空持仓比, 盘口买卖比, OI |

AI 自由组合，实战数据反馈优胜劣汰。

## 5. 技术栈

| 组件 | 技术 |
|------|------|
| AI 大脑 | Claude Code (Anthropic) |
| 交易接口 | OKX Agent Trade Kit (MCP 协议) |
| 数据引擎 | Python 3.11+ / pandas / pandas_ta |
| 数据库 | SQLite (WAL 模式) |
| 前端 | 原生 HTML/CSS/JS（零依赖单文件） |
| 通知 | Telegram Bot API |
| 监控 | watchdog.py 独立看门狗 |

GitHub: https://github.com/cyptokoz-svg/ai-autonomous-trader

#OKXAI松 #AIAgent #ClaudeCode #AgentTradeKit
