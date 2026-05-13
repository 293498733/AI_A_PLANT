"""Tests for pipeline/watchdog.py — process watchdog with tree kill."""

import sys
import time
import subprocess
import pytest
from pipeline.watchdog import ProcessWatchdog, WatchdogTimeout


class TestProcessWatchdog:
    """Test the process watchdog timer and kill mechanism."""

    def test_watchdog_does_not_trigger_when_cancelled(self):
        """Watchdog should not fire if cancelled before timeout."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(3)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        wd = ProcessWatchdog(proc.pid, 10)
        wd.start()
        proc.wait()
        wd.cancel()
        assert not wd.triggered
        assert proc.returncode == 0

    def test_watchdog_triggers_on_timeout(self):
        """Watchdog should kill the process after timeout."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
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

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        wd = ProcessWatchdog(proc.pid, 1, on_timeout=_cb)
        wd.start()
        proc.wait()
        time.sleep(0.5)  # Allow Timer thread to execute callback
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
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
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
