"""
AI 自主交易员 — 实时异动监控器
常驻运行，加载 AI 生成的 watch_condition.py，实时监控价格，条件满足时触发交易流程
不改任何现有逻辑，仅补充触发

锁机制：与 cron 共享 .trigger.lock，防止同时跑两个 AI 轮次

用法: python3 watcher.py  (tmux 后台运行)
"""
import json
import signal
import sys
import time
import os
import subprocess
import importlib.util
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from collections import deque
from config import OKX_DEMO

CHECK_TIMEOUT = 5  # check() 最多执行 5 秒


class CheckTimeoutError(Exception):
    pass


def _check_timeout_handler(signum, frame):
    raise CheckTimeoutError("check() 执行超时")

# ── 配置 ──
PAIRS = {"BTC-USDT-SWAP": "btc", "ETH-USDT-SWAP": "eth"}
POLL_INTERVAL = 10          # 每 10 秒拉一次价格
COOLDOWN = 600              # 触发后冷却 10 分钟
HISTORY_SIZE = 360          # 保留 1 小时历史（10s × 360）

PROJECT_DIR = Path(__file__).parent
CONDITION_FILE = PROJECT_DIR / "watch_condition.py"
LOCK_FILE = PROJECT_DIR / ".trigger.lock"
LOG_FILE = Path.home() / "watcher.log"
LOG_MAX_SIZE = 5 * 1024 * 1024  # 5MB 后轮转
VENV_PYTHON = PROJECT_DIR / "venv" / "bin" / "python3"
LOCK_EXPIRE = 600           # 锁超过 10 分钟视为僵尸锁，自动清理


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        # 日志轮转：超过 LOG_MAX_SIZE 时重命名为 .old
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE:
            old = LOG_FILE.with_suffix(".log.old")
            LOG_FILE.rename(old)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── 锁 ──
def acquire_lock():
    """尝试获取锁，成功返回 True"""
    # 清理僵尸锁
    if LOCK_FILE.exists():
        try:
            age = time.time() - os.path.getmtime(LOCK_FILE)
            if age > LOCK_EXPIRE:
                log(f"🔓 清理僵尸锁 (已存在 {age:.0f}s)")
                LOCK_FILE.unlink()
            else:
                return False
        except Exception:
            return False
    try:
        LOCK_FILE.write_text(f"watcher:{os.getpid()}:{time.time():.0f}")
        return True
    except Exception:
        return False


def release_lock():
    """只释放自己创建的锁，不误删 cron 的锁"""
    try:
        if LOCK_FILE.exists():
            content = LOCK_FILE.read_text()
            if content.startswith(f"watcher:{os.getpid()}:"):
                LOCK_FILE.unlink()
    except Exception:
        pass


def is_locked():
    """检查是否有其他进程在跑"""
    if not LOCK_FILE.exists():
        return False
    try:
        age = time.time() - os.path.getmtime(LOCK_FILE)
        return age < LOCK_EXPIRE
    except Exception:
        return False


# ── 价格拉取 ──
def fetch_ticker(pair):
    headers = {"User-Agent": "Mozilla/5.0"}
    if OKX_DEMO:
        headers["x-simulated-trading"] = "1"
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={pair}"
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        if data.get("data"):
            t = data["data"][0]
            return {
                "price": float(t.get("last", 0)),
                "vol24h": float(t.get("vol24h", 0)),
                "volCcy24h": float(t.get("volCcy24h", 0)),
                "high24h": float(t.get("high24h", 0)),
                "low24h": float(t.get("low24h", 0)),
                "open24h": float(t.get("open24h", 0)),
                "ts": time.time(),
            }
    except Exception as e:
        log(f"⚠️ 拉取 {pair} 失败: {e}")
    return None


# ── 条件加载 ──
def load_condition():
    """动态加载 AI 生成的 watch_condition.py"""
    if not CONDITION_FILE.exists():
        return None
    try:
        # 清理缓存，确保每次加载最新代码
        sys.modules.pop("watch_condition", None)
        spec = importlib.util.spec_from_file_location("watch_condition", CONDITION_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "check"):
            return mod
        log("⚠️ watch_condition.py 缺少 check() 函数")
    except Exception as e:
        log(f"⚠️ 加载 watch_condition.py 失败: {e}")
    return None


