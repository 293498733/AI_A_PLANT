import pytest
from pathlib import Path


@pytest.fixture
def ci_mode():
    """Set ci_mode=True for both checkpoint and error_handler. Reset after test."""
    from pipeline.checkpoint import set_ci_mode as set_ci_checkpoint
    from pipeline.error_handler import set_ci_mode as set_ci_error
    set_ci_checkpoint(True)
    set_ci_error(True)
    yield
    set_ci_checkpoint(False)
    set_ci_error(False)


@pytest.fixture
def temp_ai_dev_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".ai-dev"
    d.mkdir()
    (d / "outputs").mkdir()
    return d


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Minimal project structure with .git marker."""
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "main.py").write_text("# dummy\n", encoding="utf-8")
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".ai-dev").mkdir(exist_ok=True)
    return tmp_path
