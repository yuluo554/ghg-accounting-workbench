#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三维规则包生成器（data/rules/ 的唯一写入者）。

产出（全部为**冻结产物**，禁手改；改体例走本脚本整目录重生成）：
  * ``data/rules/units.json``                       单位换算表（定义性关系，verified）
  * ``data/rules/ruleset-<std>-<year>-<industry>.json`` × 40   三维坐标规则包
  * ``data/rules/manifest.json``                    坐标索引 + 各产物 sha256

M1 数据态（数据先行，逐条挂官方原文核对）：
  * 通则元数据（发布/实施日期、代替关系、有效性）：官方原文核对 → ``verified``；
  * 排放源纳入（``boundary.sources[].required`` / ``delta_vs_2015``）：行业指南 §5.2 +
    通则 2025 前言主要技术变化 → ``verified``；
  * 公式条款（通则 7.2.2 排放因子法 + 行业指南 6.1.1/6.1 公式(1)）→ ``verified``；
  * 系数与行业缺省因子（单位热值含碳量 / 氧化率缺省值）→ 有官方缺省值者 ``verified``，
    无（改由因子库取值等）者 ``pending`` 并写明原因；
  * 配额方法学：发电行业基准值官方公布 → ``verified``；三行业「平衡值」仅平台可查 → ``pending``。

**未核对不得生效**：任何 ``status: "pending"`` 或 ``value: null`` 的条目都不进入计算路径
（门控单点 ``RulesIndex.effective_ruleset``，范围 = 计算路径所引用的块）。

数据纪律（NFR-04）：
  * 禁 stdlib ``random`` / 禁系统时钟 / 禁 set 迭代序；
  * 键排序固定（jsonio.write sort_keys=True）；一律 ``write_bytes``（LF，无 CRLF 漂移）；
  * 产物不含时间戳 —— ``provenance.generated_on`` 为固定发布日字符串。

出处台账：``data/README.md`` §二 依据查证记录（含各条 URL / 文号 / 日期 / 快照 sha256）。
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

GENERATOR_VERSION = "gen_rulesets/0.3.0"
GENERATED_ON = "2026-10-13"

# --------------------------------------------------------------------------
# 内置基准的验收门槛（M4）——**门槛是数据，不是代码**（见 plan/06 D4-1）
# --------------------------------------------------------------------------
# 与"零政策字面量"同一条纪律：验收门槛若内联在引擎代码里，就是"抄进代码的第二份真相"，
# 调门槛要改代码、也容易被误读为政策数值。故门槛随 manifest 下发，基准层只读不算。
# 语义（`ghg bench` 逐项判定，任一不达标即退出码 1）：
#   * *_rate 类为下限（达成率 >= 门槛）；runtime_seconds 为上限（运行时长 <= 门槛）。
BENCH_TARGETS = {
    "rules_self_consistency_rate": Decimal("1.0"),   # 规则自洽率（40 包逐条检查全过）
    "factor_unit_consistency_rate": Decimal("1.0"),  # 因子一致性 + 单位往返一致率
    "case_hit_rate": Decimal("0.95"),                # 异常用例命中率下限
    "case_false_positive_rate": Decimal("0"),        # 误报率上限（零容忍）
    "runtime_seconds": Decimal("2"),                 # 单次全量运行时长上限（NFR-11）
}

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

# --------------------------------------------------------------------------
# 官方出处登记（M1 逐条核对；URL 与快照见 data/README.md §二 / data/knowledge/raw/）
# --------------------------------------------------------------------------
STANDARD_FACTS = {
    "gbt32150-2025": {
        "published": "2025-12-31",
        "effective": "2026-07-01",
        "supersedes": "GB/T 32150-2015",
        "validity": "现行",
        "clause": {
            "code": "GB/T 32150-2025",
            "article": "封面 / 前言",
            "note": "封面载「代替 GB/T 32150—2015」；日期与国家标准化管理委员会标准详情页一致",
        },
        "ref": {
            "source": "全国标准信息公共服务平台（openstd.samr.gov.cn）标准详情页",
            "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=6E4997D6B3118055931BC13C71B9A452",
            "version": "2026-10-13 抓取",
        },
    },
    "gbt32150-2015": {
        "published": "2015-11-19",
        "effective": "2016-06-01",
        "supersedes": None,
        "validity": "废止",
        "clause": {
            "code": "GB/T 32150-2015",
            "article": "封面",
            "note": "详情页标准状态：废止；未显示代替关系字段",
        },
        "ref": {
            "source": "全国标准信息公共服务平台（openstd.samr.gov.cn）标准详情页",
            "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=29DE620206A268D0E27B8739E332D70E",
            "version": "2026-10-13 抓取",
        },
    },
}

