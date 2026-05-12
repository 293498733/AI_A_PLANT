import subprocess
from pipeline.git_ops import GitOps


class TestInit:
    def test_without_git_raises(self, tmp_path):
        try:
            GitOps(tmp_path)
            assert False, "should have raised"
        except RuntimeError:
            pass

    def test_with_git_succeeds(self, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)
        assert git.repo == tmp_path


class TestCommitTask:
    def test_no_changes(self, mocker, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)

        def mock_run(*args, **kwargs):
            cmd = args[0]
            if "status" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")

        mocker.patch("subprocess.run", side_effect=mock_run)
        assert git.commit_task("t1", "Task", "core", "P0", 20) is None

    def test_with_changes(self, mocker, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)

        def mock_run(*args, **kwargs):
            cmd = args[0] if args else []
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "status" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="M file.py\n", stderr="")
            elif "commit" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            elif "rev-parse" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abcd1234efgh5678\n", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mocker.patch("subprocess.run", side_effect=mock_run)
        h = git.commit_task("t1", "Task", "core", "P0", 20)
        assert h == "abcd1234"

    def test_commit_failed(self, mocker, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)

        def mock_run(*args, **kwargs):
            cmd = args[0] if args else []
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "status" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="M file.py\n", stderr="")
            elif "commit" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="rejected")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mocker.patch("subprocess.run", side_effect=mock_run)
        assert git.commit_task("t1", "Task", "core", "P0", 20) is None


class TestPreTaskCheck:
    def test_clean_workspace(self, mocker, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)
        mocker.patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr=""))
        assert git.pre_task_check() is True

    def test_dirty_stashes(self, mocker, tmp_path):
        (tmp_path / ".git").mkdir()
        git = GitOps(tmp_path)
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            cmd = args[0] if args else []
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            call_count += 1
            if "status" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="M x.py\n", stderr="")
            elif "stash" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mocker.patch("subprocess.run", side_effect=mock_run)
        assert git.pre_task_check() is True
        assert call_count >= 2
