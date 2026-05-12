from pathlib import Path
from pipeline.snapshot import SnapshotManager, FileEntry, SnapshotDiff


class TestFileEntry:
    def test_dataclass(self):
        e = FileEntry(path="src/main.py", size=100, mtime=1.5, hash="abc")
        assert e.path == "src/main.py"
        assert e.size == 100
        assert e.mtime == 1.5
        assert e.hash == "abc"

    def test_default_hash(self):
        e = FileEntry(path="x.py", size=10, mtime=2.0)
        assert e.hash == ""


class TestDiff:
    def test_added(self):
        before = {}
        after = {"new.py": FileEntry(path="new.py", size=10, mtime=1.0)}
        mgr = SnapshotManager(Path("."), Path("."))
        diff = mgr.diff(before, after)
        assert diff.added == ["new.py"]
        assert diff.removed == []
        assert diff.modified == []

    def test_removed(self):
        before = {"old.py": FileEntry(path="old.py", size=10, mtime=1.0)}
        after = {}
        mgr = SnapshotManager(Path("."), Path("."))
        diff = mgr.diff(before, after)
        assert diff.removed == ["old.py"]
        assert diff.added == []

    def test_modified_mtime(self):
        before = {"f.py": FileEntry(path="f.py", size=10, mtime=1.0)}
        after = {"f.py": FileEntry(path="f.py", size=10, mtime=2.0)}
        mgr = SnapshotManager(Path("."), Path("."))
        diff = mgr.diff(before, after)
        assert "f.py" in diff.modified

    def test_modified_size(self):
        before = {"f.py": FileEntry(path="f.py", size=10, mtime=1.0)}
        after = {"f.py": FileEntry(path="f.py", size=20, mtime=1.0)}
        mgr = SnapshotManager(Path("."), Path("."))
        diff = mgr.diff(before, after)
        assert "f.py" in diff.modified

    def test_no_changes(self):
        fe = FileEntry(path="f.py", size=10, mtime=1.0)
        before = {"f.py": fe}
        after = {"f.py": fe}
        mgr = SnapshotManager(Path("."), Path("."))
        diff = mgr.diff(before, after)
        assert "f.py" in diff.unchanged
        assert diff.modified == []


class TestBuildSnapshot:
    def test_walks_files(self, tmp_path):
        (tmp_path / "a.py").write_text("hello")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.py").write_text("world")
        mgr = SnapshotManager(tmp_path / ".ai-dev", tmp_path)
        (tmp_path / ".ai-dev").mkdir()
        entries = mgr.build_snapshot()
        assert "a.py" in entries
        assert "sub/b.py" in entries
        assert entries["a.py"].size > 0

    def test_skips_dotdirs(self, tmp_path):
        (tmp_path / "a.py").write_text("hello")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("x")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()
        mgr = SnapshotManager(tmp_path / ".ai-dev", tmp_path)
        (tmp_path / ".ai-dev").mkdir()
        entries = mgr.build_snapshot()
        assert "a.py" in entries
        assert all(".git/" not in k for k in entries)
        assert all("node_modules/" not in k for k in entries)


class TestSaveAndLoad:
    def test_roundtrip(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        mgr = SnapshotManager(ad, tmp_path)
        (tmp_path / "x.py").write_text("data")
        entries = mgr.build_snapshot()
        mgr.save(entries)
        loaded = mgr.load()
        assert loaded is not None
        assert "x.py" in loaded
        assert loaded["x.py"].size == 4

    def test_load_missing_returns_none(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        mgr = SnapshotManager(ad, tmp_path)
        assert mgr.load() is None

    def test_load_corrupted_returns_none(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (ad / "snapshot.json").write_text("not json", encoding="utf-8")
        mgr = SnapshotManager(ad, tmp_path)
        assert mgr.load() is None


class TestGetChangedFiles:
    def test_first_run_all_added(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (tmp_path / "a.py").write_text("x")
        mgr = SnapshotManager(ad, tmp_path)
        diff = mgr.get_changed_files()
        assert "a.py" in diff.added
        assert diff.removed == []

    def test_incremental_detects_change(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (tmp_path / "a.py").write_text("original content here")
        mgr = SnapshotManager(ad, tmp_path)
        mgr.save(mgr.build_snapshot())
        # Change file size to guarantee detection (mtime may have low resolution)
        (tmp_path / "a.py").write_text("modified content with different length")
        diff = mgr.get_changed_files()
        assert "a.py" in diff.modified

    def test_unchanged_not_in_modified(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (tmp_path / "a.py").write_text("same")
        mgr = SnapshotManager(ad, tmp_path)
        mgr.save(mgr.build_snapshot())
        diff = mgr.get_changed_files()
        assert "a.py" not in diff.modified
        assert "a.py" in diff.unchanged


class TestUpdateSnapshot:
    def test_preserves_hashes(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (tmp_path / "x.py").write_text("unchanged")
        mgr = SnapshotManager(ad, tmp_path)
        mgr.save(mgr.build_snapshot())
        mgr.update_snapshot()
        loaded = mgr.load()
        assert loaded is not None
        assert "x.py" in loaded


class TestReadCached:
    def test_uses_cache(self, tmp_path):
        mgr = SnapshotManager(tmp_path / ".ai-dev", tmp_path)
        cache = {"f.py": "cached content"}
        assert mgr.read_cached("f.py", cache) == "cached content"

    def test_reads_from_disk_if_not_cached(self, tmp_path):
        (tmp_path / "f.py").write_text("file content", encoding="utf-8")
        mgr = SnapshotManager(tmp_path / ".ai-dev", tmp_path)
        cache = {}
        result = mgr.read_cached("f.py", cache)
        assert result == "file content"
        assert cache["f.py"] == "file content"

    def test_file_not_found(self, tmp_path):
        mgr = SnapshotManager(tmp_path / ".ai-dev", tmp_path)
        assert mgr.read_cached("nope.py", {}) is None