# 分行业核算与报告指南（CETS—AG 系列；行业适用性 / 公式 / 缺省值的条款依据）
INDUSTRY_GUIDES = {
    "power": {
        "code": "CETS-AG-01.01-V04-2026",
        "title": "《企业温室气体排放核算与报告指南 发电设施》",
        "doc_no": "环办气候函〔2026〕237号",
        "date": "2026-06-29",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202606/t20260629_1160473.html",
        "pdf": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202606/W020260629673485282202.pdf",
    },
    "steel": {
        "code": "CETS-AG-03.01-V01-2024",
        "title": "《企业温室气体排放核算与报告指南 钢铁行业》",
        "doc_no": "环办气候函〔2025〕27号",
        "date": "2025-01-24",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202501/t20250124_1101316.html",
        "pdf": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202501/W020250124388842647934.pdf",
    },
    "cement": {
        "code": "CETS-AG-02.01-V01-2024",
        "title": "《企业温室气体排放核算与报告指南 水泥行业》",
        "doc_no": "环办气候函〔2024〕321号",
        "date": "2024-09-14",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/t20240914_1086067.html",
        "pdf": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/W020240914705756032366.pdf",
    },
    "aluminum": {
        "code": "CETS-AG-04.01-V01-2024",
        "title": "《企业温室气体排放核算与报告指南 铝冶炼行业》",
        "doc_no": "环办气候函〔2024〕321号",
        "date": "2024-09-14",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/t20240914_1086067.html",
        "pdf": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/W020240914705758174865.pdf",
    },
}

COVERAGE_PLAN = {
    "code": "环气候〔2025〕23号",
    "title": "《全国碳排放权交易市场覆盖钢铁、水泥、铝冶炼行业工作方案》",
    "date": "2025-03-21",
    "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202503/t20250326_1104736.html",
}

QUOTA_PLAN_2026 = {
    "code": "国环规气候〔2026〕1号",
    "title": "《全国碳排放权交易市场2025、2026年度发电行业以及2026年度钢铁、水泥、铝冶炼行业配额总量和分配方案》",
    "date": "2026-09-02",
    "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202609/t20260903_1165029.html",
    "pdf": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202609/W020260903551498752549.pdf",
}

FACTOR_DB = {
    "title": "国家温室气体排放因子数据库（第二版）",
    "date": "2026-03-01",
    "url": "https://data.ncsc.org.cn/factories/index",
    "notice_url": "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202603/t20260301_1145117.shtml",
    "access_note": "站点经 WAF 拦截（HTTP 412），M1 未能直连逐条摘录；官方发布通知已核对",
}

# --------------------------------------------------------------------------
# 排放源目录：结构脚手架（id 全局稳定，P1；哪些源适用属政策内容，见 BOUNDARY_MATRIX）
# --------------------------------------------------------------------------
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

