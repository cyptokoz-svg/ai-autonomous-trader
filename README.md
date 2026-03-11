# AI Autonomous Trader

AI 驱动的加密货币自主交易系统，专注 BTC/ETH 永续合约。基于多时间框架技术分析，自主决策开平仓，持续自我学习进化。

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![OKX](https://img.shields.io/badge/Exchange-OKX-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 特性

- **全自主交易** — 每 30 分钟自动分析市场、决策、执行，无需人工干预
- **实时异动监控** — AI 每轮定义监控条件，watcher 常驻 10 秒轮询，突破/放量/异动秒级触发
- **多时间框架分析** — 日线(趋势) → 4H(中期) → 1H/15m(入场)，20+ 技术指标
- **硬编码风控** — 单笔亏损 ≤5%、最大回撤 ≤20%、杠杆 ≤5x、必须止损
- **持久记忆系统** — DB 量化数据自动同步到 Claude 记忆，跨会话保持认知，越跑越聪明
- **自我学习** — 每日/每周自动复盘，淘汰失效策略，进化有效规则
- **实时 Dashboard** — 权益曲线、持仓监控、AI 推理过程、信号胜率排名全透明（桌面 + 手机 PWA）
- **生产级可靠** — 锁机制防并发、超时保护、看门狗告警、Telegram 通知、数据库自动备份
- **模拟/实盘切换** — 一键切换 Demo/Live 模式

## 架构

```
┌──────────────────────────────────────────────────────┐
│         Dashboard (desktop + mobile PWA)             │
├──────────────────────────────────────────────────────┤
│              Dashboard API (Python)                  │  ← Cookie 认证
├───────────┬──────────┬───────────────────────────────┤
│ Data      │ Risk     │ Trade DB (SQLite)             │
│ Engine    │ Check    │ trades/rounds/signals/reviews  │
├───────────┴──────────┴───────────────────────────────┤
│                  触发层                               │
│  ┌─────────────┐    ┌──────────────────────┐         │
│  │ Cron 30min  │    │ Watcher (常驻10s轮询) │         │
│  │ run_trigger │◄──►│ watch_condition.py    │         │
│  │   .sh       │锁  │ (AI每轮生成)          │         │
│  └──────┬──────┘    └──────────┬───────────┘         │
│         └──────────┬───────────┘                     │
│                    ▼                                 │
│         prepare.py → claude -p trigger.md            │
│              ↓ 自动同步                               │
│         trades.db → Claude 记忆文件                   │
├──────────────────────────────────────────────────────┤
│              OKX API (MCP / REST)                    │
└──────────────────────────────────────────────────────┘
```

## 文件说明

| 文件 | 说明 |
|------|------|
| **核心流程** | |
| `trigger.md` | AI 触发 Prompt：每轮执行流程（含记忆同步指令） |
| `ai-trader-prompt.md` | AI 分析决策 Prompt：交易逻辑核心 |
| `prepare.py` | 智能报告生成 + 自动同步 DB → Claude 记忆 |
| `risk_check.py` | 风控硬检查：铁律不可被 AI 绕过 |
| **实时监控** | |
| `watcher.py` | 常驻价格监控：10s 轮询，AI 条件触发，锁机制防并发 |
| `run_trigger.sh` | Cron 触发脚本：带锁机制，与 watcher 协调 |
| `watch_condition.py` | AI 每轮生成的监控条件（动态覆盖） |
| **数据层** | |
| `data_engine.py` | 数据引擎：拉取 K 线 + 计算 20+ 技术指标 |
| `trade_db.py` | 数据库层：交易记录、轮次日志、信号统计、复盘 |
| `stats.py` | 统计报告 + 自动更新 Claude 记忆文件 |
| `config.py` | 全局配置：交易对、时间框架、EMA 参数 |
| **前端** | |
| `dashboard.html` | 桌面端仪表盘（单文件，含 CSS/JS） |
| `mobile.html` | 手机端 PWA（iPhone 适配，底部 Tab 导航） |
| `dashboard_api.py` | 后端 API + Cookie 登录认证 |
| **运维** | |
| `notify.py` | Telegram 通知：开仓/平仓/异常推送 |
| `watchdog.py` | 故障看门狗：系统停摆、孤儿持仓、API 告警 |
| `backup_db.py` | 数据库自动备份（保留最近 7 份） |
| `deploy.sh` | 云服务器一键部署脚本 |
| `test_watcher.py` | Watcher 单元测试（41 个用例） |

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/cyptokoz-svg/ai-autonomous-trader.git
cd ai-autonomous-trader
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 OKX API

创建 `~/.okx/config.toml`：

```toml
default_profile = "demo"

[profiles.demo]
api_key = "your-api-key"
secret_key = "your-secret-key"
passphrase = "your-passphrase"
demo = true

[profiles.live]
api_key = "your-live-api-key"
secret_key = "your-live-secret-key"
passphrase = "your-live-passphrase"
demo = false
```

> **API Key 存放在 `~/.okx/config.toml`，不在项目目录内，不会被提交。**

### 4. 启动 Dashboard

```bash
python3 dashboard_api.py
```

打开 http://localhost:8888 查看仪表盘。

### 5. 运行数据引擎（测试）

```bash
python3 data_engine.py
```

### 6. 安装 OKX MCP（Claude Code 交易接口）

本项目通过 [OKX Agent Trade Kit](https://github.com/anthropics/anthropic-quickstarts/tree/main/okx-trade) 的 MCP 协议让 Claude Code 直接操作 OKX 交易所。

```bash
# 创建 MCP 工作目录并安装
mkdir -p ~/Desktop/okx-trade && cd ~/Desktop/okx-trade
npm init -y
npm install okx-trade-mcp
```

配置 Claude Code MCP（编辑 `~/.claude/mcp.json`）：

```json
{
  "mcpServers": {
    "okx": {
      "command": "npx",
      "args": ["okx-trade-mcp", "--demo", "--modules", "swap,account,market"],
      "cwd": "/path/to/okx-trade"
    }
  }
}
```

> **模拟盘**: 使用 `--demo` 参数
> **实盘**: 去掉 `--demo` 参数

OKX API 凭证需配置在 `~/.okx/config.toml`（见步骤 3）。

### 7. 配合 Claude Code 自动交易

使用 [Claude Code](https://claude.ai) 实现自主交易循环：

```bash
# 设置 cron 定时触发（每 30 分钟）
crontab -e
*/30 * * * * ~/ai-autonomous-trader/run_trigger.sh >> ~/ai-autonomous-trader/cron.log 2>&1

# 启动实时异动监控（常驻后台）
tmux new -d -s watcher "cd ~/ai-autonomous-trader && python3 watcher.py"
```

`run_trigger.sh` 带锁机制，与 `watcher.py` 互斥，防止并发执行。

## 风控铁律

这些规则硬编码在 `risk_check.py` 中，AI **无法绕过**：

| 规则 | 限制 |
|------|------|
| 单笔亏损 | ≤ 5% 权益 |
| 最大回撤 | ≤ 20% |
| 杠杆倍数 | ≤ 5x |
| 同时持仓 | ≤ 3 个 |
| 允许币种 | BTC-USDT-SWAP, ETH-USDT-SWAP |
| 止损 | 必须设置 |
| 仓位比例 | ≤ 50% |

## Dashboard 功能

- 实时 BTC/ETH 价格 + 资金费率
- 今日 P&L 横幅
- 权益曲线图表
- 当前持仓（实时浮动盈亏）
- 交易历史（分页）
- AI 决策推理过程
- 信号组合胜率统计
- 每日/每周复盘记录
- 策略笔记
- 中英文切换
- Demo/Live 模式指示
- Cookie 登录认证（密码保护）
- 手机端 PWA（`mobile.html`，iPhone 适配，可添加到主屏幕）

## 模拟 ↔ 实盘切换

修改 `~/.okx/config.toml` 的 `default_profile`：

```toml
default_profile = "live"  # 切换到实盘
```

重启服务后 Dashboard 会自动显示当前模式（蓝色 DEMO / 红色 LIVE）。

## 技术栈

- **后端**: Python 3.11+, SQLite (WAL), aiohttp, pandas, pandas_ta
- **前端**: 原生 HTML/CSS/JS（零依赖，单文件）
- **交易所**: OKX API (REST + MCP)
- **AI**: Claude Code (Anthropic)

## 技术指标（20+）

| 类别 | 指标 |
|------|------|
| 趋势 | EMA(7/25/99), SMA(50/200), SuperTrend, MACD |
| 动量 | RSI, MFI, StochK/D, ROC |
| 波动 | ATR, ADX, Bollinger Bands |
| 量价 | OBV, CMF, 量比, VWAP |
| 支撑阻力 | Pivot Points (S1/P/R1) |
| 链上/盘口 | 资金费率(趋势), 多空持仓比, 盘口买卖比, OI |

AI 自由组合，实战数据反馈优胜劣汰。

## 免责声明

本项目仅供学习和研究目的。加密货币交易存在高风险，过去的表现不代表未来收益。使用本系统进行实盘交易的风险由用户自行承担。

## License

MIT
