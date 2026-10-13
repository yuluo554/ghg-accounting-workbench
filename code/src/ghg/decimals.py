"""Decimal 精度约定与转换工具。

为什么不用 float：排放量需逐项可核证，float 尾差会让"同一输入两次结果不同"，
直接违反 NFR-04（确定性）与 NFR-05（Decimal 精度）。

精度位用 ``Decimal(1).scaleb(-n)`` 表达而非小数字面量 —— 避免与
"零政策字面量门禁"的数值 token 判定互相污染（plan/03 §五、plan/06 §二）。
"""

from decimal import Decimal, ROUND_HALF_UP

# 内部计算精度（有效位数）
PRECISION = 28

# 输出呈现小数位（排放量 tCO2e 保留 3 位，符合常规盘查报告口径）
OUTPUT_PLACES = 3

# 中间比强度等辅助量的小数位
RATIO_PLACES = 6


def scale_for(places):
    """返回指定小数位的量化刻度，如 places=3 → Decimal('0.001')。"""
    if not isinstance(places, int) or places < 0:
        raise ValueError("places 必须为非负整数")
    return Decimal(1).scaleb(-places)


def as_decimal(value):
    """把 int/str/Decimal 转成 Decimal；显式拒绝 float。

    拒绝 float 是刻意的：允许 float 会让尾差从入口渗入计算路径。
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("bool 不是合法数值输入")
    if isinstance(value, float):
        raise TypeError(
            "禁止 float 进入计算路径；请用字符串或 Decimal 表达数值（见 plan/03 §五）"
        )
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value.strip())
    raise TypeError("无法转换为 Decimal：%r" % (type(value).__name__,))


def quantize(value, places=OUTPUT_PLACES):
    """按指定小数位四舍五入（ROUND_HALF_UP）—— 呈现口径。"""
    return as_decimal(value).quantize(scale_for(places), rounding=ROUND_HALF_UP)


def to_text(value, places=OUTPUT_PLACES):
    """量化后转字符串（避免科学计数法，报告与 CSV 友好）。"""
    q = quantize(value, places)
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