# 排放源纳入矩阵（M1 核对结果）：industry -> source_id -> (required, delta_vs_2015, 依据要点)
# 依据：行业指南「5 核算边界和排放源确定 / 5.2 排放源」+ 通则 2025 前言「主要技术变化」。
BOUNDARY_MATRIX = {
    "power": {
        "stationary_combustion": (
            True, "adjusted",
            "发电设施核算边界内的化石燃料燃烧排放（含启动锅炉、燃气轮机等主要生产系统；"
            "生物质掺烧仅计化石燃料部分）；通则 2025 前言 b) 将「燃料燃烧排放」更名为"
            "「化石燃料燃烧排放」",
        ),
        "purchased_electricity": (
            False, "adjusted",
            "2026 版指南全文删除「购入使用电力排放」，购入使用电量改列辅助报告项；"
            "工作方案明确发电行业不覆盖间接排放；通则 2025 增加 7.5.6 外购非化石能源电力"
            "排放因子要求及附录 B",
        ),
        "purchased_heat": (
            False, "adjusted",
            "发电行业核算范围不含净购入热力隐含排放（工作方案：不覆盖间接排放）；"
            "通则 2025 增加 7.5.7 外购非化石能源热力排放因子选取要求",
        ),
        "fugitive_emission": (
            False, "same",
            "发电设施指南核算范围为化石燃料燃烧产生的二氧化碳排放，未设逃逸排放源",
        ),
    },
    "steel": {
        "stationary_combustion": (
            True, "adjusted",
            "企业层级「消耗化石燃料排放」：外购燃料在焦炉、高炉等设备作原料/燃料用途，"
            "不含点火助燃、运输与附属生产系统；通则 2025 前言 b) 术语更名",
        ),
        "process_emission": (
            True, "same",
            "企业层级「过程排放」：碳酸盐分解、电极、外购含碳原料（生铁/直接还原铁/"
            "铁合金/废钢等）消耗；通则 2025 与 2015 均设过程排放",
        ),
        "purchased_electricity": (
            False, "adjusted",
            "钢铁行业核算范围为直接排放，工作方案明确不覆盖因消耗电力等导致的间接排放；"
            "通则 2025 增加 7.5.6 与附录 B",
        ),
        "purchased_heat": (
            False, "adjusted",
            "钢铁行业不覆盖净购入热力隐含排放；通则 2025 增加 7.5.7",
        ),
        "carbon_product": (
            True, "adjusted",
            "企业层级「含碳产品隐含的排放」：粗钢与外销生铁、粗苯、焦油对应的碳排放予以扣减，"
            "冶金渣不扣减；通则 2025 前言 a)/c) 增加温室气体汇、碳清除及不可忽略的其他间接排放",
        ),
    },
    "cement": {
        "stationary_combustion": (
            True, "adjusted",
            "熟料生产「化石燃料燃烧排放」：化石燃料在水泥窑中燃烧，不含替代燃料与窑点火柴油；"
            "通则 2025 前言 b) 术语更名",
        ),
        "process_emission": (
            True, "same",
            "熟料生产「过程排放」：熟料对应碳酸盐分解，不含窑头/旁路放风粉尘与生料非燃料碳；"
            "通则 2025 与 2015 均设过程排放",
        ),
        "purchased_electricity": (
            False, "adjusted",
            "水泥行业核算范围为直接排放，不覆盖电力间接排放；通则 2025 增加 7.5.6 与附录 B",
        ),
        "purchased_heat": (
            False, "adjusted",
            "水泥行业不覆盖净购入热力隐含排放；通则 2025 增加 7.5.7",
        ),
        "carbon_product": (
            False, "adjusted",
            "水泥熟料生产指南未设含碳产品隐含排放源；通则 2025 前言 c) 增加温室气体汇相关内容",
        ),
    },
    "aluminum": {
        "stationary_combustion": (
            True, "adjusted",
            "企业层级「化石燃料燃烧排放」：各种固定或移动燃烧设备；通则 2025 前言 b) 术语更名",
        ),
        "process_emission": (
            True, "same",
            "铝电解工序「能源作为原材料用途的排放」（阳极消耗）+「阳极效应排放」（CF4/C2F6）"
            "+ 企业层级碳酸盐分解排放；通则 2025 与 2015 均设过程排放",
        ),
        "purchased_electricity": (
            False, "adjusted",
            "铝冶炼行业核算范围为直接排放，不覆盖电力间接排放；通则 2025 增加 7.5.6 与附录 B",
        ),
        "purchased_heat": (
            False, "adjusted",
            "铝冶炼行业不覆盖净购入热力隐含排放；通则 2025 增加 7.5.7",
        ),
        "carbon_product": (
            False, "adjusted",
            "铝冶炼指南未设含碳产品隐含排放源；通则 2025 前言 c) 增加温室气体汇相关内容",
        ),
    },
}

