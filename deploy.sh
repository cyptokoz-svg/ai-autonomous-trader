#!/bin/bash
# AI Autonomous Trader — 云服务器一键部署脚本
# 用法: 在 Ubuntu 22.04 服务器上执行
#   curl -sSL https://raw.githubusercontent.com/cyptokoz-svg/ai-autonomous-trader/main/deploy.sh | bash

set -e

echo "=== AI Autonomous Trader 部署 ==="

# 1. 系统依赖
echo "[1/6] 安装系统依赖..."
sudo apt update -qq
sudo apt install -y -qq python3-pip python3-venv git nodejs npm > /dev/null 2>&1

# 2. Claude Code
echo "[2/6] 安装 Claude Code..."
sudo npm install -g @anthropic-ai/claude-code > /dev/null 2>&1

# 3. 克隆项目
echo "[3/6] 克隆项目..."
cd ~
if [ -d "ai-autonomous-trader" ]; then
    cd ai-autonomous-trader && git pull
else
    git clone https://github.com/cyptokoz-svg/ai-autonomous-trader.git
    cd ai-autonomous-trader
fi

# 4. Python 虚拟环境 + 依赖
echo "[4/6] 安装 Python 依赖..."
python3 -m venv venv
source venv/bin/activate
pip install -q aiohttp pandas pandas_ta

# 5. OKX 配置检查
echo "[5/6] 检查配置..."
if [ ! -f ~/.okx/config.toml ]; then
    mkdir -p ~/.okx
    cat > ~/.okx/config.toml << 'TOML'
default_profile = "demo"

[profiles.demo]
api_key = "YOUR_API_KEY"
secret_key = "YOUR_SECRET_KEY"
passphrase = "YOUR_PASSPHRASE"
demo = true
TOML
    echo "⚠️  请编辑 ~/.okx/config.toml 填入你的 OKX API 凭证"
fi

# 6. 环境变量
echo "[6/6] 配置环境..."
grep -q "DASH_BIND" ~/.bashrc 2>/dev/null || echo 'export DASH_BIND="0.0.0.0"' >> ~/.bashrc
source ~/.bashrc

echo ""
echo "=== 部署完成 ==="
echo ""
echo "接下来手动执行："
echo "  1. 编辑 ~/.okx/config.toml 填入 API 凭证"
echo "  2. claude login  (登录 Claude Code)"
echo "  3. ~/ai-autonomous-trader/venv/bin/python3 ~/ai-autonomous-trader/dashboard_api.py &  (启动 Dashboard)"
echo "  4. 设置 cron:"
echo "     crontab -e"
echo "     */30 * * * * cd ~/ai-autonomous-trader && venv/bin/python3 prepare.py && claude -p trigger.md >> ~/trader.log 2>&1"
echo "     */10 * * * * cd ~/ai-autonomous-trader && venv/bin/python3 watchdog.py >> ~/watchdog.log 2>&1"
echo "     0 2 * * * cd ~/ai-autonomous-trader && venv/bin/python3 backup_db.py >> ~/backup.log 2>&1"
echo ""
echo "Dashboard: http://$(curl -s ifconfig.me):8888"
