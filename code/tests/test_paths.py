"""数据目录定位测试（含冻结分支）。"""

import os

import pytest

from ghg.errors import DataDirNotFound
from ghg.paths import find_data_dir


def test_find_data_dir_explicit(data_dir):
    assert find_data_dir(data_dir) == os.path.abspath(data_dir)


def test_find_data_dir_from_cwd(repo_root, monkeypatch):
    monkeypatch.chdir(repo_root)
    assert find_data_dir() == os.path.abspath(os.path.join(repo_root, "data"))


def test_explicit_invalid_raises(tmp_path):
    with pytest.raises(DataDirNotFound):
        find_data_dir(str(tmp_path))


def test_env_var_used(repo_root, monkeypatch):
    monkeypatch.setenv("GHG_DATA_DIR", os.path.join(repo_root, "data"))
    assert find_data_dir() == os.path.abspath(os.path.join(repo_root, "data"))


def test_env_var_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("GHG_DATA_DIR", str(tmp_path))
    with pytest.raises(DataDirNotFound):
        find_data_dir()


def test_upward_search_finds_repo_data(repo_root, monkeypatch, tmp_path):
    """从仓库子目录上溯应能定位 data/。"""
    nested = os.path.join(repo_root, "code", "src", "ghg")
    monkeypatch.chdir(nested)
    monkeypatch.delenv("GHG_DATA_DIR", raising=False)
    assert find_data_dir() == os.path.abspath(os.path.join(repo_root, "data"))
