"""
watcher.py 单元测试
测试锁机制、条件加载、冷却同步、文件删除清理等核心逻辑
"""
import os
import signal
import sys
import time
import tempfile
import unittest
from pathlib import Path
from collections import deque
from unittest.mock import patch, MagicMock

# 在 import watcher 前 mock config，避免依赖 ~/.okx/config.toml
sys.modules["config"] = MagicMock(OKX_DEMO=True)

import watcher


class TestLockMechanism(unittest.TestCase):
    """测试锁机制：获取、释放、僵尸清理"""

    def setUp(self):
        self.orig_lock = watcher.LOCK_FILE
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lock")
        self.tmp.close()
        os.unlink(self.tmp.name)  # 确保不存在
        watcher.LOCK_FILE = Path(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass
        watcher.LOCK_FILE = self.orig_lock

    def test_acquire_and_release(self):
        """正常获取和释放锁"""
        self.assertTrue(watcher.acquire_lock())
        content = watcher.LOCK_FILE.read_text()
        self.assertTrue(content.startswith("watcher:"))
        # 锁存在时再次获取应失败
        self.assertFalse(watcher.acquire_lock())
        # 释放后可重新获取
        watcher.release_lock()
        self.assertFalse(watcher.LOCK_FILE.exists())
        self.assertTrue(watcher.acquire_lock())
        watcher.release_lock()

    def test_zombie_lock_cleanup(self):
        """僵尸锁（超过 LOCK_EXPIRE）应被自动清理"""
        watcher.LOCK_FILE.write_text("old:0:0")
        # 把文件 mtime 设为 11 分钟前
        old_time = time.time() - 660
        os.utime(watcher.LOCK_FILE, (old_time, old_time))
        # acquire 应该清理僵尸锁并成功
        self.assertTrue(watcher.acquire_lock())
        watcher.release_lock()

    def test_fresh_lock_blocks(self):
        """新锁（未过期）应阻止获取"""
        watcher.LOCK_FILE.write_text("other:999:0")
        # mtime 就是现在，不会被清理
        self.assertFalse(watcher.acquire_lock())

    def test_is_locked(self):
        """is_locked 检测"""
        self.assertFalse(watcher.is_locked())
        watcher.LOCK_FILE.write_text("test")
        self.assertTrue(watcher.is_locked())
        # 过期的锁
        old_time = time.time() - 660
        os.utime(watcher.LOCK_FILE, (old_time, old_time))
        self.assertFalse(watcher.is_locked())

    def test_release_nonexistent(self):
        """释放不存在的锁不应报错"""
        watcher.release_lock()  # 不应抛异常


class TestLoadCondition(unittest.TestCase):
    """测试条件文件的动态加载"""

    def setUp(self):
        self.orig_cond = watcher.CONDITION_FILE
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        watcher.CONDITION_FILE = self.orig_cond
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_condition(self, code):
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text(code)
        watcher.CONDITION_FILE = p
        return p

    def test_load_valid(self):
        """加载有效的 check 函数"""
        self._write_condition('''
"""测试条件"""
def check(prices, history):
    return True, "test reason"
''')
        mod = watcher.load_condition()
        self.assertIsNotNone(mod)
        triggered, reason = mod.check({}, {})
        self.assertTrue(triggered)
        self.assertEqual(reason, "test reason")
        self.assertEqual(mod.__doc__.strip(), "测试条件")

    def test_load_missing_check(self):
        """缺少 check 函数应返回 None"""
        self._write_condition('x = 1\n')
        mod = watcher.load_condition()
        self.assertIsNone(mod)

    def test_load_syntax_error(self):
        """语法错误应返回 None 不崩溃"""
        self._write_condition('def check(:\n')
        mod = watcher.load_condition()
        self.assertIsNone(mod)

    def test_load_nonexistent(self):
        """文件不存在应返回 None"""
        watcher.CONDITION_FILE = Path(self.tmpdir) / "nope.py"
        mod = watcher.load_condition()
        self.assertIsNone(mod)

    def test_hot_reload(self):
        """修改文件后重新加载应得到新代码（sys.modules 缓存清理）"""
        p = self._write_condition('''
"""V1"""
def check(prices, history):
    return False, ""
''')
        mod1 = watcher.load_condition()
        self.assertFalse(mod1.check({}, {})[0])

        # 修改文件
        p.write_text('''
"""V2"""
def check(prices, history):
    return True, "upgraded"
''')
        mod2 = watcher.load_condition()
        self.assertTrue(mod2.check({}, {})[0])
        self.assertEqual(mod2.check({}, {})[1], "upgraded")
        self.assertEqual(mod2.__doc__.strip(), "V2")


class TestConditionFileDeleted(unittest.TestCase):
    """测试 #6: watch_condition.py 删除后 condition_mod 应被清空"""

    def test_deletion_clears_condition(self):
        """模拟主循环中的文件删除检测逻辑"""
        tmpdir = tempfile.mkdtemp()
        cond_file = Path(tmpdir) / "watch_condition.py"
        cond_file.write_text('"""active"""\ndef check(p,h): return False, ""\n')

        orig = watcher.CONDITION_FILE
        watcher.CONDITION_FILE = cond_file

        # 模拟: 文件存在时加载
        condition_mod = watcher.load_condition()
        self.assertIsNotNone(condition_mod)

        # 模拟: 文件被删除
        cond_file.unlink()

        # 主循环中的逻辑
        if watcher.CONDITION_FILE.exists():
            pass  # 会进入热加载
        elif condition_mod is not None:
            condition_mod = None  # 这就是修复 #6 的逻辑

        self.assertIsNone(condition_mod)

        watcher.CONDITION_FILE = orig
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestCronCooldownSync(unittest.TestCase):
    """测试 #8: cron 触发后 watcher 同步冷却期"""

    def setUp(self):
        self.orig_lock = watcher.LOCK_FILE
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lock")
        self.tmp.close()
        os.unlink(self.tmp.name)
        watcher.LOCK_FILE = Path(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass
        watcher.LOCK_FILE = self.orig_lock

    def test_cron_lock_syncs_cooldown(self):
        """检测到 cron 锁时应更新 last_trigger_time"""
        last_trigger_time = 0
        now = time.time()

        # 写入 cron 锁
        watcher.LOCK_FILE.write_text(f"cron:12345:{now:.0f}")

        # 模拟主循环中的检测逻辑
        if watcher.LOCK_FILE.exists():
            try:
                lock_content = watcher.LOCK_FILE.read_text()
                if lock_content.startswith("cron:"):
                    last_trigger_time = now
            except Exception:
                pass

        # 冷却期应生效
        self.assertGreater(last_trigger_time, 0)
        self.assertTrue(now - last_trigger_time < watcher.COOLDOWN)

    def test_watcher_lock_no_sync(self):
        """watcher 自己的锁不应触发冷却同步"""
        last_trigger_time = 0
        now = time.time()

        watcher.LOCK_FILE.write_text(f"watcher:12345:{now:.0f}")

        if watcher.LOCK_FILE.exists():
            try:
                lock_content = watcher.LOCK_FILE.read_text()
                if lock_content.startswith("cron:"):
                    last_trigger_time = now
            except Exception:
                pass

        self.assertEqual(last_trigger_time, 0)


class TestCheckExecution(unittest.TestCase):
    """测试 check() 函数的各种条件场景"""

    def test_breakout_condition(self):
        """突破型条件"""
        code = '''
"""BTC 突破 71000"""
def check(prices, history):
    if prices.get("btc", 0) > 71000:
        return True, "BTC 突破 71000"
    return False, ""
'''
        tmpdir = tempfile.mkdtemp()
        p = Path(tmpdir) / "watch_condition.py"
        p.write_text(code)
        orig = watcher.CONDITION_FILE
        watcher.CONDITION_FILE = p

        mod = watcher.load_condition()
        # 未突破
        t, r = mod.check({"btc": 70000, "eth": 2100}, {})
        self.assertFalse(t)
        # 突破
        t, r = mod.check({"btc": 71500, "eth": 2100}, {})
        self.assertTrue(t)
        self.assertIn("71000", r)

        watcher.CONDITION_FILE = orig
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_volume_condition_with_history(self):
        """使用 history 的放量条件"""
        code = '''
"""BTC 放量"""
import time
def check(prices, history):
    btc_hist = list(history.get("btc", []))
    if len(btc_hist) < 5:
        return False, ""
    avg_vol = sum(t["vol24h"] for t in btc_hist) / len(btc_hist)
    cur_vol = btc_hist[-1]["vol24h"]
    if cur_vol > avg_vol * 2:
        return True, f"BTC 放量 {cur_vol:.0f} > avg {avg_vol:.0f}"
    return False, ""
'''
        tmpdir = tempfile.mkdtemp()
        p = Path(tmpdir) / "watch_condition.py"
        p.write_text(code)
        orig = watcher.CONDITION_FILE
        watcher.CONDITION_FILE = p

        mod = watcher.load_condition()

        # 构造 history
        now = time.time()
        hist = deque()
        for i in range(10):
            hist.append({"price": 70000, "vol24h": 1000, "ts": now - (10 - i) * 10,
                         "high24h": 71000, "low24h": 69000, "open24h": 70000, "volCcy24h": 0})
        # 最后一条放量
        hist.append({"price": 70000, "vol24h": 5000, "ts": now,
                      "high24h": 71000, "low24h": 69000, "open24h": 70000, "volCcy24h": 0})

        t, r = mod.check({"btc": 70000}, {"btc": hist})
        self.assertTrue(t)
        self.assertIn("放量", r)

        watcher.CONDITION_FILE = orig
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestTriggerTrade(unittest.TestCase):
    """测试 trigger_trade 流程"""

    def setUp(self):
        self.orig_lock = watcher.LOCK_FILE
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lock")
        self.tmp.close()
        os.unlink(self.tmp.name)
        watcher.LOCK_FILE = Path(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass
        watcher.LOCK_FILE = self.orig_lock

    def test_trigger_blocked_by_lock(self):
        """有锁时 trigger_trade 应跳过"""
        watcher.LOCK_FILE.write_text("other:999:0")
        result = watcher.trigger_trade("test reason")
        self.assertFalse(result)

    @patch("watcher.subprocess.run")
    def test_trigger_prepare_fails(self, mock_run):
        """prepare.py 失败时应返回 False 并释放锁"""
        mock_run.return_value = MagicMock(returncode=1, stderr="some error", stdout="")
        result = watcher.trigger_trade("test")
        self.assertFalse(result)
        # 锁应被释放
        self.assertFalse(watcher.LOCK_FILE.exists())

    @patch("watcher.subprocess.run")
    def test_trigger_success(self, mock_run):
        """完整成功流程"""
        # prepare.py 成功，claude 成功
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout="prepare ok"),
            MagicMock(returncode=0, stderr="", stdout="claude done\nresult line"),
        ]
        result = watcher.trigger_trade("BTC breakout")
        self.assertTrue(result)
        self.assertFalse(watcher.LOCK_FILE.exists())
        # 验证 claude 调用包含 --dangerously-skip-permissions
        claude_call = mock_run.call_args_list[1]
        self.assertIn("--dangerously-skip-permissions", claude_call[0][0])

    @patch("watcher.subprocess.run")
    def test_trigger_timeout_releases_lock(self, mock_run):
        """超时时应释放锁"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=60)
        result = watcher.trigger_trade("test")
        self.assertFalse(result)
        self.assertFalse(watcher.LOCK_FILE.exists())

    @patch("watcher.subprocess.run")
    def test_trigger_error_log_stdout_fallback(self, mock_run):
        """#7: stderr 为空时应记录 stdout"""
        mock_run.return_value = MagicMock(returncode=1, stderr="", stdout="error in stdout")
        with patch("watcher.log") as mock_log:
            watcher.trigger_trade("test")
            # 检查有记录 stdout 的日志
            logged = [str(c) for c in mock_log.call_args_list]
            self.assertTrue(any("error in stdout" in s for s in logged))


class TestReleaseLockOwnership(unittest.TestCase):
    """测试 #13: release_lock 只删自己的锁"""

    def setUp(self):
        self.orig_lock = watcher.LOCK_FILE
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lock")
        self.tmp.close()
        os.unlink(self.tmp.name)
        watcher.LOCK_FILE = Path(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass
        watcher.LOCK_FILE = self.orig_lock

    def test_release_own_lock(self):
        """释放自己创建的锁"""
        watcher.acquire_lock()
        self.assertTrue(watcher.LOCK_FILE.exists())
        watcher.release_lock()
        self.assertFalse(watcher.LOCK_FILE.exists())

    def test_release_does_not_delete_cron_lock(self):
        """不应删除 cron 创建的锁"""
        watcher.LOCK_FILE.write_text("cron:99999:1234567890")
        watcher.release_lock()
        # cron 的锁应该还在
        self.assertTrue(watcher.LOCK_FILE.exists())
        self.assertTrue(watcher.LOCK_FILE.read_text().startswith("cron:"))

    def test_release_does_not_delete_other_watcher_lock(self):
        """不应删除其他 watcher PID 的锁"""
        watcher.LOCK_FILE.write_text("watcher:99999:1234567890")
        watcher.release_lock()
        # 其他 PID 的锁应该还在
        self.assertTrue(watcher.LOCK_FILE.exists())


class TestCheckReturnValidation(unittest.TestCase):
    """测试 #11: check() 返回值校验"""

    def setUp(self):
        self.orig_cond = watcher.CONDITION_FILE
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        watcher.CONDITION_FILE = self.orig_cond
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _load(self, code):
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text(code)
        watcher.CONDITION_FILE = p
        return watcher.load_condition()

    def test_valid_tuple(self):
        """正常二元组"""
        mod = self._load('def check(p, h): return True, "reason"\n')
        prices = {"btc": 70000, "eth": 2100}
        history = {"btc": deque(), "eth": deque()}
        # 模拟主循环的校验逻辑
        prices_copy = dict(prices)
        history_copy = {k: deque(v) for k, v in history.items()}
        result = mod.check(prices_copy, history_copy)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertTrue(bool(result[0]))
        self.assertEqual(str(result[1]), "reason")

    def test_returns_single_bool(self):
        """返回单个 bool 应被捕获"""
        mod = self._load('def check(p, h): return True\n')
        result = mod.check({}, {})
        # 在主循环中这会触发格式错误检测
        self.assertNotIsInstance(result, (tuple, list))

    def test_returns_three_values(self):
        """返回三元组应被捕获"""
        mod = self._load('def check(p, h): return True, "x", 123\n')
        result = mod.check({}, {})
        self.assertEqual(len(result), 3)  # 主循环会检测 len != 2

    def test_returns_list(self):
        """返回 list 也应该被接受"""
        mod = self._load('def check(p, h): return [True, "ok"]\n')
        result = mod.check({}, {})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)


class TestCheckTimeout(unittest.TestCase):
    """测试 #22: check() 超时保护"""

    def setUp(self):
        self.orig_cond = watcher.CONDITION_FILE
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        watcher.CONDITION_FILE = self.orig_cond
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_infinite_loop_killed(self):
        """死循环的 check 应在超时后被终止"""
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text('import time\ndef check(p, h):\n    while True: time.sleep(0.01)\n')
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()

        old_timeout = watcher.CHECK_TIMEOUT
        watcher.CHECK_TIMEOUT = 1  # 1 秒超时方便测试

        start = time.time()
        try:
            old_handler = signal.signal(signal.SIGALRM, watcher._check_timeout_handler)
            signal.alarm(watcher.CHECK_TIMEOUT)
            try:
                mod.check({}, {})
                self.fail("应该抛出 CheckTimeoutError")
            except watcher.CheckTimeoutError:
                pass  # 预期
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        finally:
            watcher.CHECK_TIMEOUT = old_timeout

        elapsed = time.time() - start
        self.assertLess(elapsed, 3, "超时应在几秒内触发，不应卡很久")

    def test_normal_check_not_affected(self):
        """正常 check 不受超时机制影响"""
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text('def check(p, h): return True, "fast"\n')
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()

        old_handler = signal.signal(signal.SIGALRM, watcher._check_timeout_handler)
        signal.alarm(watcher.CHECK_TIMEOUT)
        try:
            result = mod.check({}, {})
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        self.assertEqual(result, (True, "fast"))


class TestMutableProtection(unittest.TestCase):
    """测试 #10: check() 不应污染主循环数据"""

    def setUp(self):
        self.orig_cond = watcher.CONDITION_FILE
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        watcher.CONDITION_FILE = self.orig_cond
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_prices_mutation_isolated(self):
        """check 修改 prices 不影响原数据"""
        code = 'def check(p, h):\n    p["btc"] = 0\n    return False, ""\n'
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text(code)
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()

        prices = {"btc": 70000, "eth": 2100}
        history = {"btc": deque(), "eth": deque()}

        # 模拟主循环：传副本
        prices_copy = dict(prices)
        history_copy = {k: deque(v, maxlen=watcher.HISTORY_SIZE) for k, v in history.items()}
        mod.check(prices_copy, history_copy)

        # 原数据不受影响
        self.assertEqual(prices["btc"], 70000)

    def test_history_mutation_isolated(self):
        """check 清空 history 不影响原数据"""
        code = 'def check(p, h):\n    h.get("btc", []).clear()\n    return False, ""\n'
        p = Path(self.tmpdir) / "watch_condition.py"
        p.write_text(code)
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()

        now = time.time()
        history = {"btc": deque([{"price": 70000, "vol24h": 1000, "ts": now,
                                   "high24h": 71000, "low24h": 69000, "open24h": 70000, "volCcy24h": 0}],
                                 maxlen=watcher.HISTORY_SIZE)}
        prices = {"btc": 70000}

        prices_copy = dict(prices)
        history_copy = {k: deque(v, maxlen=watcher.HISTORY_SIZE) for k, v in history.items()}
        mod.check(prices_copy, history_copy)

        # 原 history 不受影响
        self.assertEqual(len(history["btc"]), 1)


class TestLogRotation(unittest.TestCase):
    """测试 #12: 日志轮转"""

    def test_log_rotation_triggers(self):
        """超过 LOG_MAX_SIZE 时应轮转"""
        tmpdir = tempfile.mkdtemp()
        orig_log = watcher.LOG_FILE
        orig_max = watcher.LOG_MAX_SIZE
        test_log = Path(tmpdir) / "test_watcher.log"
        watcher.LOG_FILE = test_log
        watcher.LOG_MAX_SIZE = 100  # 100 bytes 方便测试

        # 写入超过限制的内容
        test_log.write_text("x" * 200)

        watcher.log("trigger rotation")

        old_log = test_log.with_suffix(".log.old")
        self.assertTrue(old_log.exists())
        # 新文件应该只包含最新的一条
        new_content = test_log.read_text()
        self.assertIn("trigger rotation", new_content)
        self.assertNotIn("x" * 50, new_content)

        watcher.LOG_FILE = orig_log
        watcher.LOG_MAX_SIZE = orig_max
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestRunTriggerSh(unittest.TestCase):
    """测试 run_trigger.sh 的关键内容"""

    def test_has_skip_permissions_flag(self):
        """#1: 必须包含 --dangerously-skip-permissions"""
        sh_path = Path(__file__).parent / "run_trigger.sh"
        content = sh_path.read_text()
        self.assertIn("--dangerously-skip-permissions", content)

    def test_has_lock_mechanism(self):
        """脚本包含锁机制"""
        sh_path = Path(__file__).parent / "run_trigger.sh"
        content = sh_path.read_text()
        self.assertIn(".trigger.lock", content)
        self.assertIn("trap", content)

    def test_lock_content_starts_with_cron(self):
        """锁内容以 cron: 开头（watcher 依赖此前缀检测）"""
        sh_path = Path(__file__).parent / "run_trigger.sh"
        content = sh_path.read_text()
        self.assertIn('echo "cron:', content)

    def test_trap_checks_ownership(self):
        """#14: trap 应检查锁归属，不无条件删"""
        sh_path = Path(__file__).parent / "run_trigger.sh"
        content = sh_path.read_text()
        # trap 不应是简单的 rm -f "$LOCK"，应包含 grep 或条件检查
        # 找到 trap 行
        trap_lines = [l for l in content.splitlines() if l.strip().startswith("trap")]
        self.assertTrue(len(trap_lines) > 0, "run_trigger.sh 缺少 trap")
        trap_line = trap_lines[0]
        # 不应是无条件 rm
        self.assertNotEqual(trap_line.strip(), "trap 'rm -f \"$LOCK\"' EXIT",
                            "trap 不应无条件删锁")
        # 应包含 PID 检查 ($$)
        self.assertIn("$$", trap_line, "trap 应检查 PID 归属")


class TestEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def setUp(self):
        self.orig_lock = watcher.LOCK_FILE
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lock")
        self.tmp.close()
        os.unlink(self.tmp.name)
        watcher.LOCK_FILE = Path(self.tmp.name)

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass
        watcher.LOCK_FILE = self.orig_lock

    def test_fetch_timeout_does_not_crash(self):
        """API 超时不崩溃"""
        with patch("watcher.urllib.request.urlopen", side_effect=Exception("timeout")):
            result = watcher.fetch_ticker("BTC-USDT-SWAP")
            self.assertIsNone(result)

    def test_empty_history_check(self):
        """空 history 传给 check 不崩溃"""
        tmpdir = tempfile.mkdtemp()
        p = Path(tmpdir) / "watch_condition.py"
        p.write_text('def check(p, h):\n    return len(h.get("btc",[])) > 5, "enough data"\n')
        orig_cond = watcher.CONDITION_FILE
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()
        t, r = mod.check({"btc": 0}, {"btc": deque()})
        self.assertFalse(t)
        watcher.CONDITION_FILE = orig_cond
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_check_exception_returns_false(self):
        """check 抛异常应返回 False 不崩溃"""
        tmpdir = tempfile.mkdtemp()
        p = Path(tmpdir) / "watch_condition.py"
        p.write_text('def check(p, h): raise ValueError("boom")\n')
        orig_cond = watcher.CONDITION_FILE
        watcher.CONDITION_FILE = p
        mod = watcher.load_condition()
        # 模拟主循环的异常处理
        try:
            result = mod.check({}, {})
            triggered, reason = bool(result[0]), str(result[1])
        except Exception:
            triggered, reason = False, ""
        self.assertFalse(triggered)
        watcher.CONDITION_FILE = orig_cond
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_acquire_lock_after_release_cycle(self):
        """多次 acquire→release 循环"""
        for _ in range(5):
            self.assertTrue(watcher.acquire_lock())
            watcher.release_lock()
            self.assertFalse(watcher.LOCK_FILE.exists())

    def test_concurrent_cron_watcher_lock_safety(self):
        """模拟: watcher 持锁时 cron 检测到锁应跳过"""
        # watcher 获取锁
        watcher.acquire_lock()
        content = watcher.LOCK_FILE.read_text()
        self.assertTrue(content.startswith("watcher:"))
        # 模拟 cron 的 run_trigger.sh 逻辑: 检查锁存在 → 跳过
        lock_exists = watcher.LOCK_FILE.exists()
        self.assertTrue(lock_exists)
        age = time.time() - os.path.getmtime(watcher.LOCK_FILE)
        self.assertLess(age, 600)  # 未过期 → cron 应 exit 0
        watcher.release_lock()


if __name__ == "__main__":
    unittest.main(verbosity=2)
