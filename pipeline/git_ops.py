"""Git 操作封装 — 自动提交、stash、commit hash 提取。"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")


class GitOps:
    """管理任务驱动的 Git 操作。"""

    def __init__(self, repo_root: Path):
        self.repo = repo_root
        if not (repo_root / ".git").exists():
            raise RuntimeError(f"Not a git repository: {repo_root}")
        self._branch = self._detect_branch()
        self._tracking_remote, self._tracking_ref = self._detect_upstream()

    def _detect_branch(self) -> str:
        """检测当前分支名。"""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            logger.warning("Cannot detect current branch")
            return ""

    def _detect_upstream(self) -> tuple[str, str]:
        """检测当前分支的 tracking remote 和 merge ref。返回 (remote, ref)。"""
        if not self._branch:
            return ("", "")
        try:
            remote = subprocess.run(
                ["git", "-C", str(self.repo), "config",
                 f"branch.{self._branch}.remote"],
                capture_output=True, text=True, timeout=5,
            )
            merge = subprocess.run(
                ["git", "-C", str(self.repo), "config",
                 f"branch.{self._branch}.merge"],
                capture_output=True, text=True, timeout=5,
            )
            r = remote.stdout.strip()
            m = merge.stdout.strip()
            if r and m:
                logger.debug(f"Upstream: {r}/{m} (branch={self._branch})")
            else:
                logger.warning(f"No upstream tracking for branch '{self._branch}'")
            return (r, m)
        except Exception:
            return ("", "")

    def commit_task(self, task_id: str, task_name: str, category: str, priority: str,
                    estimated_turns: int) -> str | None:
        """Stage 所有变更并提交，返回 commit hash。无变更时返回 None。"""
        # Check if there's anything to commit
        status = subprocess.run(
            ["git", "-C", str(self.repo), "status", "--porcelain"],
            capture_output=True, text=True
        )
        if not status.stdout.strip():
            logger.debug(f"No changes to commit for task {task_id}")
            return None

        # Stage all changes
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "-A"],
            capture_output=True, text=True
        )

        message = (
            f"[ai-dev-flow] {task_id}: {task_name}\n\n"
            f"Category: {category}\n"
            f"Priority: {priority}\n"
            f"Estimated turns: {estimated_turns}"
        )
        result = subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", message],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Git commit failed: {result.stderr}")
            return None

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        )
        commit_hash = hash_result.stdout.strip()[:8]
        logger.info(f"Task {task_id} committed: {commit_hash}")
        return commit_hash

    def commit_files(self, file_paths: list[str], task_id: str, task_name: str,
                     category: str, priority: str,
                     estimated_turns: int) -> str | None:
        """仅 stage 指定文件并提交。无变更时返回 None。"""
        if not file_paths:
            return None

        for fp in file_paths:
            subprocess.run(
                ["git", "-C", str(self.repo), "add", fp],
                capture_output=True, text=True,
            )

        message = (
            f"[ai-dev-flow] {task_id}: {task_name}\n\n"
            f"Category: {category}\n"
            f"Priority: {priority}\n"
            f"Estimated turns: {estimated_turns}"
        )
        result = subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", message],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error(f"Git commit failed: {result.stderr}")
            return None

        hash_result = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = hash_result.stdout.strip()[:8]
        logger.info(f"Task {task_id} committed ({len(file_paths)} files): {commit_hash}")
        return commit_hash

    @property
    def can_push(self) -> bool:
        """是否具备推送条件：有 remote 且 tracking 已配置。"""
        return bool(self._tracking_remote and self._tracking_ref and self._branch)

    def push(self) -> bool:
        """推送当前分支到 tracking remote。失败时返回 False 不抛异常。

        先检测当前分支的 upstream (branch.<name>.remote + merge)，
        若未配置 tracking 则跳过推送并告警。
        """
        if not self.can_push:
            logger.warning(
                f"Cannot push: branch '{self._branch}' has no tracking remote configured"
            )
            return False

        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo), "push",
                 self._tracking_remote, f"HEAD:{self._tracking_ref}"],
                capture_output=True, text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Git push failed: {result.stderr.strip()}")
                return False
            logger.info(
                f"Pushed to {self._tracking_remote}/{self._tracking_ref} "
                f"(branch={self._branch})"
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Git push timed out")
            return False
        except Exception:
            logger.warning("Git push failed (network/permission)")
            return False

    def pre_task_check(self) -> bool:
        """检查工作区是否干净，不干净时自动 stash。"""
        status = subprocess.run(
            ["git", "-C", str(self.repo), "status", "--porcelain"],
            capture_output=True, text=True
        )
        if status.stdout.strip():
            logger.warning("Working tree is dirty, creating auto-stash")
            subprocess.run(
                ["git", "-C", str(self.repo), "stash", "push", "-m",
                 "ai-dev-flow auto-stash before task"],
                capture_output=True, text=True
            )
        return True
