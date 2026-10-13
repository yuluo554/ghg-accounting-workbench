#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三维规则包生成器（data/rules/ 的唯一写入者）。

产出（全部为**冻结产物**，禁手改；改体例走本脚本整目录重生成）：
  * ``data/rules/units.json``                       单位换算表（定义性关系，verified）
  * ``data/rules/ruleset-<std>-<year>-<industry>.json`` × 40   三维坐标规则包
  * ``data/rules/manifest.json``                    坐标索引 + 各产物 sha256

M0 数据初态（刻意的诚实初态，见 plan/06 D0-7）：
  **全部政策数值字段为 ``null``、``status: "pending"``** —— 未挂官方原文核对不得生效。
  因此 ``ghg calc`` 在 M0 必然被门控拦截（退出码 1），这正是要演示的行为。
  真实数值与条款号由 M1 逐条核对后填回（并同步 config 内的出处引用）。

确定性纪律（NFR-04）：
  * 禁 stdlib ``random`` / 禁系统时钟 / 禁 set 迭代序；
  * 键排序固定（jsonio.write sort_keys=True）；一律 ``write_bytes``（LF，无 CRLF 漂移）；
  * 产物不含时间戳 —— ``provenance.generated_on`` 为固定发布日字符串。
"""

import hashlib
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg import jsonio  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
RULES_DIR = os.path.join(DATA_DIR, "rules")

GENERATOR_VERSION = "gen_rulesets/0.1.0"
GENERATED_ON = "2026-10-13"
CLAUSE_PENDING = {"code": None, "article": "待核对", "note": "条款要点与数值待官方原文核对（M1）"}

# --------------------------------------------------------------------------
# 坐标空间声明（本文件是坐标的**唯一真相源**；引擎代码内不得内联这些字面量）
# --------------------------------------------------------------------------
STANDARDS = [
    {
        "key": "gbt32150-2015",
        "code": "GB/T 32150-2015",
        "label": "工业企业温室气体排放核算和报告通则（旧版，废止）",
    },
    {
        "key": "gbt32150-2025",
        "code": "GB/T 32150-2025",
        "label": "工业企业温室气体排放核算和报告通则（新版，现行）",
    },
]

YEARS = [2022, 2023, 2024, 2025, 2026]

INDUSTRIES = [
    {"key": "power", "label": "发电"},
    {"key": "steel", "label": "钢铁"},
    {"key": "cement", "label": "水泥"},
    {"key": "aluminum", "label": "铝冶炼"},
]

# 排放源目录：结构脚手架（**哪些源适用属政策内容，M1 逐条核对**）。
# applicability 是结构性提示，实际纳入判据以核对后的 boundary.sources[].required 为准。
SOURCE_CATALOG = [
    {
        "id": "stationary_combustion",
        "name": "化石燃料燃烧排放",
        "category": "combustion",
        "applicability": ["power", "steel", "cement", "aluminum"],
    },
    {
        "id": "process_emission",
        "name": "工业生产过程排放",
        "category": "process",
        "applicability": ["steel", "cement", "aluminum"],
    },
    {
        "id": "purchased_electricity",
        "name": "净购入电力隐含排放",
        "category": "purchased_energy",
        "applicability": ["power", "steel", "cement", "aluminum"],
    },
    {
        "id": "purchased_heat",
        "name": "净购入热力隐含排放",
        "category": "purchased_energy",
        "applicability": ["power", "steel", "cement", "aluminum"],
    },
    {
        "id": "carbon_product",
        "name": "固碳产品隐含排放",
        "category": "carbon_product",
        "applicability": ["steel", "cement", "aluminum"],
    },
    {
        "id": "fugitive_emission",
        "name": "逃逸排放",
        "category": "other",
        "applicability": ["power"],
    },
]

QUALITY_RULES = [
    {
        "id": "Q-UNIT-01",
        "type": "unit_consistency",
        "level": "error",
        "name": "活动数据单位与因子单位口径不一致",
        "advice": "统一到规则包声明的基本单位后重新录入",
    },
    {
        "id": "Q-MAG-01",
        "type": "magnitude_outlier",
        "level": "warning",
        "name": "排放源活动数据/排放量超出规则包声明区间",
        "advice": "核对活动数据原始计量凭证与单位",
    },
    {
        "id": "Q-YOY-01",
        "type": "yoy_jump",
        "level": "warning",
        "name": "同一排放源跨年度变化率超过阈值",
        "advice": "提供变化原因说明（产量、工艺、计量口径变更）",
    },
    {
        "id": "Q-INT-01",
        "type": "intensity_plausibility",
        "level": "info",
        "name": "比强度指标是否落在行业合理区间",
        "advice": "结合产量与工艺核对比强度合理性",
    },
]

DISCLAIMER = (
    "本报告由本地核算工具生成，结果仅供企业内部参考；正式排放数据以主管部门核定结果、"
    "第三方核查机构结论为准。配额试算结果不构成任何配额分配承诺。"
)


def _pending(value=None, unit=None, ref=None):
    """构造一个未核对条目（value 为 null、status=pending）。"""
    entry = {"value": value, "status": "pending", "clause": dict(CLAUSE_PENDING)}
    if unit is not None:
        entry["unit"] = unit
    if ref is not None:
        entry["ref"] = ref
    return entry


def units_payload():
    """单位换算表：定义性关系（1 t = 1000 kg 等），非政策数值，故标 verified。"""
    dims = {
        "mass": {
            "base": "t",
            "units": {"t": 1, "kg": Decimal("0.001"), "kt": 1000},
        },
        "energy": {
            "base": "GJ",
            "units": {"GJ": 1, "MJ": Decimal("0.001"), "TJ": 1000},
        },
        "volume": {
            "base": "Nm3",
            "units": {"Nm3": 1, "万Nm3": 10000},
        },
        "electricity": {
            "base": "MWh",
            "units": {"MWh": 1, "kWh": Decimal("0.001"), "GWh": 1000, "万kWh": 10},
        },
        "emission": {
            "base": "tCO2e",
            "units": {"tCO2e": 1, "kgCO2e": Decimal("0.001")},
        },
        "ratio": {
            "base": "1",
            "units": {"1": 1, "%": Decimal("0.01")},
        },
    }
    return {
        "schema": "ghg-units/v1",
        "note": "单位换算因子为定义性关系（SI/法定计量单位定义），非政策数值；"
                "政策数值一律挂在规则包 status 门控之下。",
        "verified": True,
        "dimensions": dims,
    }


def _sources_for(industry):
    out = []
    for src in SOURCE_CATALOG:
        if industry not in src["applicability"]:
            continue
        out.append({
            "id": src["id"],
            "name": src["name"],
            "category": src["category"],
            "applicable_industries": list(src["applicability"]),
            "required": None,          # 政策内容：M1 核对
            "delta_vs_2015": None,     # 政策内容：M1 核对（same/added/removed/adjusted）
            "clause": dict(CLAUSE_PENDING),
            "status": "pending",
        })
    return out


def ruleset_payload(standard_key, year, industry_key):
    std = next(s for s in STANDARDS if s["key"] == standard_key)
    ind = next(i for i in INDUSTRIES if i["key"] == industry_key)
    coord = {"standard": standard_key, "year": year, "industry": industry_key}

    return {
        "schema": "ghg-ruleset/v1",
        "coordinate": coord,
        "standard": {
            "code": std["code"],
            "label": std["label"],
            "published": None,      # 待核对（M1 挂原文快照）
            "effective": None,
            "supersedes": None,
            "validity": None,
            "status": "pending",
            "clause": dict(CLAUSE_PENDING),
        },
        "boundary": {
            "sources": _sources_for(industry_key),
        },
        "engine": {
            "formula": {
                "id": "emission_basic",
                "name": "排放量 = 活动数据 × 排放因子 × 氧化率系数",
                "expr": {
                    "op": "mul",
                    "args": [
                        {"op": "var", "ref": "activity_data"},
                        {"op": "var", "ref": "emission_factor"},
                        {"op": "const", "ref": "oxidation_rate"},
                    ],
                },
                "clause": dict(CLAUSE_PENDING),
                "status": "pending",
            },
            "coefficients": {
                "oxidation_rate": _pending(unit="1"),
            },
        },
        "factors": {
            "priority": ["measured", "official_db", "industry_default"],
            "industry_default_values": {
                "default_factor": _pending(
                    unit="tCO2e_per_activity_unit",
                    ref={
                        "source": "国家温室气体排放因子数据库（第二版）",
                        "url": "待核对",
                        "version": "第二版",
                    },
                ),
            },
        },
        "quality": {
            "rules": [
                {
                    "id": rule["id"],
                    "type": rule["type"],
                    "level": rule["level"],
                    "name": rule["name"],
                    "advice": rule["advice"],
                    "clause": dict(CLAUSE_PENDING),
                    "status": "pending",
                }
                for rule in QUALITY_RULES
            ],
            "thresholds": {
                "magnitude": _pending(unit="ratio"),
                "yoy": _pending(unit="ratio"),
                "intensity_min": _pending(unit="tCO2e_per_unit_output"),
                "intensity_max": _pending(unit="tCO2e_per_unit_output"),
            },
        },
        "quota": {
            "allowed_methods": ["benchmark", "historical_intensity", "none"],
            "method": None,             # 政策内容：M1 核对（各行业方法学不同）
            "method_clause": dict(CLAUSE_PENDING),
            "params": {
                "benchmark_value": _pending(unit="tCO2e_per_unit_output"),
                "correction_factor": _pending(unit="1"),
            },
            "status": "pending",
        },
        "report": {
            "disclaimer": DISCLAIMER,
            "industry_label": ind["label"],
            "standard_code": std["code"],
        },
        "provenance": {
            "generator": GENERATOR_VERSION,
            "generated_on": GENERATED_ON,
            "source_ledger": "data/README.md §二 依据查证记录",
            "unverified_discipline": "未挂官方原文核对（status=pending）的条目不得进入计算路径",
        },
    }


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def generate(data_dir=None, verbose=True):
    rules_dir = os.path.join(data_dir or DATA_DIR, "rules")
    if not os.path.isdir(rules_dir):
        os.makedirs(rules_dir)

    # 1) units.json
    units_path = os.path.join(rules_dir, "units.json")
    jsonio.write(units_path, units_payload())

    # 2) 40 份规则包
    coord_entries = []
    for std in STANDARDS:
        for year in YEARS:
            for ind in INDUSTRIES:
                name = "ruleset-%s-%d-%s.json" % (std["key"], year, ind["key"])
                path = os.path.join(rules_dir, name)
                jsonio.write(path, ruleset_payload(std["key"], year, ind["key"]))
                coord_entries.append({
                    "standard": std["key"],
                    "year": year,
                    "industry": ind["key"],
                    "file": name,
                    "sha256": _sha256_file(path),
                })

    # 3) manifest.json（坐标索引 + 产物 sha256）
    manifest = {
        "schema": "ghg-manifest/v1",
        "generator": GENERATOR_VERSION,
        "generated_on": GENERATED_ON,
        "standards": [s["key"] for s in STANDARDS],
        "years": list(YEARS),
        "industries": [i["key"] for i in INDUSTRIES],
        "labels": {
            "standards": {s["key"]: s["label"] for s in STANDARDS},
            "industries": {i["key"]: i["label"] for i in INDUSTRIES},
        },
        "units_file": {
            "file": "units.json",
            "sha256": _sha256_file(units_path),
        },
        "coordinates": coord_entries,
    }
    jsonio.write(os.path.join(rules_dir, "manifest.json"), manifest)

    if verbose:
        print("已生成：%s" % rules_dir)
        print("  规则包 %d 份（全部 status=pending，等 M1 核对）" % len(coord_entries))
        print("  units.json + manifest.json")
    return manifest


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = DATA_DIR
    if argv:
        if len(argv) == 2 and argv[0] == "--data-dir":
            data_dir = argv[1]
        else:
            print("用法：python tools/gen_rulesets.py [--data-dir <目录>]")
            return 2
    generate(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