# ── 触发交易 ──
def trigger_trade(reason):
    """获取锁 → prepare.py → claude -p trigger.md → 释放锁"""
    if not acquire_lock():
        log(f"⏸️ 跳过触发（有其他轮次在跑）: {reason}")
        return False

    log(f"🚨 触发交易! 原因: {reason}")
    try:
        python = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"

        # Step 1: prepare.py
        log("  → prepare.py ...")
        r1 = subprocess.run(
            [python, "prepare.py"],
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True, timeout=60,
        )
        if r1.returncode != 0:
            err = r1.stderr[:200] or r1.stdout[:200]
            log(f"  ❌ prepare.py 失败: {err}")
            return False
        log("  ✅ prepare.py 完成")

        # Step 2: claude -p trigger.md
        log("  → claude -p trigger.md ...")
        r2 = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "-p", "trigger.md"],
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True, timeout=300,
            env=os.environ.copy(),
        )
        if r2.returncode != 0:
            log(f"  ❌ claude 失败: {r2.stderr[:200]}")
            return False
        lines = r2.stdout.strip().split("\n")
        summary = "\n".join(lines[-5:]) if len(lines) > 5 else r2.stdout.strip()
        log(f"  ✅ 完成:\n{summary}")
        return True

    except subprocess.TimeoutExpired:
        log("  ❌ 执行超时")
        return False
    except Exception as e:
        log(f"  ❌ 异常: {e}")
        return False
    finally:
        release_lock()


# ── 主循环 ──
def main():
    log("=" * 50)
    log("👁️ AI 自主监控器启动")
    log(f"   监控: {', '.join(PAIRS.keys())}")
    log(f"   轮询: {POLL_INTERVAL}s | 冷却: {COOLDOWN}s")
    log(f"   模式: {'模拟盘' if OKX_DEMO else '⚠️ 实盘'}")
    log("=" * 50)

    history = {coin: deque(maxlen=HISTORY_SIZE) for coin in PAIRS.values()}
    prices = {coin: 0.0 for coin in PAIRS.values()}

    last_trigger_time = 0
    condition_mod = None
    condition_mtime = 0
    heartbeat = 0  # 每 5 分钟打印一次心跳

    while True:
        try:
            now = time.time()

            # 拉取价格
            for pair, coin in PAIRS.items():
                tick = fetch_ticker(pair)
                if not tick:
                    continue
                prices[coin] = tick["price"]
                history[coin].append(tick)

            # 心跳日志（每 5 分钟）
            if now - heartbeat > 300:
                heartbeat = now
                btc_str = f"${prices['btc']:,.0f}" if prices['btc'] else "--"
                eth_str = f"${prices['eth']:,.0f}" if prices['eth'] else "--"
                cond_str = condition_mod.__doc__.strip() if condition_mod and condition_mod.__doc__ else "无"
                locked = "🔒" if is_locked() else "🟢"
                log(f"💓 BTC:{btc_str} ETH:{eth_str} | 条件:{cond_str} | {locked}")

            # 热加载 watch_condition.py
            if CONDITION_FILE.exists():
                mtime = os.path.getmtime(CONDITION_FILE)
                if mtime != condition_mtime:
                    new_mod = load_condition()
                    if new_mod:
                        condition_mod = new_mod
                        condition_mtime = mtime
                        desc = condition_mod.__doc__.strip() if condition_mod.__doc__ else "无描述"
                        log(f"📋 新监控条件已加载: {desc}")
            elif condition_mod is not None:
                # 文件被删除，清空条件
                condition_mod = None
                condition_mtime = 0
                log("📋 watch_condition.py 已删除，停止监控条件")

            # 检测 cron 触发：读取锁内容，如果是 cron 的锁则同步冷却期
            if LOCK_FILE.exists():
                try:
                    lock_content = LOCK_FILE.read_text()
                    if lock_content.startswith("cron:"):
                        last_trigger_time = now
                except Exception:
                    pass

            # 冷却 / 锁定 / 无条件 → 跳过
            if now - last_trigger_time < COOLDOWN:
                time.sleep(POLL_INTERVAL)
                continue
            if is_locked():
                time.sleep(POLL_INTERVAL)
                continue
            if not condition_mod:
                time.sleep(POLL_INTERVAL)
                continue

            # 执行 check()（传副本，防止 AI 代码污染主循环数据；带超时保护）
            try:
                prices_copy = dict(prices)
                history_copy = {k: deque(v, maxlen=HISTORY_SIZE) for k, v in history.items()}
                old_handler = signal.signal(signal.SIGALRM, _check_timeout_handler)
                signal.alarm(CHECK_TIMEOUT)
                try:
                    result = condition_mod.check(prices_copy, history_copy)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
                if not isinstance(result, (tuple, list)) or len(result) != 2:
                    log(f"⚠️ check() 返回值格式错误: {type(result).__name__}，应返回 (bool, str)")
                    triggered, reason = False, ""
                else:
                    triggered, reason = bool(result[0]), str(result[1])
            except CheckTimeoutError:
                log(f"⚠️ check() 执行超过 {CHECK_TIMEOUT}s，已终止。请检查 watch_condition.py")
                triggered, reason = False, ""
            except Exception as e:
                log(f"⚠️ check() 出错: {e}")
                triggered, reason = False, ""

            if triggered and reason:
                last_trigger_time = now
                trigger_trade(reason)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log("监控器停止")
            break
        except Exception as e:
            log(f"⚠️ 主循环异常: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
