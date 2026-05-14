"""独立线程进程看门狗 — 到时间后强制终止整个进程树。"""

import os
import sys
import time
import logging
import threading
import subprocess

logger = logging.getLogger("ai-dev-flow")


class WatchdogTimeout(Exception):
    """进程被看门狗超时终止。"""

    def __init__(self, pid: int, timeout_seconds: int):
        self.pid = pid
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Process {pid} killed after {timeout_seconds}s timeout")


class ProcessWatchdog:
    """在独立 Timer 线程中监控进程，到期后强制终止整个进程树。"""

    def __init__(self, pid: int, timeout_seconds: int, on_timeout=None):
        self._pid = pid
        self._timeout = timeout_seconds
        self._on_timeout = on_timeout
        self._timer: threading.Timer | None = None
        self.triggered = False

    def start(self):
        """启动倒计时。到期后调用 _kill() 并在回调线程中触发 on_timeout。"""
        self._timer = threading.Timer(self._timeout, self._on_timer)
        self._timer.daemon = False
        self._timer.start()
        logger.debug(f"Watchdog started: pid={self._pid}, timeout={self._timeout}s")

    def cancel(self):
        """取消看门狗（进程正常完成时调用）。"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
            logger.debug(f"Watchdog cancelled: pid={self._pid}")

    def _on_timer(self):
        """Timer 回调 — 在独立线程中执行。"""
        self.triggered = True
        logger.error(f"Watchdog triggered: pid={self._pid}, timeout={self._timeout}s, killing process tree")
        self._kill()
        if self._on_timeout:
            try:
                self._on_timeout()
            except Exception:
                logger.exception("on_timeout callback raised")

    def _kill(self):
        """强制终止进程及其所有子进程。"""
        if sys.platform == "win32":
            self._kill_windows()
        else:
            self._kill_unix()

    def _kill_windows(self):
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self._pid)],
                capture_output=True, text=True,
            )
        except Exception:
            logger.exception("taskkill failed")

        # 二次确认 — 等待最多 5 秒
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._is_process_dead():
                logger.info(f"Process tree {self._pid} terminated by watchdog")
                return
            time.sleep(0.5)

        logger.critical(f"Process {self._pid} survived taskkill, retrying...")
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self._pid)],
                capture_output=True, text=True,
            )
        except Exception as e:
            logger.error(f"Retry taskkill failed for PID {self._pid}: {e}")

    def _kill_unix(self):
        import signal
        try:
            os.killpg(os.getpgid(self._pid), signal.SIGKILL)
        except Exception as e1:
            try:
                os.kill(self._pid, signal.SIGKILL)
            except Exception as e2:
                logger.error(f"Unix kill failed for PID {self._pid}: killpg={e1}, kill={e2}")

    def _is_process_dead(self) -> bool:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {self._pid}"],
                capture_output=True, text=True,
            )
            return str(self._pid) not in result.stdout
        except Exception:
            return True
