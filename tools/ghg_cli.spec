# -*- mode: python ; coding: utf-8 -*-
"""CLI exe 打包规格（PyInstaller onedir，FR-08.3）。

数据白名单与 pathex 取自 ``tools/packaging.py``（单一真相源），本文件不重复枚举。
用法：``py -X utf8 -m PyInstaller tools/ghg_cli.spec --noconfirm``
"""

import os
import sys

# spec 由 PyInstaller exec 执行，无 __file__；SPECPATH 由 PyInstaller 注入
_TOOLS_DIR = globals().get("SPECPATH") or os.path.join(os.getcwd(), "tools")
sys.path.insert(0, _TOOLS_DIR)

import ghg_packaging as packaging  # noqa: E402

ROOT = packaging.repo_root()

a = Analysis(
    [os.path.join(ROOT, "tools", "entry_cli.py")],
    pathex=packaging.code_pathex(ROOT),
    binaries=[],
    datas=packaging.data_datas(ROOT),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "shiboken6", "tkinter"],   # CLI 不需要 GUI 栈
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=packaging.CLI_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                                   # CLI 形态：保留控制台
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=packaging.CLI_EXE_NAME,
)