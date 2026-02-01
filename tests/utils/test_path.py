"""utils/path.py 单元测试"""

import pytest
from pathlib import Path
from quantcli.utils import (
    project_root, data_dir, results_dir,
    ensure_dir, ensure_parent_dir,
)


class TestProjectRoot:
    """project_root 测试"""

    def test_project_root_returns_path(self):
        result = project_root()
        assert isinstance(result, Path)
        assert result.exists()

    def test_project_root_has_quantcli(self):
        root = project_root()
        assert (root / "quantcli").exists()


class TestDataDir:
    """data_dir 测试"""

    def test_data_dir_returns_path(self):
        result = data_dir()
        assert isinstance(result, Path)


class TestResultsDir:
    """results_dir 测试"""

    def test_results_dir_returns_path(self):
        result = results_dir()
        assert isinstance(result, Path)

    def test_results_dir_with_subdir(self):
        result = results_dir("test_run")
        assert "test_run" in str(result)


class TestEnsureDir:
    """ensure_dir 测试"""

    def test_ensure_dir_creates_directory(self, tmp_path):
        test_dir = tmp_path / "new_dir" / "nested"
        result = ensure_dir(test_dir)
        assert result.exists()
        assert result == test_dir

    def test_ensure_dir_existing(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        result = ensure_dir(existing)
        assert result.exists()

    def test_ensure_parent_dir(self, tmp_path):
        child = tmp_path / "parent" / "child"
        ensure_parent_dir(child)
        assert child.parent.exists()
