"""逐源核算与完整编排的计算内核（M2）。

职责边界：
  * 本模块**只消费已过门控的规则包**（由调用方先经 ``effective_ruleset(scope=calc)``）；
  * 数值全链路 :class:`Decimal`；单位换算一律经 :class:`ghg.units.UnitTable`；
  * 公式求值经 :mod:`ghg.engine`（表达式树来自规则包，非代码内联）。

M2 相对 M1 的三处升级：
  1. **边界识别接入**：纳入判定统一走 :func:`ghg.boundary.identify_boundary`，
     不再由本模块各自维护一份"哪些源要算"的判断（单一判定点）。
  2. **因子选择按类别分派**：``factors.industry_default_values`` 支持按
     ``category`` 覆盖（``by_category``）；无覆盖时回落到 ``default_factor``。
     优先级取规则包 ``factors.priority``（实测 > 官方因子库 > 行业缺省）；
     三层皆不可用 → :class:`FactorUnavailable`（退出码 2，不得静默取 0 或 1）。
  3. **单位换算显式化**（FR-02.3）：活动数据换算到规则包声明的基本单位；
     因子单位（``<排放单位>_per_<活动单位>``）换算到"每基本单位"；
     排放量再换算到 ``tCO2e``。换算因子全部取自 ``data/rules/units.json``。

行序按 ``source_id`` 排序（位级确定性，不依赖输入顺序）。
"""

from decimal import Decimal

from .boundary import identify_boundary
from .decimals import as_decimal, quantize, to_text
from .engine import collect_refs, evaluate, validate
from .errors import BoundaryError, CalcError, FactorUnavailable, UnitError
from .units import PER_SEPARATOR, split_compound_unit

UNIT_EMISSION = "tCO2e"

# 因子在报告中的呈现小数位（内部仍保留全精度求值）
FACTOR_PLACES = 6

# 氧化率系数仅对"燃烧类"源适用；其余源按恒等 1（FR-02.1「系数按源类型缺省为恒等」）。
_OXIDATION_CATEGORIES = ("combustion",)

# 档案自报因子来源的合法层级（其余一律视为输入不可用，避免"自称"绕过优先级）
_DECLARED_FACTOR_SOURCES = ("measured", "official_db", "industry_default")

# 复合因子单位的分隔符（定义在 units.py，避免第二份真相）
_PER_SEPARATOR = PER_SEPARATOR

# 无量纲单位的文本形态（换算表 ratio 量纲的基准）
_DIMENSIONLESS = ("1", "", None)

# 公式可用变量集（**单一真相源**）：引擎求值作用域提供的键。
# 规则包 ``engine.formula.expr`` 里的 ``var`` 引用必须落在该集合内（M4 自洽扫描依据，
# 见 plan/06 D4-3）——否则是"引用了引擎不提供的变量"，运行到一半才炸。
VAR_ACTIVITY = "activity_data"
VAR_FACTOR = "emission_factor"
VAR_OXIDATION = "oxidation_rate"
FORMULA_VARS = (VAR_ACTIVITY, VAR_FACTOR, VAR_OXIDATION)

# 仅燃烧类源注入的变量（其余源不提供）；用于"可选变量"与"必需变量"的区分。
OPTIONAL_FORMULA_VARS = (VAR_OXIDATION,)


def _factor_text(value):
    return to_text(quantize(value, FACTOR_PLACES), FACTOR_PLACES)


def _coefficient(pack, name):
    entry = pack.get("engine", {}).get("coefficients", {}).get(name)
    if entry is None:
        raise CalcError("规则包缺少系数：%s" % name)
    return entry


def _split_compound_unit(unit):
    """把 ``<排放单位>_per_<活动单位>`` 拆成二元组；非复合单位返回 (unit, None)。"""
    return split_compound_unit(unit)