# 行业核算与报告指南的文号页（快照见 data/knowledge/raw/）
def _guide_ref(industry_key, article=None):
    guide = INDUSTRY_GUIDES[industry_key]
    return {
        "source": "%s（%s，%s；%s）" % (guide["title"], guide["code"], guide["doc_no"], guide["date"]),
        "url": guide["url"],
        "version": guide["code"],
    }


def _guide_clause(industry_key, article, note):
    guide = INDUSTRY_GUIDES[industry_key]
    return {"code": guide["code"], "article": article, "note": note}


# 公式条款（通则 7.2.2 排放因子法 + 行业指南公式(1)）
FORMULA_FACTS = {
    "power": ("6.1.1 公式(1)", "化石燃料燃烧排放 = Σ(消耗量 × 收到基元素碳含量 × 碳氧化率 × 44/12)"),
    "steel": ("6.1.1 公式(1)", "企业层级采用物料平衡法；工序层级化石燃料排放按输入/输出燃料核算"),
    "cement": ("6.1.1 公式(1)", "熟料生产化石燃料燃烧排放 = Σ(消耗量 × 收到基低位发热量 × 单位热值含碳量 × 碳氧化率 × 44/12)"),
    "aluminum": ("7.1.1 公式(5)", "化石燃料燃烧排放；另有 6.1.1 公式(1) 能源作原材料用途排放"),
}

# 碳氧化率缺省值（附录 A / 正文缺省值）：industry -> (value, unit, status, article, note)
# 发电行业按年度取值：2026 年度起改用因子库（更新通知），2025 及以前适用原 6.2.5.1「燃煤 99%」。
OXIDATION_FACTS = {
    "steel": (
        Decimal("99"), "%", "verified", "6.2.3 / 附录 A 附表 A.1",
        "固体燃料碳氧化率缺省值 99%（液体 98%、气体 99%，按燃料品种取值）",
    ),
    "cement": (
        Decimal("99"), "%", "verified", "6.1.2.4 / 附录 A 附表 A.1",
        "水泥窑碳氧化率缺省值 99%（发电锅炉 95%、工业锅炉 85%）",
    ),
    "aluminum": (
        Decimal("98"), "%", "verified", "7.1.2.5 / 附录 A 附表 A.1",
        "固体燃料碳氧化率缺省值 98%（气体 99%）",
    ),
}

# 发电行业碳氧化率：2026 年度起改用国家温室气体排放因子数据库（更新通知）→ pending；
# 2025 及以前适用原 6.2.5.1「燃煤的碳氧化率取 99%」（更新通知附件 1 引述原条款原文）。
POWER_OXIDATION_LEGACY_PCT = Decimal("99")
POWER_OXIDATION_PENDING_ARTICLE = "6.2.5"
POWER_OXIDATION_LEGACY_ARTICLE = "6.2.5.1（2026 更新通知附件 1 引述原条款）"
POWER_OXIDATION_FACTOR_DB_FROM_YEAR = 2026

