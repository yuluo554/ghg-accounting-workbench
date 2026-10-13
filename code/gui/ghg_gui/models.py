"""页面「视图模型」—— **零 Qt 依赖**，可在无显示环境直接测试。

为什么把这一层单独拎出来：GUI 的价值在于"界面能不能把引擎结论摆对"，
而"摆对"这件事不需要真的画窗口就能验证（把结果结构喂进来，断言呈现的文本/行数）。
Qt 页面（:mod:`ghg_gui.pages`）只负责把这里的文本塞进控件——
**逻辑在视图模型里，控件里没有 if**。

每个视图模型只做三件事：调 :class:`ghg_gui.service.WorkbenchService`、
把结构转成表格行、给出状态摘要文本。**不做任何判定**。
"""

from ghg.errors import GhgError

from .service import (
    LEVEL_ERROR,
    LEVEL_WARNING,
    QUOTA_NOT_APPLICABLE,
    WorkbenchService,
)

STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_NA = "not_applicable"


def _cell(value):
    return "" if value is None else str(value)


def _clause_text(clause):
    clause = clause or {}
    return "%s %s" % (clause.get("code") or "-", clause.get("article") or "-")


class ViewModel(object):
    """所有页面视图模型的基类：统一「状态 + 摘要 + 表格」三件套。"""

    #: 表格列标题（子类覆盖）
    headers = ()

    def __init__(self, service):
        self.service = service
        self.status = STATUS_NA
        self.summary = ""
        self.rows = []
        self.error = None

    def run(self, *args, **kwargs):        # pragma: no cover - 由子类实现
        raise NotImplementedError

    def _fail(self, exc):
        """把核心层异常转成界面可读的失败态（**不吞异常语义**，只做呈现）。"""
        self.status = STATUS_FAIL
        self.error = str(exc)
        self.summary = "失败：%s" % exc
        self.rows = []


class CalcPageModel(ViewModel):
    """核算页：完整编排结果（报告头 + 边界 + 明细 + 因子表 + 溯源表）。"""

    headers = ("源 id", "源名称", "活动数据", "单位", "因子", "因子来源", "排放量(tCO2e)")

    def run(self, payload, diff_standard=None):
        try:
            self.report = self.service.calc(payload, diff_standard=diff_standard)
        except GhgError as exc:
            self._fail(exc)
            return self
        calc = self.report["calc"]
        boundary = self.report["boundary"]
        head = self.report["report_head"]
        self.rows = [
            [_cell(line["source_id"]), _cell(line["source_name"]),
             _cell((line.get("activity") or {}).get("value")),
             _cell((line.get("activity") or {}).get("unit")),
             _cell((line.get("factor") or {}).get("value")),
             _cell((line.get("factor") or {}).get("source")),
             _cell(line["emission"])]
            for line in calc["lines"]
        ]
        self.status = STATUS_OK
        self.summary = (
            "坐标 %s；应核算 %d 项，纳入 %d 项；排放总量 %s %s；溯源 %d 行 = 明细 %d + 因子 %d"
            % (head["coordinate"], boundary["required_count"], boundary["included_count"],
               calc["total"], calc["unit"], self.report["provenance_counts"]["total"],
               self.report["provenance_counts"]["detail_rows"],
               self.report["provenance_counts"]["factor_rows"])
        )
        return self

    def provenance_rows(self):
        return [[_cell(r["position"]), _cell(r["value"]), _cell(r["activity_source"]),
                 _cell(r["factor_source"]), _clause_text(r.get("clause")),
                 _cell(r["rule_entry_id"])]
                for r in (getattr(self, "report", None) or {}).get("provenance", [])]


