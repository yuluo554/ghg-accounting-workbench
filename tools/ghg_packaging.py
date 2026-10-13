"""打包白名单与共用配置（PyInstaller spec 的唯一真相源）。

**白名单是硬约束**（plan/03 §七「打包后数据定位失真」的对策）：随 exe 分发的数据目录
必须是显式枚举的清单，而不是 `data/` 整棵拷进去。理由有二：

  1. **可审计**：发布产物的数据面一眼可数——哪些目录进了包、各自多大、来自哪；
  2. **防误带**：`data/knowledge/raw/` 是官方原文快照（约 11 MB），是**核对留档**而非
     运行时依赖（报告 §7 只用 `clauses.json` 的索引），整树拷贝会让发布包无谓膨胀。

清单外的任何 `data/**` 目录一律**不进包**；新增数据目录必须在此登记并说明运行时用途
（由 `test_m5_packaging.py` 的断言锁定）。
"""

import os

#: 随 exe 分发的 data/ 子目录白名单：``(相对路径, 运行时用途)``
DATA_WHITELIST = (
    ("rules", "规则包 + manifest + units（运行时必需）"),
    ("factors", "官方因子库台账（因子来源可核证）"),
    ("truth", "内置示例档案 + 真值库（演示与冒烟）"),
    ("knowledge/clauses.json", "条款库索引（报告 §7 依据清单）"),
)

#: 显式排除项（即使落在白名单目录内也不进包）
DATA_EXCLUDE = (
    "knowledge/raw",          # 官方原文快照：核对留档，非运行时依赖
)

#: 打进包但属"代码"的部分（供 spec 引用，避免两条路径各写一遍）
CODE_PATHS = ("code/src", "code/gui")

#: 打包产物名（双 exe，FR-08.3）
CLI_EXE_NAME = "ghg-cli"
GUI_EXE_NAME = "ghg-gui"

#: 隐藏导入：GUI 入口在函数内 import PySide6，spec 静态分析看不到
GUI_HIDDEN_IMPORTS = ("PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets")


def repo_root():
    """仓库根（本文件位于 ``<root>/tools/``）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_datas(root=None):
    """返回 PyInstaller ``datas`` 列表：白名单内的 data 子项 → 包内 ``data/<相对路径>``。"""
    root = root or repo_root()
    datas = []
    for rel, _purpose in DATA_WHITELIST:
        source = os.path.join(root, "data", *rel.split("/"))
        if not os.path.exists(source):
            raise RuntimeError("打包白名单指向的数据路径不存在：%s" % source)
        if os.path.isdir(source):
            dest = os.path.join("data", *rel.split("/"))
        else:
            dest = os.path.join("data", *os.path.dirname(rel).split("/"))
        datas.append((source, dest))
    return datas


def code_pathex(root=None):
    """``pathex``：让 PyInstaller 能解析 ghg / ghg_gui 两个包。"""
    root = root or repo_root()
    return [os.path.join(root, *path.split("/")) for path in CODE_PATHS]


def assert_whitelist_clean(root=None):
    """自检：白名单与排除项不得互相矛盾（新增目录时必须显式登记）。"""
    root = root or repo_root()
    data_dir = os.path.join(root, "data")
    present = sorted(name for name in os.listdir(data_dir)
                     if os.path.isdir(os.path.join(data_dir, name)))
    listed = {rel.split("/")[0] for rel, _purpose in DATA_WHITELIST}
    unlisted = [name for name in present if name not in listed]
    if unlisted:
        raise RuntimeError(
            "data/ 下存在未登记进打包白名单的目录：%s；"
            "请在 tools/packaging.py 的 DATA_WHITELIST 中显式登记（或说明为何不进包）"
            % unlisted
        )
    return True
