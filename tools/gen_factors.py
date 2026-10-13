#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""官方排放因子库摘录入库生成器（data/factors/ 的唯一写入者）。

数据来源（M1 核对）：
  * 生态环境部《国家温室气体排放因子数据库（第二版）》（2026-03-01 发布）
    —— 官方入口 https://data.ncsc.org.cn/factories/index。
    **实测约束**：该站点经 WAF 防护（直连返回 HTTP 412），M1 未能逐条摘录其因子数值。
    本文件因此**不编造任何因子数值**，只登记"来源 + 版本 + 访问状态"，
    缺省因子数值改由各行业核算指南附录 A 的官方缺省值承担（见 data/rules/）。
  * 四行业核算与报告指南附录 A 附表 A.1「常用化石燃料相关参数缺省值」
    —— 官方 PDF 直连下载并 pdftotext 核对（快照见 data/knowledge/raw/）。

产出（冻结产物，禁手改；改体例走本脚本重生成）：
  * ``data/factors/manifest.json``  因子库台账（来源 / 版本 / sha256 / 访问状态）

纪律（NFR-04）：无时间戳、键排序固定、``write_bytes``（LF）。
"""

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code", "src"))

from ghg import jsonio  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
FACTORS_DIR = os.path.join(DATA_DIR, "factors")

GENERATOR_VERSION = "gen_factors/0.1.0"
GENERATED_ON = "2026-10-13"

FACTOR_DB_V2 = {
    "title": "国家温室气体排放因子数据库（第二版）",
    "publisher": "生态环境部",
    "released": "2026-03-01",
    "entry_url": "https://data.ncsc.org.cn/factories/index",
    "notice_url": "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/202603/t20260301_1145117.shtml",
    "notice_snapshot": "data/knowledge/raw/mee-2026-03-01-factors-db-v2.html",
    "access_status": "blocked_waf_http_412",
    "access_note": (
        "官方入口 data.ncsc.org.cn 直连返回 HTTP 412（WAF 拦截），M1 未能逐条摘录因子数值；"
        "按数据纪律不编造数值，缺省因子改由各行业核算指南附录 A 官方缺省值承担"
        "（见 data/rules/ruleset-*.json 的 factors.industry_default_values）。"
        "发布通知页（mee.gov.cn）已核对：第二版新增和更新共 291 个因子，因子总数 576 个。"
    ),
}

# 无已摘录的因子条目（WAF 阻断）；此处显式留空并以状态说明，避免"沉默的空库"
FACTOR_ENTRIES = []


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _snapshot_sha256(rel_path):
    path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    return _sha256_file(path)


def manifest_payload():
    return {
        "schema": "ghg-factor-ledger/v1",
        "generator": GENERATOR_VERSION,
        "generated_on": GENERATED_ON,
        "sources": [
            {
                "id": "mee-factor-db-v2",
                "title": FACTOR_DB_V2["title"],
                "publisher": FACTOR_DB_V2["publisher"],
                "released": FACTOR_DB_V2["released"],
                "entry_url": FACTOR_DB_V2["entry_url"],
                "notice_url": FACTOR_DB_V2["notice_url"],
                "notice_snapshot": FACTOR_DB_V2["notice_snapshot"],
                "notice_snapshot_sha256": _snapshot_sha256(FACTOR_DB_V2["notice_snapshot"]),
                "access_status": FACTOR_DB_V2["access_status"],
                "access_note": FACTOR_DB_V2["access_note"],
                "entries": list(FACTOR_ENTRIES),
            },
        ],
        "fallback_note": (
            "因子来源优先级（通则 7.4）：企业实测 > 官方因子库 > 行业缺省。"
            "官方因子库手摘未成（WAF 阻断）时，行业缺省值仍可用，且逐条挂行业指南附录 A 条款号。"
        ),
    }


def generate(data_dir=None, verbose=True):
    factors_dir = os.path.join(data_dir or DATA_DIR, "factors")
    if not os.path.isdir(factors_dir):
        os.makedirs(factors_dir)
    path = os.path.join(factors_dir, "manifest.json")
    jsonio.write(path, manifest_payload())
    if verbose:
        print("已生成：%s" % path)
        print("  因子条目：%d（因子库站点 WAF 阻断，未摘录 → 如实留空）" % len(FACTOR_ENTRIES))
    return manifest_payload()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = DATA_DIR
    if argv:
        if len(argv) == 2 and argv[0] == "--data-dir":
            data_dir = argv[1]
        else:
            print("用法：python tools/gen_factors.py [--data-dir <目录>]")
            return 2
    generate(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
