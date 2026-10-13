"""单位换算（换算因子全部来自 data/rules/units.json）。

设计判断：单位换算因子是**定义性关系**（1 t = 1000 kg、1 GJ = 1000 MJ），不属于
"政策数值"（policy value），因此可在 M0 即标 verified —— 与"未核对的政策数值一律
pending"的纪律不冲突（见 plan/06 D0-8）。代码内不得内联任何换算数值（NFR-07）。
"""

import os

from . import jsonio
from .decimals import as_decimal
from .errors import UnitError

UNITS_FILE = "units.json"


class UnitTable(object):
    """量纲 → 基准单位 → 换算因子 的换算表。"""

    def __init__(self, raw):
        self._raw = raw
        self._dim_of = {}
        self._factor = {}
        for dimension, spec in raw.get("dimensions", {}).items():
            base = spec["base"]
            for unit, factor in spec["units"].items():
                if unit in self._dim_of:
                    raise UnitError("单位在多个量纲中重复定义：%s" % unit)
                self._dim_of[unit] = dimension
                self._factor[unit] = as_decimal(str(factor))
                # 基准单位自身因子应为 1，否则表内不一致
            if self._factor.get(base) != as_decimal(1):
                raise UnitError("量纲 %s 的基准单位 %s 换算因子必须为 1" % (dimension, base))

    @classmethod
    def load(cls, data_dir):
        path = os.path.join(data_dir, "rules", UNITS_FILE)
        if not os.path.isfile(path):
            raise UnitError("缺少单位换算表：%s" % path)
        with open(path, "r", encoding="utf-8") as fh:
            raw = jsonio.loads(fh.read())
        if raw.get("schema") != "ghg-units/v1":
            raise UnitError("单位表 schema 不受支持：%r" % raw.get("schema"))
        return cls(raw)

    def known(self, unit):
        return unit in self._dim_of

    def dimension_of(self, unit):
        try:
            return self._dim_of[unit]
        except KeyError:
            raise UnitError("未知单位：%s" % unit)

    def unit_list(self):
        return sorted(self._dim_of.keys())

    def dimensions(self):
        return dict(self._raw.get("dimensions", {}))

    def to_base(self, value, unit):
        dim = self.dimension_of(unit)
        base = self._raw["dimensions"][dim]["base"]
        return as_decimal(value) * self._factor[unit], base

    def convert(self, value, from_unit, to_unit):
        """同量纲换算；跨量纲直接报错（防止 t 换 MWh 这类量纲混用）。"""
        dim_from = self.dimension_of(from_unit)
        dim_to = self.dimension_of(to_unit)
        if dim_from != dim_to:
            raise UnitError(
                "量纲不一致，禁止换算：%s(%s) → %s(%s)"
                % (from_unit, dim_from, to_unit, dim_to)
            )
        # 经基准单位中转，保证往返一致（round-trip）
        base_value = as_decimal(value) * self._factor[from_unit]
        return base_value / self._factor[to_unit]


def default_table(data_dir):
    return UnitTable.load(data_dir)
