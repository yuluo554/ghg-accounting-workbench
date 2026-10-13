#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成企业档案 + 植入真值生成器（data/truth/ 的唯一写入者）。

产出（冻结产物，禁手改；改体例走本脚本重生成）：
  * ``data/truth/profiles/<name>.json``  合成企业档案（虚构企业；仅活动数据，不含因子）
  * ``data/truth/expected.json``         植入真值（逐源分解 + 汇总 + 边界用例期望）

纪律：
  * **假企业白名单**：统一使用虚构名称（含「（合成）」后缀），统一社会信用代码为保留测试号段
    （``90000000000000000X`` 形态的虚构占位），不得与真实企业冲突；
  * **确定性 RNG**：自研 counter-mode（SHA-256），**禁 stdlib random**（NFR-04）；
  * **真值非手抄**：由本脚本按规则包（唯一政策数值真相源）逐源计算并写入；
    引擎（``ghg.calc``）以**独立代码路径**实现同一算式，由测试对账（双路对账）；
  * **边界用例**：另产出一个"缺应核算源"的档案，真值标注为期望错误（M2/M3 失败路径基准）。

真值算式（与通则 7.2.2 排放因子法一致）：
  排放量 = 活动数据 × 排放因子 × 氧化率系数
  * 排放因子取规则包 ``factors.industry_default_values.default_factor``（verified）；
  * 氧化率系数仅燃烧类源适用（取规则包 ``engine.coefficients.oxidation_rate``，
    ``%`` → 无量纲），其余源恒等 1。