# 行业缺省排放因子：由单位热值含碳量与低位发热量**官方缺省值**按标准公式合成
#   燃料排放因子(tCO2/t) = 收到基低位发热量(GJ/t) × 单位热值含碳量(tC/GJ) × 44/12
# 两个输入均直接取自行业指南附录 A / 正文缺省值（逐条挂条款号），合成只做该公式本身的乘法，
# 属可复现推导而非新政策数值。所选代表性燃料即指南规定的兜底品种。
# 结构：industry -> {fuel, ncv(Decimal), ncv_article, cc(Decimal), cc_article, note}
DEFAULT_FACTOR_INPUTS = {
    "power": {
        "fuel": "燃煤",
        "ncv": Decimal("26.7"),
        "ncv_article": "6.2.3.3",
        "ncv_note": "某日/批次燃煤收到基低位发热量无实测或方法不符时取 26.7 GJ/t",
        "cc": Decimal("0.03085"),
        "cc_article": "6.2.4.1",
        "cc_note": "未开展燃煤元素碳实测或实测不符合要求时，单位热值含碳量取 0.03085 tC/GJ（不含非常规燃煤机组）",
    },
    "steel": {
        "fuel": "烟煤",
        "ncv": Decimal("23.736"),
        "ncv_article": "附录 A 附表 A.1",
        "ncv_note": "烟煤收到基低位发热量缺省值 23.736 GJ/t",
        "cc": Decimal("0.02618"),
        "cc_article": "附录 A 附表 A.1",
        "cc_note": "烟煤单位热值含碳量缺省值 0.02618 tC/GJ",
    },
    "cement": {
        "fuel": "烟煤（低位发热量兜底）+ 褐煤（含碳量兜底）",
        "ncv": Decimal("23.076"),
        "ncv_article": "6.1.2.2 / 附录 A 附表 A.1",
        "ncv_note": "无法区分煤种或附录 A 未列煤种时，采用附录 A 中烟煤的收到基低位发热量缺省值 23.076 GJ/t",
        "cc": Decimal("0.02797"),
        "cc_article": "6.1.2.3 / 附录 A 附表 A.1",
        "cc_note": "无法区分煤种或附录 A 未列煤种时，采用附录 A 中褐煤的单位热值含碳量缺省值 0.02797 tC/GJ",
    },
    "aluminum": {
        "fuel": "烟煤",
        "ncv": Decimal("23.337"),
        "ncv_article": "附录 A 附表 A.1",
        "ncv_note": "烟煤收到基低位发热量缺省值 23.337 GJ/t",
        "cc": Decimal("0.02618"),
        "cc_article": "附录 A 附表 A.1",
        "cc_note": "烟煤单位热值含碳量缺省值 0.02618 tC/GJ",
    },
}

# 二氧化碳与碳的相对分子质量之比（标准公式中的无量纲常数，非政策数值）
CO2_TO_C = Decimal(44) / Decimal(12)

# 合成得到的缺省因子落库小数位（44/12 为循环小数，量化后落库以保证字节稳定可读）
FACTOR_PLACES = 9

# 质量校核规则（条款依据：通则第 8 章质量保证 + 行业指南数据质量管理章节）
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

# 数据质量校核阈值（M3 工程定值，**非政策数值**：属本工具的工程筛查判据，非官方发布值）。
# 语义见 code/src/ghg/quality.py 模块 docstring：
#   magnitude      —— 单源排放量占全厂合计的占比上限（粗筛；单源档案跳过）
#   yoy            —— 同一源活动数据跨年度变化率上限（需上一年度基线）
#   intensity_min/max —— 比强度（排放量/产量）合理区间
QUALITY_THRESHOLDS = {
    "magnitude": {"value": Decimal("0.95"), "unit": "ratio",
                  "note": "单源排放量占全厂合计占比上限（超过即提示复核量级）"},
    "yoy": {"value": Decimal("0.50"), "unit": "ratio",
            "note": "同一排放源活动数据跨年度变化率上限"},
    "intensity_min": {"value": Decimal("0.5"), "unit": "tCO2e_per_unit_output",
                      "note": "比强度合理区间下限（排放量/产量）"},
    "intensity_max": {"value": Decimal("5.0"), "unit": "tCO2e_per_unit_output",
                      "note": "比强度合理区间上限（排放量/产量）"},
}

# 配额方法学与参数（发电行业基准值官方公布；三行业「平衡值」仅平台可查）
POWER_BENCHMARK_2025 = Decimal("0.7902")
POWER_BENCHMARK_2026 = Decimal("0.7894")

# 碳排放强度系数法推导参数（方案表 3：|X| 小于带内取 斜率×X，越界取 ±封顶）
# 来源：国环规气候〔2026〕1号 表 3「2026 年度碳排放强度系数」+ 三（二）2 公式。
QUOTA_DERIVATION = {
    "slope": Decimal("0.15"),
    "band": Decimal("0.20"),
    "cap": Decimal("0.03"),
}


