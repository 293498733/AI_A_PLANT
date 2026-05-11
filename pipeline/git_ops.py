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
