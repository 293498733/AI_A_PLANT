import subprocess
from pathlib import Path
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
        """detect_jdk finds JDK 17 on the actual system (D:/zulu17 or similar)."""
        result = detect_jdk(17)
        assert result is not None
        assert "jdk" in result.lower() or "zulu" in result.lower()
        # Verify javac exists at that path
        javac = Path(result) / "bin" / "javac.exe"
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
