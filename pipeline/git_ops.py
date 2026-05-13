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

    def push(self) -> bool:
        """推送所有本地提交到 origin。失败时返回 False 不抛异常。"""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo), "push", "origin", "main"],
                capture_output=True, text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Git push failed: {result.stderr.strip()}")
                return False
            logger.info("Pushed to origin/main")
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
