# -*- mode: python ; coding: utf-8 -*-
"""GUI exe 打包规格（PyInstaller onedir，FR-08.3）。

数据白名单与 pathex 取自 ``tools/packaging.py``（单一真相源）。
用法：``py -X utf8 -m PyInstaller tools/ghg_gui.spec --noconfirm``
"""

import os
import sys

# spec 由 PyInstaller exec 执行，无 __file__；SPECPATH 由 PyInstaller 注入
_TOOLS_DIR = globals().get("SPECPATH") or os.path.join(os.getcwd(), "tools")
sys.path.insert(0, _TOOLS_DIR)

import ghg_packaging as packaging  # noqa: E402

ROOT = packaging.repo_root()

a = Analysis(
    [os.path.join(ROOT, "tools", "entry_gui.py")],
    pathex=packaging.code_pathex(ROOT),
    binaries=[],
    datas=packaging.data_datas(ROOT),
    hiddenimports=list(packaging.GUI_HIDDEN_IMPORTS),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=packaging.GUI_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                                  # GUI 形态：不弹控制台
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=packaging.GUI_EXE_NAME,
)