确定性纪律（NFR-04）：无时间戳、键排序固定、``write_bytes``（LF）、无 set 迭代序。
"""

import hashlib
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg import jsonio  # noqa: E402
from ghg.rules import RulesIndex  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
TRUTH_DIR = os.path.join(DATA_DIR, "truth")
PROFILES_DIR = os.path.join(TRUTH_DIR, "profiles")

GENERATOR_VERSION = "gen_synthetic/0.1.0"
GENERATED_ON = "2026-10-13"

SEED = "ghg-synthetic-2026-10-13"

# 虚构企业名（自研白名单：统一「（合成）」后缀，任何真实企业均不含该后缀）
FACILITY_NAMES = {
    "power": "示例发电（合成）有限公司",
    "steel": "示例钢铁（合成）有限公司",
    "cement": "示例水泥（合成）有限公司",
    "aluminum": "示例铝业（合成）有限公司",
}

# 虚构统一社会信用代码前缀（保留测试号段，避免与真实企业冲突）
CREDIT_PREFIX = "90000000"
CREDIT_SUFFIX = "SYN"

# 活动数据抽取区间（按 category；确定性 RNG 在区间内取值，单位吨/万标方）
ACTIVITY_RANGE = {
    "combustion": (50000, 200000),
    "process": (1000, 20000),
    "purchased_energy": (1000, 50000),
    "carbon_product": (500, 8000),
    "other": (100, 3000),
}

# 每个行业产出的档案（坐标；year 用于选年度规则包）
PROFILE_PLAN = [
    ("power-2024", "gbt32150-2025", 2024, "power"),
    ("steel-2024", "gbt32150-2025", 2024, "steel"),
    ("cement-2024", "gbt32150-2025", 2024, "cement"),
    ("aluminum-2024", "gbt32150-2025", 2024, "aluminum"),
    ("steel-2023", "gbt32150-2025", 2023, "steel"),
    ("steel-2015-2024", "gbt32150-2015", 2024, "steel"),
]

# 附产量的档案（比强度校核 / 配额试算需要产量；其余档案不产产量以演示"跳过"分支）
PROFILES_WITH_OUTPUT = {"power-2024", "steel-2024", "cement-2024", "aluminum-2024",
                        "steel-2023"}

# 边界用例：虚构企业缺一个应核算源的活动数据 → 期望引擎报「缺少应核算排放源」
MISSING_SOURCE_CASE = ("steel-2024-missing-source", "gbt32150-2025", 2024, "steel",
                       "carbon_product")

# M2 扩充算例：单位换算（活动数据以 kg 录入，引擎须显式换算到 t 后与吨口径真值一致）
UNIT_CONVERSION_CASE = ("steel-2024-unit-kg", "gbt32150-2025", 2024, "steel")

# M2 扩充算例：因子来源优先级（实测因子 > 官方因子库 > 行业缺省）
#   显式因子数值取行业缺省值的一半，便于断言"确实用了档案因子而非缺省值"。
FACTOR_PRIORITY_CASE = (
    "steel-2024-measured-factor", "gbt32150-2025", 2024, "steel",
    {
        "stationary_combustion": {
            "value": "1.139248880",
            "unit": "tCO2e_per_t",
            "source": "measured",
            "ref": "示例检测报告（合成数据，非真实报告）",
        },
        "process_emission": {
            "value": "1.139248880",
            "unit": "tCO2e_per_t",
            "source": "official_db",
            "ref": "国家温室气体排放因子数据库（第二版）—— 摘录位（示例，非真实摘录）",
        },
    },
)

# M2 失败路径用例：因子三层皆不可用（引擎侧用空规则包触发 FactorUnavailable）
FACTOR_UNAVAILABLE_CASE = ("steel-2024-factor-unavailable", "gbt32150-2025", 2024, "steel")

# M2 失败路径用例：坏格式（活动数据缺数值）
BAD_FORMAT_CASE = ("steel-2024-bad-format", "gbt32150-2025", 2024, "steel")

# --------------------------------------------------------------------------
# M3：合成产量与异常算例（校核层命中率 / 误报率基准）
# --------------------------------------------------------------------------

# 各行业目标比强度（tCO2e / 单位产量）——取规则包 intensity 区间中部，
# 使"清洁档案"在比强度检查上不产生误报。
TARGET_INTENSITY = {
    "power": Decimal("0.75"),
    "steel": Decimal("2"),
    "cement": Decimal("0.8"),
    "aluminum": Decimal("3"),
}

# 产量单位（与行业计量口径一致）
OUTPUT_UNIT = {
    "power": "MWh",
    "steel": "t",
    "cement": "t",
    "aluminum": "t",
}

# 校核异常算例 1：单位错配（未被纳入核算的源录入未知单位）→ Q-UNIT-01 error。
# 说明：**已纳入核算**的源若单位量纲错配，引擎（calc）会先以退出码 2 拦截；
# 校核层的职责是拦住引擎容忍或忽略的录入问题（此处为选填源录入未知单位）。
BAD_UNIT_CASE = ("steel-2024-bad-unit", "gbt32150-2025", 2024, "steel")
BAD_UNIT_SOURCE = "purchased_electricity"
BAD_UNIT_VALUE = "stone"

# 校核异常算例 2：量级异常（单源排放量几乎等于全厂合计）→ Q-MAG-01 warning
MAGNITUDE_CASE = ("steel-2024-magnitude", "gbt32150-2025", 2024, "steel")

# 校核异常算例 3：跨年突变（活动数据同比放大 3 倍）→ Q-YOY-01 warning
#   误报对照：clean 档案与其基线**活动数据逐位相同**（变化率 0）→ 不得命中；
#   jump 档案在 clean 基础上把燃烧源活动数据放大 3 倍 → 命中。
YOY_BASELINE_CASE = ("steel-2023-yoy-baseline", "gbt32150-2025", 2023, "steel")
YOY_CLEAN_CASE = ("steel-2024-yoy-clean", "gbt32150-2025", 2024, "steel")
YOY_JUMP_CASE = ("steel-2024-yoy-jump", "gbt32150-2025", 2024, "steel")
YOY_JUMP_SOURCE = "stationary_combustion"
YOY_JUMP_FACTOR = 3

# 校核异常算例 4：比强度越界（产量压到 1/10 → 比强度 10 倍）→ Q-INT-01 info
INTENSITY_CASE = ("steel-2024-intensity", "gbt32150-2025", 2024, "steel")
INTENSITY_DIVISOR = 10

# 配额试算算例（FR-05）：方法学分支 + 外部输入索取 + 失败路径
QUOTA_BENCHMARK_CASE = ("power-2025", "gbt32150-2025", 2025, "power")
# 三行业配额算例复用已产出的 steel-2024 档案（含产量），避免重复档案
QUOTA_INTENSITY_CASE = ("steel-2024", "gbt32150-2025", 2024, "steel")
# 发电：调峰修正系数属"随机组而异"的外部输入；算例显式给出一个合成值
QUOTA_BENCHMARK_CORRECTION = Decimal("0.97")
# 三行业：行业平衡值（BP）平台可查 → 算例显式给出一个合成值
QUOTA_INTENSITY_BENCHMARK = Decimal("2.1")


class DeterministicRng(object):
    """counter-mode SHA-256 确定性伪随机数发生器（禁 stdlib random）。"""

    def __init__(self, seed, label):
        self._seed = ("%s|%s" % (seed, label)).encode("utf-8")
        self._counter = 0
        self._buf = b""

    def _next_byte(self):
        if not self._buf:
            h = hashlib.sha256(self._seed + b"|%d" % self._counter).digest()
            self._buf = h
            self._counter += 1
        byte = self._buf[0]
        self._buf = self._buf[1:]
        return byte

    def randint(self, low, high):
        """闭区间 [low, high] 内取整（拒绝采样，避免模偏差）。"""
        span = high - low + 1
        if span <= 0:
            raise ValueError("区间非法：%d..%d" % (low, high))
        n = span.bit_length() + 8
        while True:
            value = 0
            for _ in range((n + 7) // 8):
                value = (value << 8) | self._next_byte()
            value &= (1 << n) - 1
            if value < span * ((1 << n) // span):
                return low + (value % span)


def _to_ratio(units, value, unit):
    if unit in (None, "", "1"):
        return Decimal(str(value))
    return units.convert(str(value), unit, "1")


def build_profile(index, units, name, standard, year, industry,
                  unit_overrides=None, factor_overrides=None,
                  include_output=False, output_divisor=None, activity_scale=None):
    """构造一个档案（活动数据由确定性 RNG 生成）。

    * ``unit_overrides``：``{source_id: unit}`` —— 活动数据单位覆盖（用于单位换算算例）；
    * ``factor_overrides``：``{source_id: factor_entry}`` —— 显式因子（实测/官方库算例）；
    * ``include_output``：是否附产量（比强度校核 / 配额试算需要）；
    * ``output_divisor``：产量除数（默认 1；用于构造"比强度越界"算例）；
    * ``activity_scale``：``{source_id: 倍数}`` —— 活动数据放大（用于构造"跨年突变"算例）。
    """
    coord = index.resolve(standard, year, industry)
    pack = index.pack(coord)                     # 预览（生成器是真相源，允许读全部块）
    rng = DeterministicRng(SEED, name)
    unit_overrides = unit_overrides or {}
    factor_overrides = factor_overrides or {}
    activity_scale = activity_scale or {}
    sources = []
    for src in pack["boundary"]["sources"]:
        if src.get("required") is not True:
            continue
        low, high = ACTIVITY_RANGE.get(src["category"], (1, 1000))
        value = rng.randint(low, high) * activity_scale.get(src["id"], 1)
        item = {
            "source_id": src["id"],
            "activity": {"value": str(value),
                         "unit": unit_overrides.get(src["id"], "t")},
        }
        if src["id"] in factor_overrides:
            item["factor"] = factor_overrides[src["id"]]
        sources.append(item)
    profile = {
        "schema": "ghg-profile/v1",
        "coordinate": {"standard": standard, "year": year, "industry": industry},
        "facility": {
            "name": FACILITY_NAMES[industry],
            "credit_code": "%s%s%s" % (CREDIT_PREFIX, name.replace("-", ""), CREDIT_SUFFIX),
            "synthetic": True,
            "note": "虚构企业（合成数据），非真实企业；不得用于对外披露",
        },
        "sources": sources,
    }
    if include_output:
        profile["output"] = {
            "value": str(_output_for(units, sources, pack, industry, output_divisor)),
            "unit": OUTPUT_UNIT.get(industry, "t"),
        }
    return profile


def _output_for(units, sources, pack, industry, divisor):
    """按目标比强度反推产量（合成算例用；与行业缺省因子一致）。"""
    factor = Decimal(str(pack["factors"]["industry_default_values"]["default_factor"]["value"]))
    ox = pack["engine"]["coefficients"]["oxidation_rate"]
    oxidation = _to_ratio(units, ox["value"], ox.get("unit"))
    total = Decimal(0)
    for item in sources:
        sid = item["source_id"]
        category = next(s["category"] for s in pack["boundary"]["sources"] if s["id"] == sid)
        activity = Decimal(str(item["activity"]["value"]))
        total += activity * factor * (oxidation if category == "combustion" else Decimal(1))
    divisor = divisor or 1
    return (total / TARGET_INTENSITY[industry] / Decimal(divisor)).quantize(Decimal(1))


def _factor_entry_for(pack, sid, category, profile_item):
    """因子选择（生成器侧独立实现，与引擎 :func:`ghg.calc._select_factor` 对账）。

    返回 ``(factor_value_quantized, factor_unit, source_label)``。
    优先级：档案显式因子（measured/official_db）> 规则包类别缺省 > 规则包默认缺省。
    """
    declared = profile_item.get("factor")
    if declared and declared.get("value") is not None:
        label = declared.get("source")
        if label not in ("measured", "official_db"):
            label = "industry_default"
        return Decimal(str(declared["value"])), declared.get("unit"), label
    defaults = pack["factors"]["industry_default_values"]
    by_category = defaults.get("by_category") or {}
    entry = by_category.get(category) if category in by_category else defaults["default_factor"]
    if entry.get("status") != "verified" or entry.get("value") is None:
        raise SystemExit("规则包 %s 的行业缺省因子（%s）未核对，无法植入真值" % (pack, category))
    return Decimal(str(entry["value"])), entry.get("unit"), "industry_default"


def _factor_to_base(units, value, unit, activity_base):
    """因子单位 ``tCO2e_per_<活动单位>`` → 每活动基本单位（独立实现）。"""
    if not unit or "_per_" not in unit:
        return value, unit or "tCO2e"
    emission_unit, denominator = unit.split("_per_", 1)
    scale = units.scale(activity_base) / units.scale(denominator)
    return value * scale, emission_unit


def compute_truth(index, units, profile):
    """按规则包逐源计算真值（独立于 ghg.calc 的代码路径）。"""
    coord_raw = profile["coordinate"]
    coord = index.resolve(coord_raw["standard"], coord_raw["year"], coord_raw["industry"])
    pack = index.pack(coord)
    ox_entry = pack["engine"]["coefficients"]["oxidation_rate"]
    if ox_entry.get("status") != "verified" or ox_entry.get("value") is None:
        raise SystemExit("规则包 %s 的氧化率系数未核对，无法植入真值" % coord.key)
    oxidation = _to_ratio(units, ox_entry["value"], ox_entry.get("unit"))

    catalog = {s["id"]: s for s in pack["boundary"]["sources"]}
    lines = []
    total = Decimal(0)
    for item in sorted(profile["sources"], key=lambda s: s["source_id"]):
        sid = item["source_id"]
        src = catalog[sid]
        activity_unit = item["activity"].get("unit")
        activity = Decimal(str(item["activity"]["value"]))
        if activity_unit in (None, "", "1"):
            activity_base_unit = activity_unit
        else:
            activity_base_unit = units.base_of(activity_unit)
            if activity_unit != activity_base_unit:
                activity = units.convert(activity, activity_unit, activity_base_unit)

        factor, factor_unit, _label = _factor_entry_for(pack, sid, src["category"], item)
        factor_base, emission_unit = _factor_to_base(units, factor, factor_unit,
                                                     activity_base_unit)
        ox = oxidation if src["category"] == "combustion" else Decimal(1)
        emission = activity * factor_base * ox
        if emission_unit != "tCO2e":
            emission = units.convert(emission, emission_unit, "tCO2e")
        total += emission
        lines.append({
            "source_id": sid,
            "category": src["category"],
            "activity": str(activity),
            "factor": str(factor_base),
            "oxidation_rate": str(ox),
            "emission": str(emission),
        })
    return {
        "coordinate": coord.key,
        "lines": lines,
        "total": str(total),
        "index": pack.get("factors", {}).get("priority", []),
    }


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _quota_truth(index, units, profile, benchmark_value=None, correction_factor=None):
    """配额试算真值（生成器侧独立实现，与 ghg.quota 对账）。

    公式与方案原文一致（见 data/knowledge/raw/quota-plan.txt）：
      基准法     A = 产量 × 基准值 × 调峰修正系数
      强度系数法 A = 排放量 × (1 + α)，α 由偏离度 X=(BP−Ii)/BP 经表 3 分段得出。
    """
    coord_raw = profile["coordinate"]
    coord = index.resolve(coord_raw["standard"], coord_raw["year"], coord_raw["industry"])
    pack = index.pack(coord)
    quota = pack["quota"]
    method = quota["method"]
    truth = compute_truth(index, units, profile)
    actual = Decimal(truth["total"])
    output = Decimal(str(profile["output"]["value"]))
    if method == "benchmark":
        benchmark = Decimal(str(quota["params"]["benchmark_value"]["value"]))
        factor = Decimal(str(correction_factor))
        allocated = output * benchmark * factor
    elif method == "intensity_coefficient":
        benchmark = Decimal(str(benchmark_value))
        derivation = quota["derivation"]
        slope = Decimal(str(derivation["slope"]["value"]))
        band = Decimal(str(derivation["band"]["value"]))
        cap = Decimal(str(derivation["cap"]["value"]))
        intensity = actual / output
        x = (benchmark - intensity) / benchmark
        if x >= band:
            alpha = cap
        elif x <= -band:
            alpha = -cap
        else:
            alpha = slope * x
        allocated = actual * (Decimal(1) + alpha)
    else:
        raise SystemExit("配额方法学 %s 无法在生成器侧植入真值" % method)
    gap = allocated - actual
    return {
        "actual": str(actual),
        "allocated": str(allocated),
        "gap": str(gap),
        "gap_ratio": str(gap / actual),
    }


def generate(data_dir=None, verbose=True):
    data_root = data_dir or DATA_DIR
    truth_dir = os.path.join(data_root, "truth")
    profiles_dir = os.path.join(truth_dir, "profiles")
    if not os.path.isdir(profiles_dir):
        os.makedirs(profiles_dir)

    index = RulesIndex.load(data_root)
    from ghg.units import UnitTable
    units = UnitTable.load(data_root)

    expected = {
        "schema": "ghg-truth/v1",
        "generator": GENERATOR_VERSION,
        "generated_on": GENERATED_ON,
        "seed": SEED,
        "profiles": {},
        "cases": {},
    }

    for name, standard, year, industry in PROFILE_PLAN:
        profile = build_profile(index, units, name, standard, year, industry,
                                include_output=name in PROFILES_WITH_OUTPUT)
        path = os.path.join(profiles_dir, name + ".json")
        jsonio.write(path, profile)
        truth = compute_truth(index, units, profile)
        expected["profiles"][name] = {
            "file": "profiles/%s.json" % name,
            "sha256": _sha256_file(path),
            "coordinate": truth["coordinate"],
            "line_count": len(truth["lines"]),
            "lines": truth["lines"],
            "total": truth["total"],
        }

    # 边界用例 1：缺应核算源 → 期望失败（M2/M3 失败路径基准）
    name, standard, year, industry, missing = MISSING_SOURCE_CASE
    profile = build_profile(index, units, name, standard, year, industry)
    profile["sources"] = [s for s in profile["sources"] if s["source_id"] != missing]
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["missing_required_source"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "missing_source_id": missing,
        "expected": "error_missing_required_source",
    }

    # 边界用例 2：跨坐标混算 → 期望失败（混算拦截基准）
    mixed = {
        "schema": "ghg-profile/v1",
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "baseline": {"standard": "gbt32150-2015", "year": 2023, "industry": "steel"},
        "facility": {"name": "混算（合成）", "synthetic": True},
        "sources": [],
    }
    mixed_path = os.path.join(profiles_dir, "mixed-coordinates.json")
    jsonio.write(mixed_path, mixed)
    expected["cases"]["mixed_coordinates"] = {
        "file": "profiles/mixed-coordinates.json",
        "sha256": _sha256_file(mixed_path),
        "expected": "error_mixed_coordinates",
    }

    # M2 扩充算例：显式单位换算（kg → t）→ 真值须与吨口径一致
    name, standard, year, industry = UNIT_CONVERSION_CASE
    profile = build_profile(index, units, name, standard, year, industry,
                            unit_overrides={"stationary_combustion": "kg"})
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    truth = compute_truth(index, units, profile)
    expected["profiles"][name] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": truth["coordinate"],
        "line_count": len(truth["lines"]),
        "lines": truth["lines"],
        "total": truth["total"],
        "note": "stationary_combustion 活动数据以 kg 录入，引擎须显式换算到 t",
    }

    # M2 扩充算例：因子来源优先级（实测 / 官方因子库覆盖行业缺省）
    name, standard, year, industry, overrides = FACTOR_PRIORITY_CASE
    profile = build_profile(index, units, name, standard, year, industry,
                            factor_overrides=overrides)
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    truth = compute_truth(index, units, profile)
    expected["profiles"][name] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": truth["coordinate"],
        "line_count": len(truth["lines"]),
        "lines": truth["lines"],
        "total": truth["total"],
        "note": "显式因子（实测 / 官方因子库）优先于行业缺省",
    }

    # M2 失败路径用例：因子三层皆不可用 → 期望 FactorUnavailable（退出码 2）
    name, standard, year, industry = FACTOR_UNAVAILABLE_CASE
    profile = build_profile(index, units, name, standard, year, industry)
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["factor_unavailable"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "expected": "error_factor_unavailable",
        "note": "引擎按空规则包（缺 factors 块）核算时应报 FactorUnavailable",
    }

    # M2 失败路径用例：坏格式（活动数据缺数值）→ 期望 BoundaryError（退出码 2）
    name, standard, year, industry = BAD_FORMAT_CASE
    profile = build_profile(index, units, name, standard, year, industry)
    profile["sources"][0]["activity"]["value"] = None
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["bad_format_missing_activity_value"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "expected": "error_missing_activity_value",
        "note": "档案存在该源条目但 activity.value 为 null → 按缺输入处理（退出码 2）",
    }

    # ------------------------------------------------------------------
    # M3：校核层异常算例（命中率 / 误报率基准）
    # ------------------------------------------------------------------

    # 校核异常 1：单位错配（选填源录入未知单位）→ Q-UNIT-01 error
    name, standard, year, industry = BAD_UNIT_CASE
    profile = build_profile(index, units, name, standard, year, industry, include_output=True)
    profile["sources"].append({
        "source_id": BAD_UNIT_SOURCE,
        "activity": {"value": "1000", "unit": BAD_UNIT_VALUE},
    })
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["quality_bad_unit"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "expected_rule": "Q-UNIT-01",
        "expected_level": "error",
        "expected_source_id": BAD_UNIT_SOURCE,
        "note": "未被纳入核算的选填源录入未知单位 → 校核层命中单位一致性检查",
    }

    # 校核异常 2：量级异常（单源排放量几乎等于全厂合计）→ Q-MAG-01 warning
    name, standard, year, industry = MAGNITUDE_CASE
    profile = build_profile(index, units, name, standard, year, industry, include_output=True,
                            activity_scale={"stationary_combustion": 200})
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["quality_magnitude_outlier"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "expected_rule": "Q-MAG-01",
        "expected_level": "warning",
        "expected_source_id": "stationary_combustion",
        "note": "燃烧源活动数据放大 200 倍 → 单源排放量占比超过规则包量级阈值",
    }

    # 校核异常算例 3：跨年突变（活动数据同比放大 3 倍）→ Q-YOY-01 warning
    #   误报对照：clean 档案与其基线**活动数据逐位相同**（变化率 0）→ 不得命中；
    #   jump 档案在 clean 基础上把燃烧源活动数据放大 3 倍 → 命中。
    cname, cstd, cyear, cind = YOY_CLEAN_CASE
    clean_profile = build_profile(index, units, cname, cstd, cyear, cind, include_output=True)
    bname, bstd, byear, bind = YOY_BASELINE_CASE
    baseline_profile = jsonio.loads(jsonio.dumps(clean_profile))   # 逐位复制活动数据
    baseline_profile["coordinate"] = {"standard": bstd, "year": byear, "industry": bind}
    baseline_profile["facility"]["credit_code"] = "%s%s%s" % (
        CREDIT_PREFIX, bname.replace("-", ""), CREDIT_SUFFIX)
    baseline_profile["facility"]["name"] = FACILITY_NAMES[bind]
    for path, prof in ((os.path.join(profiles_dir, cname + ".json"), clean_profile),
                       (os.path.join(profiles_dir, bname + ".json"), baseline_profile)):
        jsonio.write(path, prof)
    jname, jstd, jyear, jind = YOY_JUMP_CASE
    # jump 档案由 clean 档案逐位复制后**只放大目标源**，保证唯一变量是跨年突变
    jump_profile = jsonio.loads(jsonio.dumps(clean_profile))
    jump_profile["coordinate"] = {"standard": jstd, "year": jyear, "industry": jind}
    jump_profile["facility"]["credit_code"] = "%s%s%s" % (
        CREDIT_PREFIX, jname.replace("-", ""), CREDIT_SUFFIX)
    for item in jump_profile["sources"]:
        if item["source_id"] == YOY_JUMP_SOURCE:
            item["activity"]["value"] = str(
                Decimal(item["activity"]["value"]) * Decimal(YOY_JUMP_FACTOR))
    # 同步放大产量，使比强度与 clean 档案一致（隔离变量：本算例只考察跨年突变）
    clean_total = Decimal(compute_truth(index, units, clean_profile)["total"])
    jump_total = Decimal(compute_truth(index, units, jump_profile)["total"])
    if clean_total != 0:
        jump_profile["output"]["value"] = str(
            (Decimal(str(clean_profile["output"]["value"])) * jump_total / clean_total)
            .quantize(Decimal(1)))
    jsonio.write(os.path.join(profiles_dir, jname + ".json"), jump_profile)
    expected["cases"]["quality_yoy_jump"] = {
        "baseline_file": "profiles/%s.json" % YOY_BASELINE_CASE[0],
        "baseline_sha256": _sha256_file(os.path.join(profiles_dir, YOY_BASELINE_CASE[0] + ".json")),
        "clean_file": "profiles/%s.json" % YOY_CLEAN_CASE[0],
        "clean_sha256": _sha256_file(os.path.join(profiles_dir, YOY_CLEAN_CASE[0] + ".json")),
        "file": "profiles/%s.json" % YOY_JUMP_CASE[0],
        "sha256": _sha256_file(os.path.join(profiles_dir, YOY_JUMP_CASE[0] + ".json")),
        "coordinate": "%s/%d/%s" % (YOY_JUMP_CASE[1], YOY_JUMP_CASE[2], YOY_JUMP_CASE[3]),
        "baseline_coordinate": "%s/%d/%s" % (YOY_BASELINE_CASE[1], YOY_BASELINE_CASE[2],
                                             YOY_BASELINE_CASE[3]),
        "expected_rule": "Q-YOY-01",
        "expected_level": "warning",
        "expected_source_id": YOY_JUMP_SOURCE,
        "note": "clean 档案同比未放大（不命中，误报对照）；jump 档案同比放大 3 倍（命中）",
    }

    # 校核异常 4：比强度越界（产量压到 1/10）→ Q-INT-01 info
    name, standard, year, industry = INTENSITY_CASE
    profile = build_profile(index, units, name, standard, year, industry, include_output=True,
                            output_divisor=INTENSITY_DIVISOR)
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    expected["cases"]["quality_intensity_out_of_range"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "expected_rule": "Q-INT-01",
        "expected_level": "info",
        "note": "产量压到 1/10 → 比强度约放大 10 倍，越出规则包区间",
    }

    # ------------------------------------------------------------------
    # M3：配额试算算例（方法学分支 + 外部输入索取）
    # ------------------------------------------------------------------

    # 发电（基准法）：调峰修正系数属外部输入，算例显式给出合成值
    name, standard, year, industry = QUOTA_BENCHMARK_CASE
    profile = build_profile(index, units, name, standard, year, industry, include_output=True)
    path = os.path.join(profiles_dir, name + ".json")
    jsonio.write(path, profile)
    qtruth = _quota_truth(index, units, profile,
                          correction_factor=QUOTA_BENCHMARK_CORRECTION)
    expected["cases"]["quota_benchmark"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(path),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "method": "benchmark",
        "correction_factor": str(QUOTA_BENCHMARK_CORRECTION),
        "expected": qtruth,
        "note": "发电 2025 基准值规则包已核对；调峰修正系数由算例显式提供（外部输入）",
    }

    # 三行业（强度系数法）：行业平衡值平台可查 → 算例显式给出合成值
    name, standard, year, industry = QUOTA_INTENSITY_CASE
    profile = jsonio.load(os.path.join(profiles_dir, name + ".json"))
    qtruth = _quota_truth(index, units, profile,
                          benchmark_value=QUOTA_INTENSITY_BENCHMARK)
    expected["cases"]["quota_intensity_coefficient"] = {
        "file": "profiles/%s.json" % name,
        "sha256": _sha256_file(os.path.join(profiles_dir, name + ".json")),
        "coordinate": "%s/%d/%s" % (standard, year, industry),
        "method": "intensity_coefficient",
        "benchmark_value": str(QUOTA_INTENSITY_BENCHMARK),
        "expected": qtruth,
        "note": "行业平衡值（BP）平台可查 → 算例显式提供；α 由偏离度经规则包分段常数推出",
    }

    # 失败路径：三行业未提供行业平衡值 → 期望 QuotaUnavailable（退出码 2，不得静默取 0）
    expected["cases"]["quota_missing_benchmark"] = {
        "file": "profiles/%s.json" % QUOTA_INTENSITY_CASE[0],
        "sha256": _sha256_file(os.path.join(profiles_dir, QUOTA_INTENSITY_CASE[0] + ".json")),
        "coordinate": "%s/%d/%s" % (QUOTA_INTENSITY_CASE[1], QUOTA_INTENSITY_CASE[2],
                                    QUOTA_INTENSITY_CASE[3]),
        "expected": "error_quota_unavailable",
        "note": "行业平衡值为外部输入，未提供时试算层必须硬失败（不得静默取 0）",
    }

    # 方法学 none 分支：注入一个声明"不适用"的坐标包（机制演示，不落盘为规则产物）
    expected["cases"]["quota_method_none"] = {
        "coordinate": "%s/%d/%s" % (QUOTA_BENCHMARK_CASE[1], QUOTA_BENCHMARK_CASE[2],
                                    QUOTA_BENCHMARK_CASE[3]),
        "expected": "not_applicable",
        "note": "规则包 quota.method=none 时试算显式返回 not_applicable（配额量为 None，非 0）",
    }

    # ------------------------------------------------------------------
    # M4：内置基准的**对照集声明**（数据驱动；基准层不内联档案名）
    # ------------------------------------------------------------------
    # 误报率的分母 = quality_clean 里全部"应零命中"的档案；
    # 分子 = 其中实际命中任一问题的档案数（干净档案命中即误报）。
    expected["controls"] = {
        "quality_clean": [
            {"file": "profiles/%s.json" % name,
             "note": "常规档案：四类检查应零命中（含产量，比强度落在规则包区间内）"}
            for name in sorted(PROFILES_WITH_OUTPUT)
        ] + [
            {"file": "profiles/steel-2024-measured-factor.json",
             "note": "实测因子档案：因子来源合法、单位口径一致 → 零命中"},
            {"file": "profiles/steel-2015-2024.json",
             "note": "旧版通则档案：跨版本不引入校核误报"},
        ],
        "quality_yoy_clean": {
            "file": "profiles/%s.json" % YOY_CLEAN_CASE[0],
            "baseline_file": "profiles/%s.json" % YOY_BASELINE_CASE[0],
            "note": "同比活动数据逐位相同（变化率 0）→ 跨年突变检查不得命中（误报对照）",
        },
        # 分级降级对照：命中但**可换算/可解释** → 只报 warning/info，不得升为 error
        "quality_non_error": [
            {"file": "profiles/%s.json" % UNIT_CONVERSION_CASE[0],
             "note": "kg 录入可显式换算 → Q-UNIT-01 降级为 warning（plan/06 D3-4）"},
        ],
    }

    jsonio.write(os.path.join(truth_dir, "expected.json"), expected)
    if verbose:
        print("已生成：%s" % truth_dir)
        print("  档案 %d 份 + 边界用例 %d 例" % (len(expected["profiles"]), len(expected["cases"])))
    return expected


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = DATA_DIR
    if argv:
        if len(argv) == 2 and argv[0] == "--data-dir":
            data_dir = argv[1]
        else:
            print("用法：python tools/gen_synthetic.py [--data-dir <目录>]")
            return 2
    generate(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
