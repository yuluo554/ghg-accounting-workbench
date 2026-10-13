#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GUI exe 入口（PyInstaller 打包用）。

``--selftest`` 走无窗口自检（复用 CLI 的 selftest 实现）；其余参数进主窗口。

用法：``ghg-gui.exe``（开窗口）/ ``ghg-gui.exe --selftest``（打包产物验收）。
"""

import sys

from ghg_gui.main import main

if __name__ == "__main__":
    sys.exit(main())