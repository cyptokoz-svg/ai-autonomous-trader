#!/bin/bash
# cron 调用的触发脚本，带锁机制
# 与 watcher.py 共享 .trigger.lock，防止同时跑两个 AI 轮次

DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK="$DIR/.trigger.lock"
PYTHON="$DIR/venv/bin/python3"

# 检查锁
if [ -f "$LOCK" ]; then
    # 超过 10 分钟的锁视为僵尸
    age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || stat -f %m "$LOCK" 2>/dev/null) ))
    if [ "$age" -lt 600 ]; then
        echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] 跳过: 有其他轮次在跑 (锁已存在 ${age}s)"
        exit 0
    fi
    echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] 清理僵尸锁 (${age}s)"
    rm -f "$LOCK"
fi

# 加锁
echo "cron:$$:$(date +%s)" > "$LOCK"
trap 'grep -q "^cron:$$:" "$LOCK" 2>/dev/null && rm -f "$LOCK"' EXIT

# 执行
cd "$DIR"
$PYTHON prepare.py && claude --dangerously-skip-permissions -p trigger.md
