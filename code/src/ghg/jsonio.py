"""确定性 JSON 读写（NFR-04 的实现基础）。

两条硬约束：
  1. **读**：``parse_float=Decimal``，float 永不进入计算路径；
  2. **写**：键排序固定、:class:`Decimal` 以裸数字字面量输出、缩进 2 空格、结尾单个换行、
     一律 UTF-8 且用 LF（``write_bytes``，绕开 Windows 默认 CRLF 的文本模式转换）。

为什么自写序列化而不用 ``json.dumps``：标准库无法把 Decimal 输出为"裸数字"
（``default=`` 只能产出字符串），而把数值写成带引号字符串会破坏数据文件的可读语义。
结构仅含 dict/list/str/int/bool/None/Decimal，自写 writer 足够且完全可控。
"""

import json
from decimal import Decimal

_INDENT = "  "


def loads(text):
    """解析 JSON 文本，float 转 Decimal。"""
    return json.loads(text, parse_float=Decimal)


def load(path):
    """读取 JSON 文件（UTF-8），float 转 Decimal。"""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh, parse_float=Decimal)


def _scalar_text(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError("不支持序列化的类型：%s" % type(value).__name__)


def dumps(obj, sort_keys=True):
    """确定性序列化：键排序固定 + 2 空格缩进 + 结尾换行。"""
    out = []

    def emit(node, depth):
        pad = _INDENT * depth
        inner = _INDENT * (depth + 1)
        if isinstance(node, dict):
            if not node:
                out.append("{}")
                return
            keys = sorted(node.keys()) if sort_keys else list(node.keys())
            out.append("{\n")
            for idx, key in enumerate(keys):
                out.append(inner)
                out.append(json.dumps(str(key), ensure_ascii=False))
                out.append(": ")
                emit(node[key], depth + 1)
                out.append(",\n" if idx < len(keys) - 1 else "\n")
            out.append(pad + "}")
        elif isinstance(node, (list, tuple)):
            if not node:
                out.append("[]")
                return
            out.append("[\n")
            for idx, item in enumerate(node):
                out.append(inner)
                emit(item, depth + 1)
                out.append(",\n" if idx < len(node) - 1 else "\n")
            out.append(pad + "]")
        else:
            out.append(_scalar_text(node))

    emit(obj, 0)
    return "".join(out) + "\n"


def write(path, obj, sort_keys=True):
    """以 LF + UTF-8 字节写入（不经过文本模式，杜绝 CRLF 漂移）。"""
    text = dumps(obj, sort_keys=sort_keys)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))
    return text
