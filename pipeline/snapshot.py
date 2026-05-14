"""项目快照 — 文件树 hash + 变更检测，避免每次全量扫描项目。

增量策略：
- 首次运行：全量扫描，存 mtime+size 到 snapshot.json
- 后续运行：对比 mtime/size，仅对变化文件重读内容
- 内容缓存：未变化文件复用上次读取的内容
"""

import json
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger("ai-dev-flow")

SNAPSHOT_FILE = "snapshot.json"

# 扫描时跳过的目录
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "target", "build", "dist", ".idea", ".vscode", ".ai-dev"}

# 二进制文件扩展名（不做内容缓存）
BINARY_EXTS = {".jar", ".war", ".class", ".exe", ".dll", ".so", ".dylib",
               ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz"}


@dataclass
class FileEntry:
    path: str          # 相对于 project_root 的路径
    size: int
    mtime: float
    hash: str = ""     # 仅变更文件计算


@dataclass
class SnapshotDiff:
    added: list[str]
    removed: list[str]
    modified: list[str]
    unchanged: list[str]


class SnapshotManager:
    """管理项目文件树快照，支持增量变更检测。"""

    def __init__(self, ai_dev_dir: Path, project_root: Path):
        self.snapshot_path = ai_dev_dir / SNAPSHOT_FILE
        self.project_root = project_root
        self._content_cache: dict[str, str] = {}

    # ---- 快照构建 ----

    def build_snapshot(self) -> dict[str, FileEntry]:
        """全量扫描项目，构建文件树快照。"""
        entries: dict[str, FileEntry] = {}
        self._walk(self.project_root, self.project_root, entries)
        logger.info(f"Snapshot built: {len(entries)} files indexed")
        return entries

    def _walk(self, base: Path, current: Path, entries: dict[str, FileEntry]) -> None:
        try:
            for child in sorted(current.iterdir()):
                if child.name.startswith(".") or child.name in SKIP_DIRS:
                    continue
                if child.is_dir():
                    self._walk(base, child, entries)
                elif child.is_file():
                    try:
                        stat = child.stat()
                        rel = str(child.relative_to(base)).replace("\\", "/")
                        entries[rel] = FileEntry(
                            path=rel,
                            size=stat.st_size,
                            mtime=stat.st_mtime,
                        )
                    except OSError:
                        pass
        except PermissionError:
            pass

    # ---- 持久化 ----

    def save(self, entries: dict[str, FileEntry]) -> None:
        data = {
            "project_root": str(self.project_root),
            "files": {
                path: {"size": e.size, "mtime": e.mtime, "hash": e.hash}
                for path, e in entries.items()
            }
        }
        self.snapshot_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> dict[str, FileEntry] | None:
        if not self.snapshot_path.exists():
            return None
        try:
            data = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            entries = {}
            for path, info in data.get("files", {}).items():
                entries[path] = FileEntry(
                    path=path,
                    size=info["size"],
                    mtime=info["mtime"],
                    hash=info.get("hash", ""),
                )
            return entries
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Snapshot corrupted: {e}")
            return None

    # ---- 变更检测 ----

    def diff(self, before: dict[str, FileEntry],
             after: dict[str, FileEntry]) -> SnapshotDiff:
        """对比新旧快照，返回变更分类。"""
        added = [p for p in after if p not in before]
        removed = [p for p in before if p not in after]
        modified = []
        unchanged = []

        for p in before:
            if p in after:
                bf = before[p]
                af = after[p]
                if bf.mtime != af.mtime or bf.size != af.size:
                    modified.append(p)
                else:
                    unchanged.append(p)

        return SnapshotDiff(
            added=added, removed=removed, modified=modified, unchanged=unchanged
        )

    def get_changed_files(self) -> SnapshotDiff:
        """主 API：对比当前文件系统与上次快照，返回变更文件列表。"""
        old = self.load()
        new = self.build_snapshot()
        if old is None:
            # 首次运行：全部文件视为 added
            return SnapshotDiff(
                added=list(new.keys()),
                removed=[],
                modified=[],
                unchanged=[],
            )
        diff = self.diff(old, new)
        # 对 modified 文件计算内容 hash 以确认真正变更
        real_modified = []
        for p in diff.modified:
            if self._hash_changed(p, old[p], new[p]):
                real_modified.append(p)
            else:
                diff.unchanged.append(p)
        diff.modified = real_modified
        return diff

    def _hash_changed(self, path: str, old_entry: FileEntry,
                      new_entry: FileEntry) -> bool:
        """快速判断文件内容是否真正变更（mtime 可能被 git checkout 刷新）。"""
        # 快速路径：size 不同则必然变更
        if old_entry.size != new_entry.size:
            return True
        # 对 100KB 以内的文本文件做 hash 对比
        if new_entry.size > 100 * 1024:
            return True  # 大文件保守视为变更
        ext = Path(path).suffix.lower()
        if ext in BINARY_EXTS:
            return True  # 二进制文件保守视为变更
        try:
            fp = self.project_root / path
            content = fp.read_bytes()
            new_hash = hashlib.sha256(content).hexdigest()
            if old_entry.hash:
                return old_entry.hash != new_hash
            # 旧快照无 hash（首次迁移），计算旧 hash
            hashlib.sha256(content).hexdigest()
            new_entry.hash = new_hash
            return True  # 无旧 hash 时保守视为变更
        except Exception:
            return True

    # ---- 内容缓存 ----

    def read_cached(self, path: str, cache: dict[str, str]) -> str | None:
        """读取文件内容，优先使用缓存。"""
        if path in cache:
            return cache[path]
        fp = self.project_root / path
        if not fp.exists():
            return None
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            cache[path] = content
            return content
        except Exception:
            return None

    def update_snapshot(self) -> None:
        """更新快照为当前文件系统状态。在任务完成后调用。"""
        entries = self.build_snapshot()
        # 保留已有 hash 值避免重复计算
        old = self.load()
        if old:
            for path, entry in entries.items():
                if path in old and old[path].mtime == entry.mtime and old[path].size == entry.size:
                    entry.hash = old[path].hash
        self.save(entries)