class CheckPageModel(ViewModel):
    """校核页：分级问题清单（错误 / 警告 / 提示）。"""

    headers = ("级别", "规则 id", "对象", "问题描述", "建议")

    def run(self, payload, baseline=None):
        try:
            self.report = self.service.check(payload, baseline=baseline)
        except GhgError as exc:
            self._fail(exc)
            return self
        counts = self.report["counts"]
        self.rows = [
            [_cell(issue["level"]), _cell(issue["rule_id"]),
             _cell(issue["source_id"] or "全厂"), _cell(issue["message"]),
             _cell(issue.get("advice"))]
            for issue in self.report["issues"]
        ]
        self.status = STATUS_OK
        self.summary = ("问题 %d 条（错误 %d / 警告 %d / 提示 %d）；规则执行 %d / %d"
                        % (self.report["issue_count"],
                           counts.get(LEVEL_ERROR, 0), counts.get(LEVEL_WARNING, 0),
                           counts.get("info", 0), len(self.report["rules_executed"]),
                           self.report["rules_total"]))
        if self.report["rules_skipped"]:
            skipped = "、".join(s["type"] for s in self.report["rules_skipped"])
            self.summary += "；跳过：%s" % skipped
        return self

    def has_error(self):
        return bool((getattr(self, "report", None) or {}).get("counts", {}).get(LEVEL_ERROR))


class QuotaPageModel(ViewModel):
    """配额页：方法学 / 参数 / 结果 / 免责声明。"""

    headers = ("项目", "内容")

    def run(self, payload, params=None):
        try:
            self.report = self.service.quota(payload, params=params)
        except GhgError as exc:
            self._fail(exc)
            return self
        report = self.report
        self.rows = [["方法学", _cell(report["method"])],
                     ["核算排放量", "%s %s" % (report["actual"], report["unit"])],
                     ["试算配额量", _cell(report["allocated"])],
                     ["履约缺口", _cell(report["gap"])],
                     ["缺口占比", _cell(report["gap_ratio"])]]
        for key in sorted(report["parameters"]):
            value = report["parameters"][key]
            if isinstance(value, dict):
                self.rows.append(["参数 %s" % key,
                                  "%s（来源：%s）" % (value.get("value"), value.get("source"))])
            else:
                self.rows.append(["参数 %s" % key, _cell(value)])
        for note in report["notes"]:
            self.rows.append(["说明", _cell(note)])
        self.status = STATUS_OK
        if report["status"] == QUOTA_NOT_APPLICABLE:
            self.summary = "方法学 %s；本坐标不适用配额试算" % report["method"]
        else:
            self.summary = ("方法学 %s；试算配额量 %s %s；履约缺口 %s %s"
                            % (report["method"], report["allocated"], report["unit"],
                               report["gap"], report["unit"]))
        return self

    def disclaimer(self):
        """免责声明文本（结构体恒定要求渲染层输出，R3 / NFR-10）。"""
        report = getattr(self, "report", None) or {}
        if not report.get("disclaimer_required"):
            return ""
        return report.get("disclaimer") or ""


class BenchPageModel(ViewModel):
    """基准页：三类套件结果 + 指标判定。"""

    headers = ("指标", "实测", "门槛", "判定")

    def run(self, suites=None):
        try:
            self.report = self.service.bench(suites=suites)
        except GhgError as exc:
            self._fail(exc)
            return self
        report = self.report
        self.rows = [
            [_cell(verdict["metric"]), _cell(verdict.get("value")),
             _cell(verdict.get("target")), "达标" if verdict.get("met") else "未达标"]
            for verdict in report["verdicts"]
        ]
        self.status = STATUS_OK if report["ok"] else STATUS_FAIL
        suites_text = "、".join(
            "%s %s/%s" % (report["suites"][name]["suite"],
                          report["suites"][name]["checks_passed"],
                          report["suites"][name]["checks_total"])
            for name in report["suites_run"])
        self.summary = "套件：%s；结论：%s" % (suites_text,
                                              "全部达标" if report["ok"] else "存在未达标")
        return self


def build_models(service):
    """一次会话的四个页面视图模型（供窗口与测试共用）。"""
    return {
        "calc": CalcPageModel(service),
        "check": CheckPageModel(service),
        "quota": QuotaPageModel(service),
        "bench": BenchPageModel(service),
    }


__all__ = ["ViewModel", "CalcPageModel", "CheckPageModel", "QuotaPageModel",
           "BenchPageModel", "build_models", "WorkbenchService",
           "STATUS_OK", "STATUS_FAIL", "STATUS_NA"]