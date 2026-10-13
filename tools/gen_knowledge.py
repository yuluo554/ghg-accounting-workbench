#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""条款库生成器（data/knowledge/ 的唯一写入者）。

产出（冻结产物，禁手改；改体例走本脚本重生成）：
  * ``data/knowledge/clauses.json``  结构化条款库：官方依据索引 + 快照 sha256 + 条款要点

与 ``data/knowledge/raw/`` 的关系：
  raw/ 存放**官方原文快照**（HTML / PDF / pdftotext 文本，逐份登记 sha256）；
  本文件是这些快照的**结构化索引**（哪条政策、文号、日期、URL、以及被规则包引用的条款要点）。

纪律：无时间戳、键排序固定、``write_bytes``（LF）；sha256 由快照实时计算（防"改了快照忘改台账"）。
"""

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg import jsonio  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
KNOWLEDGE_DIR = os.path.join(DATA_DIR, "knowledge")
RAW_DIR = os.path.join(KNOWLEDGE_DIR, "raw")

GENERATOR_VERSION = "gen_knowledge/0.1.0"
GENERATED_ON = "2026-10-13"

# 依据索引（M1 直连核对；snapshot 为 data/knowledge/raw/ 下相对路径）
SOURCES = [
    {
        "id": "gbt32150-2025",
        "title": "GB/T 32150-2025《工业企业温室气体排放核算和报告通则》",
        "kind": "国家标准",
        "publisher": "国家市场监督管理总局、国家标准化管理委员会",
        "doc_no": "GB/T 32150-2025",
        "published": "2025-12-31",
        "effective": "2026-07-01",
        "status_text": "现行；全部代替 GB/T 32150-2015",
        "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=6E4997D6B3118055931BC13C71B9A452",
        "snapshots": [
            "openstd-gbt32150-2025-detail.html",
            "openstd-gbt32150-2025-review.html",
        ],
        "clauses": [
            {"article": "封面", "point": "代替 GB/T 32150—2015；2025-12-31 发布、2026-07-01 实施"},
            {"article": "前言 主要技术变化 a)", "point": "增加碳汇、碳清除等相关术语（见第 3 章）"},
            {"article": "前言 主要技术变化 b)", "point": "「燃料燃烧排放」更名为「化石燃料燃烧排放」并改定义（见 3.7）"},
            {"article": "前言 主要技术变化 c)", "point": "增加报告主体涉及温室气体汇与不可忽略的其他间接排放内容（见第 6 章）"},
            {"article": "前言 主要技术变化 d)", "point": "增加外购非化石能源电力排放因子确定要求（见 7.5.6）"},
            {"article": "前言 主要技术变化 e)", "point": "增加外购非化石能源热力排放因子选取要求（见 7.5.7）"},
            {"article": "前言 主要技术变化 f)", "point": "增加「不可忽略的其他间接排放」及四种主要类别（见附录 A）"},
            {"article": "前言 主要技术变化 g)", "point": "增加非化石能源电力排放因子取值要求及证明文件（见附录 B）"},
            {"article": "6 温室气体排放核算边界", "point": "以企业法人或视同法人的独立核算单位为边界；含主要/辅助/附属生产系统"},
            {"article": "7.2.2 排放因子法（公式 1）", "point": "温室气体排放量 = 活动数据 × 排放因子 × 全球变暖潜势"},
            {"article": "7.4 选择或测定温室气体排放因子（表 4）", "point": "因子获取优先级：来源明确有公信力、适用性"},
        ],
        "access_note": "全文经 openstd 在线预览（防复制精灵图）逐页核对；未获取可下载 PDF 与编制说明。",
    },
    {
        "id": "gbt32150-2015",
        "title": "GB/T 32150-2015《工业企业温室气体排放核算和报告通则》",
        "kind": "国家标准",
        "publisher": "国家质量监督检验检疫总局、国家标准化管理委员会",
        "doc_no": "GB/T 32150-2015",
        "published": "2015-11-19",
        "effective": "2016-06-01",
        "status_text": "废止（不提供标准文本阅读服务）",
        "url": "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=29DE620206A268D0E27B8739E332D70E",
        "snapshots": ["openstd-gbt32150-2015-detail.html"],
        "clauses": [
            {"article": "3.7 燃料燃烧排放", "point": "旧版术语（2025 版更名为「化石燃料燃烧排放」）"},
        ],
    },
    {
        "id": "cets-ag-01-power",
        "title": "《企业温室气体排放核算与报告指南 发电设施》",
        "kind": "全国碳排放权交易市场技术规范",
        "publisher": "生态环境部办公厅",
        "doc_no": "环办气候函〔2026〕237号",
        "spec_no": "CETS-AG-01.01-V04-2026",
        "published": "2026-06-29",
        "status_text": "现行（适用自 2026 年度起）",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202606/t20260629_1160473.html",
        "snapshots": [
            "mee-2026-06-29-power-guideline-update.html",
            "mee-2026-06-29-power-ag-full.pdf",
            "power-update-1.txt",
        ],
        "clauses": [
            {"article": "5.2 排放源", "point": "核算范围为化石燃料燃烧产生的二氧化碳排放（含掺烧生物质时的化石燃料部分）"},
            {"article": "6.1.1 公式(1)", "point": "E燃烧 = Σ(FCi × Car,i × OFi × 44/12)"},
            {"article": "6.2.3.3", "point": "无实测时燃煤收到基低位发热量取 26.7 GJ/t"},
            {"article": "6.2.4.1", "point": "未实测时单位热值含碳量取 0.03085 tC/GJ（非常规燃煤机组 0.02858）"},
            {"article": "6.2.5（2026 更新）", "point": "燃煤/燃油/燃气碳氧化率改用国家温室气体排放因子数据库取值"},
            {"article": "6.2.5.1（更新前原文，更新通知附件 1 引述）", "point": "燃煤的碳氧化率取 99%"},
            {"article": "附录 A", "point": "常用化石燃料低位发热量 / 单位热值含碳量 / 碳氧化率缺省值"},
            {"article": "2026 更新通知（环办气候函〔2026〕237号）", "point": "全文删除「购入使用电力排放」，购入使用电量改列辅助报告项"},
        ],
    },
    {
        "id": "cets-ag-02-cement",
        "title": "《企业温室气体排放核算与报告指南 水泥行业》",
        "kind": "全国碳排放权交易市场技术规范",
        "publisher": "生态环境部办公厅",
        "doc_no": "环办气候函〔2024〕321号",
        "spec_no": "CETS-AG-02.01-V01-2024",
        "published": "2024-09-14",
        "status_text": "现行",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/t20240914_1086067.html",
        "snapshots": ["cement-ag.pdf", "cement-ag.txt"],
        "clauses": [
            {"article": "5.1.1 熟料生产", "point": "边界为熟料烧成系统（预热器、分解炉、水泥窑）"},
            {"article": "5.2.1 熟料生产排放源", "point": "化石燃料燃烧排放 + 过程排放（碳酸盐分解）"},
            {"article": "6.1.1 公式(1)", "point": "E燃烧 = Σ(消耗量 × 收到基低位发热量 × 单位热值含碳量 × 碳氧化率 × 44/12)"},
            {"article": "6.1.2.2", "point": "无法区分煤种或未列煤种时，低位发热量取烟煤缺省值 23.076 GJ/t"},
            {"article": "6.1.2.3", "point": "无法区分煤种或未列煤种时，单位热值含碳量取褐煤缺省值 0.02797 tC/GJ"},
            {"article": "6.1.2.4 / 附录 A", "point": "碳氧化率按燃烧设备取值：水泥窑 99%、发电锅炉 95%、工业锅炉 85%"},
        ],
    },
    {
        "id": "cets-ag-03-steel",
        "title": "《企业温室气体排放核算与报告指南 钢铁行业》",
        "kind": "全国碳排放权交易市场技术规范",
        "publisher": "生态环境部办公厅",
        "doc_no": "环办气候函〔2025〕27号",
        "spec_no": "CETS-AG-03.01-V01-2024",
        "published": "2025-01-24",
        "status_text": "现行",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202501/t20250124_1101316.html",
        "snapshots": ["steel-ag.pdf", "steel-ag.txt"],
        "clauses": [
            {"article": "5.2.1 企业层级排放源", "point": "消耗化石燃料排放 + 过程排放 + 含碳产品隐含排放"},
            {"article": "5.2.2 工序层级排放源", "point": "焦化/烧结/球团/炼铁/转炉/电炉六工序净消耗 + 掺烧自产二次能源发电设施 + 其他"},
            {"article": "6.1.1", "point": "企业层级采用物料平衡法（公式 1）"},
            {"article": "6.2.3 / 附录 A 附表 A.1", "point": "单位热值含碳量取附录 A 缺省值（烟煤 0.02618 tC/GJ）"},
            {"article": "附录 A 附表 A.1", "point": "固体燃料碳氧化率 99%、液体 98%、气体 99%"},
        ],
    },
    {
        "id": "cets-ag-04-aluminum",
        "title": "《企业温室气体排放核算与报告指南 铝冶炼行业》",
        "kind": "全国碳排放权交易市场技术规范",
        "publisher": "生态环境部办公厅",
        "doc_no": "环办气候函〔2024〕321号",
        "spec_no": "CETS-AG-04.01-V01-2024",
        "published": "2024-09-14",
        "status_text": "现行",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202409/t20240914_1086067.html",
        "snapshots": ["aluminum-ag.pdf", "aluminum-ag.txt"],
        "clauses": [
            {"article": "5.1.1 铝电解工序层级", "point": "工序边界为电解槽和整流器的集合"},
            {"article": "5.2.1 铝电解工序排放源", "point": "能源作为原材料用途的排放（阳极消耗）+ 阳极效应排放（CF4/C2F6）"},
            {"article": "6.1.1 公式(1)", "point": "E原材料,j = 阳极净耗量 × (1 − 含硫量 − 灰分含量) × 44/12"},
            {"article": "6.1.2.2", "point": "阳极损失率缺省值 15.18%"},
            {"article": "6.1.2.3", "point": "阳极平均含硫量缺省值 2%"},
            {"article": "6.1.2.4", "point": "阳极平均灰分含量缺省值 0.4%"},
            {"article": "7.1.2.4/7.1.2.5 / 附录 A 附表 A.1", "point": "单位热值含碳量与碳氧化率取附录 A 缺省值（固体燃料碳氧化率 98%）"},
        ],
    },
    {
        "id": "coverage-plan",
        "title": "《全国碳排放权交易市场覆盖钢铁、水泥、铝冶炼行业工作方案》",
        "kind": "政策文件",
        "publisher": "生态环境部",
        "doc_no": "环气候〔2025〕23号",
        "published": "2025-03-21",
        "status_text": "现行（启动实施阶段 2024—2026 年度）",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202503/t20250326_1104736.html",
        "snapshots": ["coverage-plan.pdf", "coverage-plan.txt"],
        "clauses": [
            {"article": "一、总体要求", "point": "启动实施阶段 2024—2026 年度；2024 年度为首个管控年度"},
            {"article": "二（一）确定管控范围", "point": "钢铁/水泥管控 CO2；铝冶炼管控 CO2、CF4、C2F6；仅直接排放，不含间接排放"},
            {"article": "二（二）确定重点排放单位", "point": "年度排放量达 2.6 万吨 CO2 当量者纳入重点排放单位"},
        ],
    },
    {
        "id": "quota-plan-2026",
        "title": "《全国碳排放权交易市场2025、2026年度发电行业以及2026年度钢铁、水泥、铝冶炼行业配额总量和分配方案》",
        "kind": "政策文件",
        "publisher": "生态环境部",
        "doc_no": "国环规气候〔2026〕1号",
        "published": "2026-09-02",
        "status_text": "现行",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202609/t20260903_1165029.html",
        "snapshots": ["mee-2026-09-02-quota-plan.html", "mee-2026-09-02-quota-plan.pdf", "quota-plan.txt"],
        "clauses": [
            {"article": "三、配额计算方法", "point": "发电采用碳排放强度基准法；钢铁/水泥/铝冶炼 2026 年度采用碳排放强度系数法"},
            {"article": "三（一）表 1", "point": "2025—2026 年度各类别机组碳排放基准值（I 类：2025 年 0.7902、2026 年 0.7894 tCO2/MWh）"},
            {"article": "三（一）表 2", "point": "常规燃煤机组调峰修正系数为负荷率 F 的函数"},
            {"article": "三（二）表 3", "point": "2026 年度碳排放强度系数 α：-20%<X<20% 取 0.15X；X≥20% 取 0.03；X≤-20% 取 -0.03"},
            {"article": "三（二）", "point": "行业平衡值 BP 由全国碳市场管理平台测算（正文未印具体数值）"},
        ],
    },
    {
        "id": "quota-plan-2025",
        "title": "《2024、2025年度全国碳排放权交易市场钢铁、水泥、铝冶炼行业配额总量和分配方案》",
        "kind": "政策文件",
        "publisher": "生态环境部",
        "doc_no": "国环规气候〔2025〕2号",
        "published": "2025-11-17",
        "status_text": "现行",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202511/t20251118_1134175.html",
        "snapshots": ["quota2425.pdf", "quota2425.txt"],
        "clauses": [
            {"article": "配额计算方法", "point": "定额公式 A = E × (1 + α)；2024 年度按经核查实际排放量等量分配"},
        ],
    },
    {
        "id": "mee-factor-db-v2",
        "title": "国家温室气体排放因子数据库（第二版）正式发布",
        "kind": "政策发布",
        "publisher": "生态环境部",
        "doc_no": None,
        "published": "2026-03-01",
        "status_text": "已发布（官方入口 data.ncsc.org.cn；实测 WAF 拦截 HTTP 412）",
        "url": "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202603/t20260301_1145117.shtml",
        "snapshots": ["mee-2026-03-01-factors-db-v2.html"],
        "clauses": [
            {"article": "发布通知", "point": "第二版新增和更新共 291 个因子，因子总数增至 576 个；同步上线英文版"},
        ],
        "access_note": "因子库站点直连返回 HTTP 412（WAF），M1 未逐条摘录；见 data/factors/manifest.json",
    },
    {
        "id": "power-oxidation-draft",
        "title": "关于公开征求更新《企业温室气体排放核算与报告指南 发电设施》…燃煤碳氧化率因子等技术要求意见的通知",
        "kind": "政策文件（征求意见稿）",
        "publisher": "生态环境部办公厅",
        "doc_no": "环办便函〔2026〕172号",
        "published": "2026-05-21",
        "status_text": "征求意见（2026-05-31 截止）",
        "url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202605/t20260521_1154888.html",
        "snapshots": ["mee-2026-05-21-oxidation-draft.html"],
        "clauses": [
            {"article": "通知", "point": "组织更新发电设施指南燃煤碳氧化率因子等技术要求并公开征求意见"},
        ],
    },
]


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _snapshot_entry(name):
    path = os.path.join(RAW_DIR, name)
    if not os.path.isfile(path):
        return {"file": name, "present": False}
    return {
        "file": name,
        "present": True,
        "bytes": os.path.getsize(path),
        "sha256": _sha256_file(path),
    }


def payload():
    sources = []
    for src in SOURCES:
        item = dict(src)
        item["snapshot_files"] = [_snapshot_entry(n) for n in src["snapshots"]]
        del item["snapshots"]
        sources.append(item)
    return {
        "schema": "ghg-clause-index/v1",
        "generator": GENERATOR_VERSION,
        "generated_on": GENERATED_ON,
        "raw_dir": "data/knowledge/raw",
        "note": ("本索引登记官方依据（文号/日期/URL/条款要点）与原文快照 sha256；"
                 "搜索摘要一律不采信，数值以官方原文直连核对为准。"
                 "快照为官方公文/标准页面（著作权法第五条官方文件不适用版权保护）。"),
        "sources": sources,
    }


def generate(data_dir=None, verbose=True):
    knowledge_dir = os.path.join(data_dir or DATA_DIR, "knowledge")
    if not os.path.isdir(knowledge_dir):
        os.makedirs(knowledge_dir)
    path = os.path.join(knowledge_dir, "clauses.json")
    jsonio.write(path, payload())
    if verbose:
        data = payload()
        n_snap = sum(len(s["snapshot_files"]) for s in data["sources"])
        missing = [e["file"] for s in data["sources"] for e in s["snapshot_files"]
                   if not e["present"]]
        print("已生成：%s" % path)
        print("  依据 %d 条；快照 %d 份%s" % (
            len(data["sources"]), n_snap,
            "（缺 %d 份）" % len(missing) if missing else ""))
    return payload()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = DATA_DIR
    if argv:
        if len(argv) == 2 and argv[0] == "--data-dir":
            data_dir = argv[1]
        else:
            print("用法：python tools/gen_knowledge.py [--data-dir <目录>]")
            return 2
    generate(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