class UnitChain(object):
    """显式单位换算链（FR-02.3）：活动数据 → 基本单位，因子 → 每基本单位，排放 → tCO2e。

    每一步都记录在 :meth:`trace` 里，供报告的"核算过程"与数据溯源表回指。
    """

    def __init__(self, units):
        self.units = units
        self.steps = []

    # ---- 活动数据 ----
    def activity_to_base(self, value, unit):
        """把活动数据换算到其量纲的基本单位；返回 (换算后数值, 基本单位)。"""
        value = as_decimal(value)
        if unit in _DIMENSIONLESS:
            return value, unit
        dimension = self.units.dimension_of(unit)
        base = self.units.dimensions()[dimension]["base"]
        if unit == base:
            return value, base
        converted = self.units.convert(value, unit, base)
        self.steps.append({
            "target": "activity",
            "from_unit": unit,
            "to_unit": base,
            "scale": str(self.units.scale(unit) / self.units.scale(base)),
        })
        return converted, base

    # ---- 排放因子 ----
    def factor_to_base(self, value, unit, activity_base):
        """把因子换算到"每活动基本单位"；返回 (换算后数值, 排放单位)。

        因子单位形如 ``tCO2e_per_t``：分母单位须与活动基本单位同量纲；
        分母换算因子取自 ``units.json``（换算因子 = 基本单位因子 / 分母单位因子）。
        """
        value = as_decimal(value)
        numerator, denominator = _split_compound_unit(unit)
        emission_unit = numerator or UNIT_EMISSION
        if denominator is None:
            # 非复合单位：视为"每基本单位"的缺省口径，不再换算
            return value, emission_unit
        if not self.units.known(denominator):
            raise UnitError("因子单位的分母未知：%s（因子单位 %s）" % (denominator, unit))
        if activity_base in _DIMENSIONLESS:
            raise UnitError(
                "活动数据无单位，无法换算因子 %s（因子分母 %s）" % (unit, denominator)
            )
        if self.units.dimension_of(denominator) != self.units.dimension_of(activity_base):
            raise UnitError(
                "因子分母与活动数据量纲不一致：%s(%s) vs %s(%s)"
                % (denominator, self.units.dimension_of(denominator),
                   activity_base, self.units.dimension_of(activity_base))
            )
        scale = self.units.scale(activity_base) / self.units.scale(denominator)
        if scale == 1:
            return value, emission_unit
        converted = value * scale
        self.steps.append({
            "target": "factor",
            "from_unit": unit,
            "to_unit": "%s%s%s" % (emission_unit, _PER_SEPARATOR, activity_base),
            "scale": str(scale),
        })
        return converted, emission_unit

    # ---- 排放量 ----
    def emission_to_unit(self, value, unit):
        """把排放量换算到 ``tCO2e``。"""
        value = as_decimal(value)
        if unit in _DIMENSIONLESS or unit == UNIT_EMISSION:
            return value
        if not self.units.known(unit):
            raise UnitError("排放量单位未知：%s" % unit)
        converted = self.units.convert(value, unit, UNIT_EMISSION)
        self.steps.append({
            "target": "emission",
            "from_unit": unit,
            "to_unit": UNIT_EMISSION,
            "scale": str(self.units.scale(unit) / self.units.scale(UNIT_EMISSION)),
        })
        return converted

    def trace(self):
        return list(self.steps)


def _default_factor_entry(pack, category):
    """按类别取行业缺省因子条目；无类别覆盖时回落 ``default_factor``。"""
    defaults = pack.get("factors", {}).get("industry_default_values", {}) or {}
    by_category = defaults.get("by_category") or {}
    if category and category in by_category:
        return by_category[category], "industry_default:%s" % category
    entry = defaults.get("default_factor")
    return entry, "industry_default"


def _select_factor(profile_source, pack, category):
    """按规则包优先级选择排放因子。

    返回 ``(value, unit, source_label, provenance)``。

    优先级：``measured``（档案实测）> ``official_db``（官方因子库）> ``industry_default``
    （规则包，按类别分派）。档案自报来源不在白名单内时按行业缺省处理（防"自称"绕过）。
    三层皆不可用 → :class:`FactorUnavailable`（退出码 2）。
    """
    priority = list(pack.get("factors", {}).get("priority") or ())
    declared = profile_source.get("factor")
    if declared and declared.get("value") is not None:
        label = declared.get("source")
        if label not in _DECLARED_FACTOR_SOURCES:
            raise FactorUnavailable(
                "档案自报因子来源非法：%r（允许：%s）"
                % (label, "、".join(_DECLARED_FACTOR_SOURCES))
            )
        if priority and label not in priority:
            raise FactorUnavailable(
                "档案自报因子来源 %r 不在规则包优先级 %s 内" % (label, priority)
            )
        if label == "industry_default":
            # 自报"行业缺省"时仍须与规则包缺省值对账，避免用任意数值冒名缺省因子
            entry, _ = _default_factor_entry(pack, category)
            expected = None if entry is None else entry.get("value")
            if expected is None or as_decimal(declared["value"]) != as_decimal(expected):
                raise FactorUnavailable(
                    "档案自报行业缺省因子，但数值与规则包缺省值不一致（源 %s）"
                    % profile_source.get("source_id")
                )
        return (
            as_decimal(declared["value"]),
            declared.get("unit"),
            label,
            {"declared_source": declared.get("source"), "ref": declared.get("ref")},
        )

    entry, label = _default_factor_entry(pack, category)
    if entry is None or entry.get("value") is None or entry.get("status") != "verified":
        raise FactorUnavailable(
            "排放源类别 %s 的行业缺省因子不可用（未核对或缺失）；"
            "实测/官方因子库亦未提供 → 不得静默取 0 或 1" % category
        )
    return (
        as_decimal(entry["value"]),
        entry.get("unit"),
        label,
        {"ref": entry.get("ref"), "clause": entry.get("clause")},
    )