def _entry(value, unit=None, status="verified", clause=None, ref=None):
    entry = {"value": value, "status": status}
    if unit is not None:
        entry["unit"] = unit
    if clause is not None:
        entry["clause"] = clause
    if ref is not None:
        entry["ref"] = ref
    return entry


def _pending(value=None, unit=None, clause=None, ref=None, note=None):
    """构造一个未核对条目（value 为 null、status=pending）。"""
    if clause is None:
        clause = {"code": None, "article": "待核对", "note": note or "待官方原文核对"}
    return _entry(value, unit=unit, status="pending", clause=clause, ref=ref)


def _input_required(unit=None, clause=None, ref=None, note=None):
    """构造一个**外部输入槽**条目（value 为 null、status=input_required）。

    语义：该数值不由规则包承载（如三行业配额"平衡值"当年度由全国碳市场管理平台测算公布，
    方案正文未印数值），故不阻断门控；缺失由试算层在运行时显式索取（不得静默取 0）。
    见 plan/06 D3-2。
    """
    if clause is None:
        clause = {"code": None, "article": "外部输入（非规则包承载）",
                  "note": note or "该数值需由调用方提供"}
    return _entry(None, unit=unit, status="input_required", clause=clause, ref=ref)


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


def _standard_block(standard_key):
    facts = STANDARD_FACTS[standard_key]
    return {
        "code": next(s["code"] for s in STANDARDS if s["key"] == standard_key),
        "label": next(s["label"] for s in STANDARDS if s["key"] == standard_key),
        "published": facts["published"],
        "effective": facts["effective"],
        "supersedes": facts["supersedes"],
        "validity": facts["validity"],
        "status": "verified",
        "clause": dict(facts["clause"]),
        "ref": dict(facts["ref"]),
    }


def _sources_for(industry):
    out = []
    matrix = BOUNDARY_MATRIX[industry]
    for src in SOURCE_CATALOG:
        if industry not in src["applicability"]:
            continue
        required, delta, note = matrix[src["id"]]
        out.append({
            "id": src["id"],
            "name": src["name"],
            "category": src["category"],
            "applicable_industries": list(src["applicability"]),
            "required": required,
            "delta_vs_2015": delta,
            "clause": _guide_clause(industry, "5.2", note),
            "ref": _guide_ref(industry),
            "status": "verified",
        })
    return out


def _formula_block(industry):
    article, note = FORMULA_FACTS[industry]
    return {
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
        "clause": {
            "code": "GB/T 32150-2025",
            "article": "7.2.2 排放因子法（公式 1）",
            "note": "温室气体排放量 = 活动数据 × 排放因子 × 全球变暖潜势；行业指南 " + article
                    + "：" + note,
        },
        "ref": _guide_ref(industry),
        "status": "verified",
    }


def _coefficients_block(industry, year):
    if industry == "power":
        return {"oxidation_rate": _power_oxidation_entry(year)}
    value, unit, status, article, note = OXIDATION_FACTS[industry]
    if status == "verified":
        entry = _entry(value, unit=unit, status="verified",
                       clause=_guide_clause(industry, article, note),
                       ref=_guide_ref(industry))
    else:
        entry = _entry(None, unit=unit, status="pending",
                       clause=_guide_clause(industry, article, note),
                       ref=_guide_ref(industry))
    return {"oxidation_rate": entry}


