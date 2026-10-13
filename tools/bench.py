#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""内置离线基准的命令行入口（薄封装，逻辑在 ``ghg.bench``）。

用法::

    py -X utf8 tools/bench.py                 # 三类基准全跑（缺省）
    py -X utf8 tools/bench.py --suite rules   # 只跑指定套件（可重复）
    py -X utf8 tools/bench.py --json          # 机器可读输出

退出码（plan/03 §六）：0 = 达标；1 = 有指标未达标；2 = 用法/配置错误。

设计判断：**判定逻辑不在此脚本**——本文件只把参数转给 ``ghg.cli bench``，
避免"两处各写一份基准"。直接 `ghg bench` 与本脚本行为完全一致。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg.cli import main  # noqa: E402


def main_argv(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    return main(["bench"] + argv)


if __name__ == "__main__":
    sys.exit(main_argv())