def _oxidation_ratio(pack, category, units):
    """燃烧类源的氧化率系数（``%`` → 无量纲）；其余源恒等 1。"""
    if category not in _OXIDATION_CATEGORIES:
        return Decimal(1)
    entry = _coefficient(pack, "oxidation_rate")
    if entry.get("value") is None or entry.get("status") != "verified":
        raise CalcError("氧化率系数不可用（未核对）：oxidation_rate")
    unit = entry.get("unit")
    if unit in _DIMENSIONLESS:
        return as_decimal(entry["value"])
    return units.convert(as_decimal(entry["value"]), unit, "1")


def compute(payload, coord, pack, units):
    """逐源核算，返回结构化结果（含逐源明细、显式单位链与汇总）。

    纳入判定统一走 :func:`ghg.boundary.identify_boundary`；应核算源缺活动数据即抛
    :class:`BoundaryError`（退出码 2，不得静默按空核算）。
    """
    formula = pack.get("engine", {}).get("formula")
    if formula is None:
        raise CalcError("规则包缺少公式定义")
    expr = formula["expr"]
    validate(expr)
    refs = collect_refs(expr)

    include_optional = bool(payload.get("include_optional"))
    report = identify_boundary(payload, coord, pack, include_optional=include_optional)
    if report["missing_inputs"]:
        raise BoundaryError(
            "档案缺少应核算排放源的活动数据：%s（缺失输入 → 不得静默按空核算）"
            % "、".join(report["missing_inputs"])
        )

    catalog = {src["id"]: src for src in pack.get("boundary", {}).get("sources", [])}
    provided = {item["source_id"]: item for item in payload.get("sources", []) or []}

    lines = []
    total = Decimal(0)
    for sid in sorted(report["included"]):
        src = catalog[sid]
        item = provided[sid]
        category = src.get("category")
        activity = item.get("activity") or {}

        chain = UnitChain(units)
        act_value, act_base = chain.activity_to_base(activity["value"], activity.get("unit"))
        factor_value, factor_unit, factor_source, factor_prov = _select_factor(
            item, pack, category)
        factor_base, emission_unit = chain.factor_to_base(
            factor_value, factor_unit, act_base)
        oxidation = _oxidation_ratio(pack, category, units)

        scope = {
            VAR_ACTIVITY: act_value,
            VAR_FACTOR: factor_base,
        }
        if VAR_OXIDATION in refs:
            scope[VAR_OXIDATION] = oxidation

        emission = evaluate(expr, scope)
        emission = chain.emission_to_unit(emission, emission_unit)
        total += emission

        lines.append({
            "source_id": sid,
            "source_name": src.get("name"),
            "category": category,
            "activity": {"value": activity.get("value"), "unit": activity.get("unit")},
            "activity_base": {"value": to_text(act_value), "unit": act_base},
            "factor": {"value": _factor_text(factor_value), "unit": factor_unit,
                       "source": factor_source},
            "factor_base": {"value": _factor_text(factor_base),
                            "unit": "%s%s%s" % (emission_unit, _PER_SEPARATOR, act_base)},
            "oxidation_rate": str(oxidation),
            "unit_chain": chain.trace(),
            "emission": to_text(emission),
            "emission_raw": str(emission),
            "clause": src.get("clause"),
            "provenance": {
                "rule_entry_id": sid,
                "coordinate": coord.key,
                "source_clause": src.get("clause"),
                "factor": factor_prov,
            },
        })

    return {
        "coordinate": coord.as_dict(),
        "coordinate_key": coord.key,
        "unit": UNIT_EMISSION,
        "lines": lines,
        "total": to_text(total),
        "total_raw": str(total),
        "line_count": len(lines),
        "boundary": report,
        "schema": "ghg-calcresult/v1",
    }


def render_calc_text(payload, result):
    """人类可读的核算输出（CLI 用）。"""
    facility = (payload.get("facility") or {}).get("name") or "（未命名）"
    lines = [
        "企业温室气体排放核算结果",
        "  报告主体：%s" % facility,
        "  规则包坐标：%s" % result["coordinate_key"],
        "  应核算排放源：%d 项（纳入 %d 项）"
        % (result["boundary"]["required_count"], result["line_count"]),
    ]
    for line in result["lines"]:
        lines.append(
            "    - %s：活动数据 %s %s × 因子 %s（%s）× 氧化率 %s = %s %s"
            % (line["source_id"], line["activity"]["value"],
               line["activity"]["unit"] or "-", line["factor"]["value"],
               line["factor"]["source"], line["oxidation_rate"],
               line["emission"], UNIT_EMISSION))
    lines.append("  排放总量：%s %s" % (result["total"], UNIT_EMISSION))
    return "\n".join(lines)


def run_calc(payload, coord, pack, units):
    """CLI 用薄封装：返回 ``{payload, text}``（结构化 + 人类可读）。"""
    result = compute(payload, coord, pack, units)
    return {"payload": result, "text": render_calc_text(payload, result)}