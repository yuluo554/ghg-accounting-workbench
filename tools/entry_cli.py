#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI exe 入口（PyInstaller 打包用）。

为什么单独一个入口文件而不是直接打包 ``ghg/cli.py``：后者用的是包内相对导入
（``from . import jsonio``），作为顶层脚本运行时 ``__package__`` 为空会直接崩。
这里以绝对导入方式调用，包结构保持完整。

用法：``ghg-cli.exe coords`` / ``ghg-cli.exe --selftest``（打包产物验收）。
"""

import sys

from ghg.cli import main

if __name__ == "__main__":
    sys.exit(main())