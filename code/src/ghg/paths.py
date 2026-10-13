"""数据目录定位（含 PyInstaller 冻结分支）。

优先级（改优先级属"会打挂测试"的口径变更，见 plan/05 §四）：
  1. 显式传参 data_dir
  2. 环境变量 GHG_DATA_DIR
  3. 冻结态内嵌：sys._MEIPASS/data （PyInstaller 6）→ exe 目录/_internal/data（PyInstaller 5）
  4. 源码态：从本文件上溯找到含 data/rules/manifest.json 的仓库根
  5. CWD 上溯（同上判据）
"""

import os
import sys

from .errors import DataDirNotFound

_MARKER = os.path.join("rules", "manifest.json")


def _looks_like_data_dir(path):
    if not path:
        return False
    return os.path.isfile(os.path.join(path, _MARKER))


def _frozen_candidates():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        yield os.path.join(base, "data")
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    yield os.path.join(exe_dir, "data")
    yield os.path.join(exe_dir, "_internal", "data")


def _climb_candidates(start):
    cur = os.path.abspath(start)
    while True:
        yield os.path.join(cur, "data")
        parent = os.path.dirname(cur)
        if parent == cur:
            return
        cur = parent


def find_data_dir(data_dir=None):
    """定位数据目录；失败抛 :class:`DataDirNotFound`。"""
    if data_dir:
        if _looks_like_data_dir(data_dir):
            return os.path.abspath(data_dir)
        raise DataDirNotFound("指定的数据目录缺少 rules/manifest.json：%s" % data_dir)

    env = os.environ.get("GHG_DATA_DIR")
    if env:
        if _looks_like_data_dir(env):
            return os.path.abspath(env)
        raise DataDirNotFound("环境变量 GHG_DATA_DIR 指向的数据目录非法：%s" % env)

    if getattr(sys, "frozen", False):
        for cand in _frozen_candidates():
            if _looks_like_data_dir(cand):
                return os.path.abspath(cand)

    for start in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        for cand in _climb_candidates(start):
            if _looks_like_data_dir(cand):
                return os.path.abspath(cand)

    raise DataDirNotFound(
        "未能定位数据目录（需含 rules/manifest.json）。可用 --data-dir 或 GHG_DATA_DIR 指定。"
    )
