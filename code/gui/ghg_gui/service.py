"""GUI 与核心层之间的**唯一**调用点（FR-08.2「只消费引擎 API」）。

本模块把 ``ghg`` 的编排/校核/配额/基准 API 收口成一组无状态方法，页面只调用这里。
好处有二：

  1. **不另起第二套行为**：GUI 与 CLI 走同一批函数（``pipeline.compute_full`` /
     ``quality.run_checks`` / ``quota.compute_quota`` / ``bench.run_bench``），
     不存在"界面算一套、命令行算一套"的漂移面；
  2. **可测**：offscreen 测试直接调服务层即可覆盖界面逻辑，无需模拟点击。

数值/阈值/方法学**一律不在此判断**——本模块只做参数透传与结果回传。
"""

import os

from ghg import __version__ as engine_version
from ghg import quality, quota
from ghg.bench import run_bench
from ghg.decimals import to_text
from ghg.errors import InputError
from ghg.jsonio import load as load_json
from ghg.paths import find_data_dir
from ghg.pipeline import compute_full
from ghg.report import export_all, load_clause_index
from ghg.rules import (
    SCOPE_CALC,
    SCOPE_CHECK,
    SCOPE_QUOTA,
    RulesIndex,
    parse_payload_coordinate,
)
from ghg.units import UnitTable

# 内置示例档案目录（随包分发；演示与冒烟用）
PROFILE_SUBDIR = ("truth", "profiles")

# 本模块是 GUI 侧**唯一**允许直接 import 引擎判定模块（calc/quality/quota/bench）的文件
# （由 test_m5_gui.py 的导入门禁锁定）；其余页面/视图模型一律经本模块转发。
GATEWAY_MODULE = "service.py"

# 呈现用枚举：**从引擎转发**（单一真相源），供视图模型做分级文案；
# 页面层不得再开一条 import 通道（见 test_m5_gui.py 导入门禁）。
LEVEL_ERROR = quality.LEVEL_ERROR
LEVEL_WARNING = quality.LEVEL_WARNING
LEVEL_INFO = quality.LEVEL_INFO
QUOTA_NOT_APPLICABLE = quota.STATUS_NOT_APPLICABLE


class WorkbenchService(object):
    """引擎门面：一次会话共用一个数据目录、规则索引与单位表。"""

    def __init__(self, data_dir=None):
        self.data_dir = find_data_dir(data_dir)
        self.index = RulesIndex.load(self.data_dir)
        self.units = UnitTable.load(self.data_dir)

    # ---------- 元信息 ----------

    def version(self):
        return engine_version

    def standards(self):
        """``[(短键, 标签)]``（标签取自 manifest，代码零坐标字面量）。"""
        labels = (self.index._manifest.get("labels") or {}).get("standards", {})
        return [(key, labels.get(key, "")) for key in self.index.standards]

    def industries(self):
        labels = (self.index._manifest.get("labels") or {}).get("industries", {})
        return [(key, labels.get(key, "")) for key in self.index.industries]

    def years(self):
        return list(self.index.years)

    def coordinates(self):
        return [coord.key for coord in self.index.coordinates()]

    def gate_summary(self, coord):
        """三个作用域的门控体检（核算 / 配额 / 校核），直接透传 ``gate_report``。"""
        return {
            "calc": self.index.gate_report(coord, scope=SCOPE_CALC),
            "quota": self.index.gate_report(coord, scope=SCOPE_QUOTA),
            "check": self.index.gate_report(coord, scope=SCOPE_CHECK),
        }

    def sample_profiles(self):
        """内置示例档案路径列表（按名排序；缺失返回空列表）。"""
        directory = os.path.join(self.data_dir, *PROFILE_SUBDIR)
        if not os.path.isdir(directory):
            return []
        return [os.path.join(directory, name)
                for name in sorted(os.listdir(directory)) if name.endswith(".json")]

    # ---------- 四类操作（全部为引擎 API 透传）----------

    def calc(self, payload, diff_standard=None, generated_at=None):
        coord = parse_payload_coordinate(payload, index=self.index)
        return compute_full(payload, coord, self.index, self.units,
                            diff_standard=diff_standard, generated_at=generated_at)

    def check(self, payload, baseline=None):
        coord = parse_payload_coordinate(payload, index=self.index)
        pack = self.index.effective_ruleset(coord, scope=SCOPE_CHECK)
        calc = compute_full(payload, coord, self.index, self.units)["calc"]
        baseline_calc = None
        if baseline is not None:
            baseline_calc = self.calc(baseline)["calc"]
        return quality.run_checks(payload, calc, coord, pack, units=self.units,
                                  baseline=baseline_calc)

    def quota(self, payload, params=None):
        coord = parse_payload_coordinate(payload, index=self.index)
        pack = self.index.effective_ruleset(coord, scope=SCOPE_QUOTA)
        calc = compute_full(payload, coord, self.index, self.units)["calc"]
        merged = quota.quota_inputs_from_profile(payload)
        for key, value in (params or {}).items():
            if value is not None:
                merged[key] = value
        return quota.compute_quota(pack, coord, calc["total_raw"], params=merged)

    def bench(self, suites=None):
        return run_bench(data_dir=self.data_dir, suites=suites,
                         index=self.index, units=self.units)

    # ---------- 导出 ----------

    def export(self, payload, out_dir, formats=("md",), quality=None, quota=None,
               basename="report", diff_standard=None, generated_at=None):
        """导出可核证报告（三产物由 :func:`ghg.report.export_all` 决定）。"""
        if not os.path.isdir(out_dir):
            raise InputError("输出目录不存在：%s" % out_dir)
        report = self.calc(payload, diff_standard=diff_standard, generated_at=generated_at)
        return export_all(report, out_dir, formats=formats, quality=quality, quota=quota,
                          clause_index=load_clause_index(self.data_dir), basename=basename)

    def load_profile(self, path):
        """读取企业档案 JSON（float → Decimal）。"""
        return load_json(path)


def load_profile(path):
    """模块级便捷函数（页面在无服务实例时也可读档案）。"""
    return load_json(path)


def ratio_text(value):
    """比率的统一呈现（透传核心层量化口径，界面不自行取舍精度）。"""
    return to_text(value)


__all__ = ["WorkbenchService", "load_profile", "ratio_text", "PROFILE_SUBDIR"]