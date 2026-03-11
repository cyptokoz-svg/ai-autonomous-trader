# 推文（280字内，可直接发）

科崽 参赛作品：《AI 自主交易员》#OKXAI松

Claude Code + OKX Agent Trade Kit，全自主 AI 交易系统

• 每30min自动分析 BTC/ETH，20+指标×4时间框架
• AI 自主决策开平仓，零硬编码策略
• 风控铁律不可绕过（5%单笔/20%回撤/5x杠杆）
• 每日自动复盘，淘汰亏钱策略，越跑越聪明
• Dashboard 全透明，AI推理过程可视化

不是信号机器人，是会自我进化的 AI 交易员

GitHub: github.com/cyptokoz-svg/ai-autonomous-trader

安装步骤见评论区

#AIAgent #ClaudeCode #CryptoTrading

---

# 评论1: 安装步骤

1⃣ git clone https://github.com/cyptokoz-svg/ai-autonomous-trader.git
2⃣ pip install -r requirements.txt
3⃣ 配置 OKX API (~/.okx/config.toml)
4⃣ npm install okx-trade-mcp
5⃣ python3 dashboard_api.py → 打开 localhost:8888
6⃣ Claude Code cron 每30min触发

详见 README

---

# 配图建议（用截图代替长文）

图1: Dashboard 整体概览
图2: AI 推理面板（展示reasoning）
图3: 信号统计胜率排名
图4: SUBMISSION.md 的架构图部分（截图）
