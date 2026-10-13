"""pytest 公共夹具：把 src 加入 import 路径，提供仓库根与数据目录。"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(CODE_DIR)
SRC_DIR = os.path.join(CODE_DIR, "src")
GUI_DIR = os.path.join(CODE_DIR, "gui")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if GUI_DIR not in sys.path:
    sys.path.insert(0, GUI_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
# GUI 测试一律 offscreen：无头 CI 也必须能跑（见 test_m5_gui.py）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def data_dir():
    return os.path.join(REPO_ROOT, "data")


@pytest.fixture(scope="session")
def rules_index(data_dir):
    from ghg.rules import RulesIndex
    return RulesIndex.load(data_dir)


@pytest.fixture(scope="session")
def unit_table(data_dir):
    from ghg.units import UnitTable
    return UnitTable.load(data_dir)
