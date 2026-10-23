"""Tests for pipeline/watchdog.py — process watchdog with tree kill."""

import os
import signal
import sys
import time
import subprocess
import pytest
from pipeline.watchdog import ProcessWatchdog, WatchdogTimeout


def _spawn_sleeper(seconds: int):
    """启动 sleep 子进程；POSIX 下独立会话，与生产 `_spawn` 行为一致。"""
    kwargs = {} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({seconds})"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **kwargs,
    )


class TestProcessWatchdog:
    """Test the process watchdog timer and kill mechanism."""

    def test_watchdog_does_not_trigger_when_cancelled(self):
        """Watchdog should not fire if cancelled before timeout."""
        proc = _spawn_sleeper(3)
        wd = ProcessWatchdog(proc.pid, 10)
        wd.start()
        proc.wait()
        wd.cancel()
        assert not wd.triggered
        assert proc.returncode == 0

    def test_watchdog_triggers_on_timeout(self):
        """Watchdog should kill the process after timeout."""
        proc = _spawn_sleeper(60)
        wd = ProcessWatchdog(proc.pid, 1)
        wd.start()
        proc.wait()
        wd.cancel()
        assert wd.triggered
        assert proc.returncode != 0

    def test_watchdog_calls_on_timeout_callback(self):
        """on_timeout should be called when watchdog fires."""
        callback_called = []

        def _cb():
            callback_called.append(True)

        proc = _spawn_sleeper(60)
        wd = ProcessWatchdog(proc.pid, 1, on_timeout=_cb)
        wd.start()
        proc.wait()
        # 回调在杀进程之后执行；Windows 下 taskkill 二次确认最长等待 5 秒，
        # 固定 sleep 会抖动，这里轮询等待回调。
        deadline = time.time() + 15
        while not callback_called and time.time() < deadline:
            time.sleep(0.05)
        wd.cancel()
        assert wd.triggered
        assert len(callback_called) == 1

    def test_watchdog_start_cancel_no_trigger(self):
        """Cancel before timer fires should prevent trigger."""
        wd = ProcessWatchdog(99999, 3600)  # PID unlikely to exist, long timeout
        wd.start()
        wd.cancel()
        assert not wd.triggered

    def test_watchdog_triggered_flag(self):
        """triggered flag should be False before timeout, True after."""
        proc = _spawn_sleeper(60)
        wd = ProcessWatchdog(proc.pid, 1)
        assert not wd.triggered
        wd.start()
        proc.wait()
        assert wd.triggered
        wd.cancel()

    def test_watchdog_timeout_exception_contains_pid(self):
        """WatchdogTimeout exception should include pid and timeout."""
        exc = WatchdogTimeout(pid=12345, timeout_seconds=900)
        assert "12345" in str(exc)
        assert "900" in str(exc)

    def test_watchdog_handles_already_dead_process(self):
        """Watchdog should not crash when process is already dead."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "exit(0)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        proc.wait()
        time.sleep(0.2)
        # Process is dead, watchdog should handle gracefully
        wd = ProcessWatchdog(proc.pid, 0)  # Immediate timeout
        wd.start()
        time.sleep(0.5)
        assert wd.triggered
        # Should not raise


class TestUnixKill:
    """_kill_unix 的进程组判定 — 直接影响是否会误杀调用方（管线自身）。

    直接调用 _kill_unix 以绕过 sys.platform 分支，使用例在 Windows 上也可运行；
    os.getpgid / os.killpg 在 Windows 不存在，故 setattr 需 raising=False。
    """

    @pytest.fixture(autouse=True)
    def _sigkill(self, monkeypatch):
        # Windows 无 signal.SIGKILL；被测代码只在 POSIX 分支用到它，补桩即可跨平台运行
        monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)

    def test_killpg_when_target_is_group_leader(self, monkeypatch):
        wd = ProcessWatchdog(1234, 10)
        calls = []
        monkeypatch.setattr(os, "getpgid", lambda pid: pid, raising=False)
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: calls.append(("killpg", pgid)), raising=False)
        monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(("kill", pid)), raising=False)
        wd._kill_unix()
        assert calls == [("killpg", 1234)]

    def test_kill_pid_only_when_not_group_leader(self, monkeypatch):
        """目标进程组 ID 与自身 PID 不同时，只能杀该 PID。

        killpg 会命中整个进程组；若目标不是组长（pytest 下启动的普通子进程），
        连带杀掉的会是调用方 —— 即管线自杀。
        """
        wd = ProcessWatchdog(1234, 10)
        calls = []
        monkeypatch.setattr(os, "getpgid", lambda pid: 999, raising=False)
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: calls.append(("killpg", pgid)), raising=False)
        monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(("kill", pid)), raising=False)
        wd._kill_unix()
        assert calls == [("kill", 1234)]

    def test_kill_pid_when_getpgid_fails(self, monkeypatch):
        """进程已退出导致 getpgid 抛错时，退化为按 PID 终止。"""
        wd = ProcessWatchdog(1234, 10)
        calls = []

        def _raise(pid):
            raise ProcessLookupError(pid)

        monkeypatch.setattr(os, "getpgid", _raise, raising=False)
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: calls.append(("killpg", pgid)), raising=False)
        monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append(("kill", pid)), raising=False)
        wd._kill_unix()
        assert calls == [("kill", 1234)]
