#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""零政策字面量门禁（NFR-07）。

规则包的政策数值**只能**来自 data/rules/ 下的 JSON；引擎/CLI/工具源码（含 docstring
与注释）里出现这些数值 token 即视为"抄进代码的第二份真相"，一律失败。

流程：
  1. 从规则包采集政策数值 token（``value``/``coefficient``/``threshold``/``limit`` 字段）；
  2. 扫描目标源码目录，词边界匹配这些 token（**含注释与 docstring**，按 Python tokenize 的
     字符串与注释一并覆盖，实际做法是整文件文本扫描 + 排除纯数字以外的噪声）；
  3. 命中即打印"文件:行号 [token] 次数"并 exit 1。

豁免口径（写死，见 plan/06 §二）：
  * 豁免 1：units.json 及其加载路径 —— 单位换算因子是定义性关系（SI 定义），非政策数值；
  * 豁免 2：免责声明法律文本（在 gen_rulesets.py 中定义，属法律文本常量）；
  * 豁免 3：精度位用 Decimal(1).scaleb(-n) 表达，天然不产生小数 token；
  * 豁免 4：标准编号/条款号是公开标识符（元数据），采集端只采数值字段，天然不采集。

阳性对照：脚本对"人为注入一个规则包数值 token"的临时文件必须命中（--selftest）。
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg.errors import GhgError  # noqa: E402
from ghg.paths import find_data_dir  # noqa: E402
from ghg.rules import RulesIndex  # noqa: E402

DEFAULT_TARGETS = [
    # 只扫**引擎与前端源码**：这些地方出现政策数值 = "抄进代码的第二份真相"。
    # 生成器（tools/gen_*.py）是数据文件的生产者，必然持有模板数值，属真相源而非复制品，
    # 因此**不在扫描范围**（否则门禁自相矛盾）。
    os.path.join("code", "src", "ghg"),
    # M5：桌面形态同属"前端源码"（只消费引擎 API，零判定逻辑），一并在门禁之下
    # （见 plan/06 D5-3）。GUI 若内联政策数值，同样是第二份真相。
    os.path.join("code", "gui", "ghg_gui"),
]

# token 太短（1~2 位）会刷屏，且这类数字在代码中普遍是索引/计数，不构成"政策数值"
MIN_TOKEN_LEN = 3

OK_MARKER = "ZERO_LITERAL_GATE_OK"


def collect_tokens(data_dir):
    index = RulesIndex.load(data_dir)
    tokens = set()
    for token in index.collect_numeric_tokens():
        if len(token) >= MIN_TOKEN_LEN:
            tokens.add(token)
    return sorted(tokens)


def _build_pattern(tokens):
    # 词边界：两侧不得是数字/小数点，避免 1000 命中 10000 的子串
    escaped = [re.escape(t) for t in sorted(tokens, key=len, reverse=True)]
    body = "|".join(escaped)
    return re.compile(r"(?<![0-9.])(" + body + r")(?![0-9])")


def _iter_source_files(root, targets):
    for target in targets:
        path = target if os.path.isabs(target) else os.path.join(root, target)
        if os.path.isfile(path):
            yield path
        elif os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
                for name in sorted(filenames):
                    if name.endswith(".py"):
                        yield os.path.join(dirpath, name)


def scan(root, data_dir, targets=None, tokens=None):
    """返回命中列表 [ {file, line, token, count} ]。"""
    if tokens is None:
        tokens = collect_tokens(data_dir)
    if not tokens:
        # 数据初态（全部 pending）下 token 集为空 —— 这是合法状态，不报错
        return []
    pattern = _build_pattern(tokens)
    hits = []
    for path in _iter_source_files(root, targets or DEFAULT_TARGETS):
        with open(path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                found = pattern.findall(line)
                for token in sorted(set(found)):
                    hits.append({
                        "file": os.path.relpath(path, root).replace("\\", "/"),
                        "line": lineno,
                        "token": token,
                        "count": found.count(token),
                    })
    return hits


def _selftest(root, data_dir, tokens):
    """阳性对照：注入一个 token 的临时文件必须被命中。

    probe token 程序化合成（不复述任何真实政策数值，避免门禁脚本自身成为命中源）：
    优先取已采集 token 集里的一个真实值，否则用数字段拼接合成一个假值。
    """
    import tempfile
    if tokens:
        probe_tokens = list(tokens)
        probe = probe_tokens[0]
    else:
        digit = str(MIN_TOKEN_LEN)
        probe = digit + digit + digit
        probe_tokens = [probe]
    tmp_dir = tempfile.mkdtemp(prefix="ghg-zerolit-")
    probe_path = os.path.join(tmp_dir, "probe.py")
    with open(probe_path, "w", encoding="utf-8") as fh:
        fh.write("# 阳性对照\nVALUE = %s\n" % probe)
    pattern = _build_pattern(probe_tokens)
    with open(probe_path, "r", encoding="utf-8") as fh:
        found = pattern.findall(fh.read())
    os.remove(probe_path)
    os.rmdir(tmp_dir)
    if not found:
        print("阳性对照失败：注入的 token %r 未被门禁命中" % probe)
        return False
    print("阳性对照通过：注入 token %r 已被命中" % probe)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="零政策字面量门禁")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--selftest", action="store_true", help="跑阳性对照")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    data_dir = find_data_dir(args.data_dir or os.path.join(root, "data"))
    try:
        tokens = collect_tokens(data_dir)
    except GhgError as exc:
        print("门禁无法采集 token：%s" % exc)
        return 2

    print("政策数值 token 数：%d" % len(tokens))
    if tokens:
        preview = "、".join(tokens[:8])
        print("  示例：%s%s" % (preview, "…" if len(tokens) > 8 else ""))

    if args.selftest and not _selftest(root, data_dir, tokens):
        return 1

    hits = scan(root, data_dir, tokens=tokens)
    if not hits:
        print("源码零政策字面量检查通过（%s）" % OK_MARKER)
        return 0

    print("命中政策字面量（必须改为从规则包读取）：")
    for hit in hits:
        print("  %s:%d [%s] x%d" % (hit["file"], hit["line"], hit["token"], hit["count"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