def _power_oxidation_entry(year):
    """发电行业碳氧化率：2026 年度起改用因子库（pending）；此前适用原 6.2.5.1「燃煤 99%」。"""
    guide = INDUSTRY_GUIDES["power"]
    if year >= POWER_OXIDATION_FACTOR_DB_FROM_YEAR:
        clause = _guide_clause(
            "power", POWER_OXIDATION_PENDING_ARTICLE,
            "2026-06-29 更新后燃煤/燃油/燃气碳氧化率改用国家温室气体排放因子数据库"
            "（全国碳市场发电行业重点排放单位相应碳氧化率排放因子）；因子库站点经 WAF "
            "拦截（HTTP 412）未直连摘录 → 保持 pending",
        )
        return _entry(None, unit="%", status="pending",
                      clause=clause, ref=_guide_ref("power"))
    clause = _guide_clause(
        "power", POWER_OXIDATION_LEGACY_ARTICLE,
        "更新前条款：燃煤的碳氧化率取 99%；燃油和燃气采用附录 A 各燃料品种缺省值"
        "（更新通知附件 1 引述原条款原文）",
    )
    return _entry(POWER_OXIDATION_LEGACY_PCT, unit="%", status="verified",
                  clause=clause, ref=_guide_ref("power"))


def _factors_block(industry):
    spec = DEFAULT_FACTOR_INPUTS[industry]
    factor_value = (spec["ncv"] * spec["cc"] * CO2_TO_C).quantize(
        Decimal(1).scaleb(-FACTOR_PLACES))
    note = ("行业缺省排放因子（按代表性兜底燃料合成）：%s 低位发热量 %s GJ/t（%s：%s）"
            "× 单位热值含碳量 %s tC/GJ（%s：%s）× 44/12"
            % (spec["fuel"], spec["ncv"], spec["ncv_article"], spec["ncv_note"],
               spec["cc"], spec["cc_article"], spec["cc_note"]))
    return {
        "priority": ["measured", "official_db", "industry_default"],
        "priority_clause": {
            "code": "GB/T 32150-2025",
            "article": "7.4 选择或测定温室气体排放因子（表 4 获取优先级）",
            "note": "企业实测 > 官方因子库 > 行业缺省值；缺省值来源不明不得作为默认因子",
        },
        "industry_default_values": {
            "default_factor": _entry(
                factor_value, unit="tCO2e_per_t", status="verified",
                clause=_guide_clause(industry, spec["cc_article"], note),
                ref=_guide_ref(industry),
            ),
        },
    }


def _quality_block(industry):
    rules = []
    for rule in QUALITY_RULES:
        rules.append({
            "id": rule["id"],
            "type": rule["type"],
            "level": rule["level"],
            "name": rule["name"],
            "advice": rule["advice"],
            "clause": {
                "code": "GB/T 32150-2025",
                "article": "8 核算工作的质量保证",
                "note": "行业指南数据质量管理要求（%s）" % INDUSTRY_GUIDES[industry]["code"],
            },
            "ref": _guide_ref(industry),
            "status": "verified",
        })
    thresholds = {}
    for key in sorted(QUALITY_THRESHOLDS):
        spec = QUALITY_THRESHOLDS[key]
        thresholds[key] = _entry(
            spec["value"], unit=spec["unit"], status="verified",
            clause={
                "code": None,
                "article": "工程筛查阈值（非政策数值）",
                "note": spec["note"] + "；M3 校核层定值，来源：本工具工程判据，非官方发布数值",
            },
        )
    return {"rules": rules, "thresholds": thresholds}


