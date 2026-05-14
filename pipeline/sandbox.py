"""Git Worktree 沙箱管理器 — 为每个任务创建隔离的 git worktree。"""

import re
import shutil
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")


class SandboxCreateError(Exception):
    """沙箱创建失败。"""
    pass


def _sanitize(task_id: str) -> str:
    """将 task_id 转换为安全的目录名。"""
    return re.sub(r"[/\\:\*\?\"<>\|]", "_", task_id)


class SandboxManager:
    """管理单个任务的 git worktree 沙箱生命周期。

    创建独立的 detached-HEAD worktree → goose 在沙箱内修改文件 →
    成功后将产出文件同步回真实项目 → 销毁沙箱。

    如果 goose 失败或超时，直接销毁沙箱不复制任何文件。
    """

    def __init__(self, project_root: Path, ai_dev_dir: Path):
        self._project = project_root.resolve()
        self._ai_dev = ai_dev_dir.resolve()
        self._sandboxes_dir = self._ai_dev / "sandboxes"
        self._sandbox_path: Path | None = None

    def create(self, task_id: str) -> Path:
        """创建 git worktree 沙箱，返回沙箱路径。

        若已有同名残留沙箱则先强制清理（崩溃恢复）。
        """
        self._sandboxes_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _sanitize(task_id)
        self._sandbox_path = self._sandboxes_dir / safe_id

        # 清理上次崩溃可能留下的残留
        if self._sandbox_path.exists():
            logger.warning(f"Removing orphaned sandbox: {self._sandbox_path}")
            self._force_remove()

        try:
            result = subprocess.run(
                [
                    "git", "-C", str(self._project),
                    "worktree", "add", "--detach",
                    str(self._sandbox_path), "HEAD",
                ],
                capture_output=True, text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise SandboxCreateError(
                    f"git worktree add failed: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise SandboxCreateError("git worktree add timed out after 30s")
        except FileNotFoundError:
            raise SandboxCreateError("git not found in PATH")

        # 初始化子模块 — 从主项目本地拷贝（避免网络依赖）
        # 使用 git config 直接解析 .gitmodules，避免 git submodule status
        # 递归发现 sandbox worktree（含 .git 文件）导致 fatal 错误
        _copy_submodules_to_sandbox(self._project, self._sandbox_path)

        logger.info(f"Sandbox created: {self._sandbox_path}")
        return self._sandbox_path

    def sync_outputs(self, output_files: list[str]) -> list[str]:
        """将沙箱中的产出文件复制到真实项目。返回成功复制的文件列表。"""
        if not self._sandbox_path:
            return []

        synced = []
        for rel_path in output_files:
            # 路径穿越检测：拒绝含 .. 或绝对路径的产出文件
            if not self._safe_rel_path(rel_path):
                logger.warning(f"Rejected unsafe output path: {rel_path}")
                continue

            src = self._sandbox_path / rel_path
            dst = self._project / rel_path

            if not src.exists():
                logger.warning(f"Output file not found in sandbox: {rel_path}")
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            synced.append(rel_path)
            logger.debug(f"Synced: {rel_path}")

        if synced:
            logger.info(f"Synced {len(synced)} files from sandbox to project")

        return synced

    @staticmethod
    def _safe_rel_path(rel_path: str) -> bool:
        """拒绝含 .. 或绝对路径的路径，防御沙箱穿越。"""
        p = Path(rel_path)
        if p.is_absolute() or '..' in p.parts:
            return False
        return True

    def detect_extra_modifications(self, task_output_files: set[str]) -> list[str]:
        """检测沙箱中未被任务声明的文件变更。"""
        if not self._sandbox_path:
            return []

        try:
            result = subprocess.run(
                ["git", "-C", str(self._sandbox_path), "diff", "--name-only", "HEAD"],
                capture_output=True, text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []

            modified = set(f.strip() for f in result.stdout.splitlines() if f.strip())
            extra = modified - set(task_output_files)
            return sorted(extra)
        except Exception:
            return []

    def destroy(self) -> None:
        """销毁沙箱 worktree。"""
        if not self._sandbox_path:
            return

        self._force_remove()
        self._sandbox_path = None

    def _force_remove(self) -> None:
        """强制移除 worktree，回退到手动清理。"""
        if not self._sandbox_path or not self._sandbox_path.exists():
            return

        # 尝试标准 worktree remove
        try:
            result = subprocess.run(
                [
                    "git", "-C", str(self._project),
                    "worktree", "remove", "--force",
                    str(self._sandbox_path),
                ],
                capture_output=True, text=True,
                timeout=15,
            )
            if result.returncode == 0:
                logger.info(f"Sandbox destroyed: {self._sandbox_path}")
                return
        except Exception:
            pass

        # 回退：直接删除目录 + prune
        try:
            shutil.rmtree(self._sandbox_path, ignore_errors=True)
            subprocess.run(
                ["git", "-C", str(self._project), "worktree", "prune"],
                capture_output=True, text=True,
                timeout=10,
            )
            logger.warning(f"Sandbox force-removed: {self._sandbox_path}")
        except Exception:
            logger.error(f"Failed to remove sandbox: {self._sandbox_path}")

    @staticmethod
    def cleanup_orphaned(project_root: Path, ai_dev_dir: Path) -> list[str]:
        """管道启动时清理所有残留的 sandbox 目录。"""
        sandboxes_dir = ai_dev_dir / "sandboxes"
        if not sandboxes_dir.exists():
            return []

        cleaned = []
        for child in sandboxes_dir.iterdir():
            if child.is_dir():
                try:
                    subprocess.run(
                        [
                            "git", "-C", str(project_root),
                            "worktree", "remove", "--force",
                            str(child),
                        ],
                        capture_output=True, text=True,
                        timeout=15,
                    )
                except Exception as e:
                    logger.debug(f"git worktree remove failed for {child.name}: {e}")

                shutil.rmtree(child, ignore_errors=True)
                cleaned.append(child.name)
                logger.info(f"Cleaned orphaned sandbox: {child.name}")

        # Prune 任何残留的 worktree 引用
        try:
            subprocess.run(
                ["git", "-C", str(project_root), "worktree", "prune"],
                capture_output=True, text=True,
                timeout=10,
            )
        except Exception as e:
            logger.debug(f"git worktree prune failed: {e}")

        if cleaned:
            logger.info(f"Cleaned {len(cleaned)} orphaned sandbox(es)")

        return cleaned


def _copy_submodules_to_sandbox(project_root: Path, sandbox_path: Path) -> None:
    """从 .gitmodules 读取子模块列表，从主项目本地拷贝到沙箱。

    不使用 git submodule status，因为沙箱 worktree 内的 .git 文件会被 git
    误判为嵌套 repo（fatal: no submodule mapping found），导致子模块列表为空。
    """
    gitmodules = project_root / ".gitmodules"
    if not gitmodules.exists():
        return

    try:
        result = subprocess.run(
            ["git", "config", "--file", str(gitmodules),
             "--get-regexp", r"submodule\..*\.path"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return

    for line in result.stdout.strip().splitlines():
        # 格式: "submodule.<name>.path <path>"
        # 路径可能含空格，取 key 之后的部分
        m = re.match(r"^submodule\.[^.]+\.path\s+(.+)$", line)
        if not m:
            continue
        sub_path = m.group(1).strip()
        src = project_root / sub_path
        dst = sandbox_path / sub_path
        if not (src.exists() and src.is_dir()):
            continue
        if dst.exists() and any(dst.iterdir()):
            continue  # 已有内容，跳过
        logger.info(f"Copying submodule '{sub_path}' to sandbox (local)")
        try:
            _robocopy_tree(src, dst)
        except Exception as e:
            logger.warning(f"Submodule copy failed for '{sub_path}': {e}")


def _robocopy_tree(src: Path, dst: Path) -> None:
    """递归复制目录树，跳过 .git 目录。robocopy 不可用时回退到 Python。"""
    import shutil as _shutil
    # 优先使用 robocopy（Windows 上更快且无 MAX_PATH 问题）
    try:
        result = subprocess.run(
            [
                "robocopy", str(src), str(dst),
                "/E", "/NFL", "/NDL", "/NJH", "/NJS",
                "/XD", ".git",
            ],
            timeout=120,
        )
        # robocopy 返回码 0-7 表示成功
        if result.returncode < 8:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: Python 递归复制
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name == ".git":
            continue
        target = dst / item.name
        if item.is_dir():
            _robocopy_tree(item, target)
        else:
            _shutil.copy2(item, target)
