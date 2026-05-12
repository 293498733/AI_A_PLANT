import subprocess
from pipeline.executor import (
    build_params, check_goose, run_stage, GooseError, GooseNotFound,
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
        except FileNotFoundError:
            pass
