# X/推特发布文案

---

科崽 参赛作品：《AI 自主交易员》#OKXAI松

让 AI 替你盯盘、分析、下单、复盘、进化策略——全程零人工。

每 30 分钟自动跑一轮：20+ 指标 × 4 时间框架分析 → 风控铁律检查 → MCP 下单 → 记录推理过程 → 每日自动复盘进化。

不是 if-else 信号机器人，是让 AI 像真人交易员一样思考和学习：哪些指标组合赚钱就多用，哪些亏钱就淘汰。

亮点：
• AI 完全自主决策，零硬编码策略
• 风控硬墙不可绕过（≤5%单笔/≤20%回撤/≤5x杠杆）
• 自我学习闭环，越跑越聪明
• 全透明 Dashboard，AI 推理过程可视化
• 看门狗 + Telegram 告警，生产级可靠

Claude Code + OKX Agent Trade Kit

GitHub: https://github.com/cyptokoz-svg/ai-autonomous-trader

#OKXAI松 #AIAgent #ClaudeCode #CryptoTrading

---

## 评论区放安装步骤：

1. 克隆项目
git clone https://github.com/cyptokoz-svg/ai-autonomous-trader.git

2. 安装依赖
pip install -r requirements.txt

3. 配置 OKX API（~/.okx/config.toml）

4. 安装 OKX MCP
npm install okx-trade-mcp

5. 启动 Dashboard
python3 dashboard_api.py
→ 打开 localhost:8888

6. 配合 Claude Code 自动交易
每 30 分钟 cron 触发即可

详见 GitHub README