def _quota_block(industry, year):
    plan = QUOTA_PLAN_2026
    plan_clause_base = {
        "code": plan["code"],
        "article": None,
        "note": plan["title"],
    }
    if industry == "power":
        method = "benchmark"
        method_clause = dict(plan_clause_base)
        method_clause["article"] = "三（一）发电行业：碳排放强度基准法"
        if year == 2025:
            benchmark, bm_note = POWER_BENCHMARK_2025, "2025 年度 I 类机组发电基准值（表 1）"
            bm_entry = _entry(
                benchmark, unit="tCO2e_per_MWh", status="verified",
                clause=dict(method_clause, article="表 1 各类别机组碳排放基准值", note=bm_note),
                ref={"source": "%s（%s）" % (plan["title"], plan["code"]),
                     "url": plan["url"], "version": plan["code"]},
            )
        elif year == 2026:
            benchmark, bm_note = POWER_BENCHMARK_2026, "2026 年度 I 类机组发电基准值（表 1）"
            bm_entry = _entry(
                benchmark, unit="tCO2e_per_MWh", status="verified",
                clause=dict(method_clause, article="表 1 各类别机组碳排放基准值", note=bm_note),
                ref={"source": "%s（%s）" % (plan["title"], plan["code"]),
                     "url": plan["url"], "version": plan["code"]},
            )
        else:
            # 其他年度配额方案未入库：不是"未核对的政策数值"，而是"本坐标不承载该输入"。
            bm_entry = _input_required(
                unit="tCO2e_per_MWh",
                clause=dict(method_clause, article="表 1 各类别机组碳排放基准值",
                            note="%d 年度配额方案未入库（现有方案仅覆盖 2025/2026 年度）" % year),
            )
        params = {
            "benchmark_value": bm_entry,
            # 调峰修正系数是机组负荷率 F 的函数（F<50 按公式，F≥50 取 1），随机组而异 →
            # 属外部输入；不得静默取 1。
            "correction_factor": _input_required(
                unit="1",
                clause=dict(method_clause, article="表 2 常规燃煤机组调峰修正系数",
                            note="调峰修正系数为机组负荷率 F 的函数（F<50 按公式，F≥50 取 1）；"
                                 "随机组而异，需由调用方按机组负荷率提供"),
            ),
        }
        status = "verified"
    else:
        method = "intensity_coefficient"
        method_clause = dict(plan_clause_base)
        method_clause["article"] = "三（二）钢铁、水泥、铝冶炼行业：碳排放强度系数法"
        # 强度系数 α 不是规则包常量：它由企业实际强度 Ii 与行业平衡值 BP 的偏离度 X 分段推出
        # （方案表 3）。故 params 只承载"平台可查"的 BP（外部输入），分段常数放 derivation。
        params = {
            "benchmark_value": _input_required(
                unit="tCO2e_per_unit_output",
                clause=dict(method_clause, article="三（二）：行业平衡值",
                            note="行业平衡值（BP）当年度由全国碳市场管理平台测算并公布，"
                                 "方案正文未印具体数值 → 外部输入（平台可查），试算层不得静默取 0"),
            ),
        }
        status = "verified"
    return {
        "allowed_methods": ["benchmark", "intensity_coefficient", "historical_intensity", "none"],
        "method": method,
        "method_clause": method_clause,
        "clause": method_clause,
        "params": params,
        "derivation": {key: _entry(value, unit="1", status="verified",
                                   clause={"code": plan["code"],
                                           "article": "表 3 2026 年度碳排放强度系数",
                                           "note": "强度系数分段推导常数（斜率/带宽/封顶）"})
                       for key, value in sorted(QUOTA_DERIVATION.items())},
        "ref": {"source": "%s（%s）" % (plan["title"], plan["code"]),
                "url": plan["url"], "version": plan["code"]},
        "status": status,
    }


def ruleset_payload(standard_key, year, industry_key):
    std = next(s for s in STANDARDS if s["key"] == standard_key)
    ind = next(i for i in INDUSTRIES if i["key"] == industry_key)
    coord = {"standard": standard_key, "year": year, "industry": industry_key}

    return {
        "schema": "ghg-ruleset/v1",
        "coordinate": coord,
        "standard": _standard_block(standard_key),
        "boundary": {
            "sources": _sources_for(industry_key),
        },
        "engine": {
            "formula": _formula_block(industry_key),
            "coefficients": _coefficients_block(industry_key, year),
        },
        "factors": _factors_block(industry_key),
        "quality": _quality_block(industry_key),
        "quota": _quota_block(industry_key, year),
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
        # M4 内置基准的验收门槛（数据驱动，见 plan/06 D4-1）
        "bench": {
            "targets": BENCH_TARGETS,
        },
        "coordinates": coord_entries,
    }
    jsonio.write(os.path.join(rules_dir, "manifest.json"), manifest)

    if verbose:
        print("已生成：%s" % rules_dir)
        print("  规则包 %d 份（M1：排放源/公式/行业缺省因子已挂官方原文核对）" % len(coord_entries))
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
