import io
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.executor import (
    build_params, check_goose, run_stage, GooseError, GooseNotFound,
    detect_jdk, JdkNotFound, _parse_javac_version,
)


class TestBuildParams:
    def test_empty(self):
        assert build_params({}) == []

    def test_single(self):
        assert build_params({"key": "val"}) == ["--params", "key=val"]

    def test_multiple(self):
        result = build_params({"a": "1", "b": "2"})
        assert result == ["--params", "a=1", "--params", "b=2"]


class TestGooseExceptions:
    def test_goose_not_found(self):
        e = GooseNotFound("goose not in PATH")
        assert "goose not in PATH" in str(e)

    def test_goose_error(self):
        e = GooseError(1, "something failed")
        assert e.returncode == 1
        assert "something failed" in e.stderr


class TestCheckGoose:
    def test_found(self, mocker):
        mocker.patch("shutil.which", return_value="/usr/bin/goose")
        assert check_goose() == "/usr/bin/goose"

    def test_not_found(self, mocker):
        mocker.patch("shutil.which", return_value=None)
        try:
            check_goose()
            assert False, "should have raised"
        except GooseNotFound:
            pass


class TestRunStage:
    def test_success(self, mocker):
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = ["output line 1\n", "output line 2\n"]
        mock_proc.stderr = []
        mock_proc.returncode = 0
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        result = run_stage(recipe="test.yaml", max_turns=10,
                           params={"k": "v"}, cwd=None)
        assert result.returncode == 0

    def test_failure(self, mocker):
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = ["start\n"]
        mock_proc.stderr = ["error: failed\n"]
        mock_proc.returncode = 1
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        result = run_stage(recipe="test.yaml", max_turns=10,
                           params={}, cwd=None)
        assert result.returncode == 1
        assert "failed" in result.stderr

    def test_popen_raises_file_not_found(self, mocker):
        mocker.patch("subprocess.Popen", side_effect=FileNotFoundError("goose"))
        try:
            run_stage(recipe="test.yaml", max_turns=10, params={}, cwd=None)
            assert False, "should have raised"
        except GooseNotFound:
            pass


class TestRunWithWatchdog:
    """超时返回契约 — 上层据此判定失败、保留沙箱，是断点恢复的入口。"""

    class _FakeProc:
        pid = 424242

        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO("")

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            pass

    def _patch_executor(self, mocker, triggered, returncode=0):
        from pipeline import executor

        proc = self._FakeProc(returncode)
        triggered_flag = triggered

        class _FakeWatchdog:
            def __init__(self, pid, timeout, on_timeout=None):
                self.triggered = triggered_flag

            def start(self):
                pass

            def cancel(self):
                pass

        mocker.patch.object(executor, "_spawn", return_value=proc)
        mocker.patch.object(executor, "ProcessWatchdog", _FakeWatchdog)
        return executor

    def test_timeout_returns_watchdog_failure(self, mocker):
        """看门狗触发时必须返回 -1 并标注原因，而不是透传子进程退出码。"""
        executor = self._patch_executor(mocker, triggered=True, returncode=-9)
        result = executor._run_with_watchdog(["goose"], Path("."), 1)
        assert result.returncode == -1
        assert "killed by watchdog after 1s" in result.stderr

    def test_no_timeout_returns_process_returncode(self, mocker):
        executor = self._patch_executor(mocker, triggered=False, returncode=0)
        result = executor._run_with_watchdog(["goose"], Path("."), 1)
        assert result.returncode == 0
        assert "watchdog" not in result.stderr


class TestParseJavacVersion:
    def test_javac_17(self):
        assert _parse_javac_version("javac 17.0.13") == (17, 0, 13)

    def test_javac_11(self):
        assert _parse_javac_version("javac 11.0.20") == (11, 0, 20)

    def test_openjdk_format(self):
        output = 'openjdk version "17.0.9" 2023-10-17'
        assert _parse_javac_version(output) == (17, 0, 9)

    def test_no_version(self):
        assert _parse_javac_version("not a javac output") is None


class TestDetectJdk:
    def test_finds_matching_jdk(self, mocker):
        """detect_jdk 在当前主机找到 JDK 17；无 JDK 环境跳过。"""
        try:
            result = detect_jdk(17)
        except JdkNotFound:
            pytest.skip("当前主机未安装 JDK 17")
        assert result is not None
        assert "jdk" in result.lower() or "zulu" in result.lower()
        # Verify javac exists at that path（Windows 为 javac.exe）
        javac_name = "javac.exe" if sys.platform == "win32" else "javac"
        javac = Path(result) / "bin" / javac_name
        assert javac.exists(), f"javac not found at {javac}"

    def test_raises_when_not_found(self, mocker):
        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("shutil.which", return_value=None)

        try:
            detect_jdk(21)
            assert False, "should raise"
        except JdkNotFound as e:
            assert e.required == 21
            assert "JDK 21" in str(e)
