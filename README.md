# AI Autonomous Trader

AI 驱动的加密货币自主交易系统，专注 BTC/ETH 永续合约。基于多时间框架技术分析，自主决策开平仓，持续自我学习进化。

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![OKX](https://img.shields.io/badge/Exchange-OKX-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 特性

- **全自主交易** — 每 30 分钟自动分析市场、决策、执行，无需人工干预
- **多时间框架分析** — 日线(趋势) → 4H(中期) → 1H/15m(入场)
- **硬编码风控** — 单笔亏损 ≤5%、最大回撤 ≤20%、杠杆 ≤5x、必须止损
- **自我学习** — 每日/每周自动复盘，淘汰失效策略，进化有效规则
- **实时 Dashboard** — 单页面仪表盘，权益曲线、持仓监控、AI 推理过程全透明
- **模拟/实盘切换** — 一键切换 Demo/Live 模式

## 架构

```
┌─────────────────────────────────────────────┐
│              Dashboard (HTML)                │  ← localhost:8888
├─────────────────────────────────────────────┤
│            Dashboard API (Python)            │  ← HTTP Server
├──────────┬──────────┬───────────────────────┤
│ Data     │ Risk     │ Trade DB              │
│ Engine   │ Check    │ (SQLite)              │
├──────────┴──────────┴───────────────────────┤
│          OKX API (MCP / REST)               │
└─────────────────────────────────────────────┘
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `dashboard.html` | 前端仪表盘（单文件，含 CSS/JS） |
| `dashboard_api.py` | 后端 API 服务器，端口 8888 |
| `data_engine.py` | 数据引擎：拉取 K 线 + 计算技术指标 |
| `trade_db.py` | 数据库层：交易记录、轮次日志、复盘 |
| `risk_check.py` | 风控硬检查：铁律不可被 AI 绕过 |
| `stats.py` | 统计报告生成 |
| `config.py` | 全局配置：交易对、时间框架、EMA 参数 |
| `trigger.md` | AI 触发 Prompt：每轮执行流程 |

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
# 每 30 分钟由 cron 触发 Claude Code，执行 trigger.md 中的完整流程
# 示例 crontab:
*/30 * * * * cd ~/Desktop/ai-autonomous-trader && claude -p trigger.md
```

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

## 免责声明

本项目仅供学习和研究目的。加密货币交易存在高风险，过去的表现不代表未来收益。使用本系统进行实盘交易的风险由用户自行承担。

## License

MIT
