"""数据质量校核层（FR-04，M3 落地）。

设计要点（plan/04 §四）：

* **规则化**：校核规则集来自规则包 ``quality.rules[]``（id / type / level / 依据 / 建议），
  按 ``type`` 分派到四个检查器：``unit_consistency`` / ``magnitude_outlier`` /
  ``yoy_jump`` / ``intensity_plausibility``（FR-04.1/FR-04.2）。
* **零阈值字面量**：一切判据阈值取自规则包 ``quality.thresholds``（NFR-07）；
  本模块内**不出现任何阈值数值**——阈值只经 ``_threshold()`` 读出。
* **只读层**：本模块不修改 ``profile`` / ``calc`` 任何字段（FR-04.4）；
  所有中间量都是本地新建对象，输出走新构造的 :class:`QualityReport` 结构。
* **分级问题清单**：每条问题挂 ``rule_id`` / ``level`` / ``clause`` / ``advice``（FR-04.3）。

与门控的关系（plan/04 §4.3）：``pending`` 的校核规则**不执行**——不得以未核对阈值报结论。
本模块对无法执行的规则记入 ``rules_skipped``（附原因），绝不静默按"通过"处理；
``check`` 子命令在 ``quality`` 块整体未生效时由门控返回退出码 1。

阈值语义（M3 工程定值，非政策数值；见 plan/06 D3-1）：

* ``magnitude``（ratio）—— 单个排放源排放量占全厂合计的**占比上限**（粗筛）；
  单源档案跳过（占比恒为 1，无筛查信息量）；
* ``yoy``（ratio）—— 同一源跨年度活动数据的**变化率上限**（需提供上一年度基线）；
* ``intensity_min`` / ``intensity_max``（tCO2e_per_unit_output）—— 比强度合理区间
  （需档案提供 ``output`` 产量）。

级别口径（plan/06 D3-4）：规则的 ``level`` 是"硬违规"的级别；当违规**可被显式换算/
可解释**时降一级报出（如"单位口径不一致但可换算"报 ``warning`` 而非 ``error``），
避免把"引擎已正确处理"的情形误报为致命错误。
"""

from .decimals import as_decimal, scale_for
from .errors import QualityError
from .units import split_compound_unit

SCHEMA_QUALITY = "ghg-qualityreport/v1"

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"
LEVELS = (LEVEL_ERROR, LEVEL_WARNING, LEVEL_INFO)

# 检查类型（与规则包 quality.rules[].type 一致）
TYPE_UNIT = "unit_consistency"
TYPE_MAGNITUDE = "magnitude_outlier"
TYPE_YOY = "yoy_jump"
TYPE_INTENSITY = "intensity_plausibility"

# 阈值键（规则包 quality.thresholds.<key>）
TH_MAGNITUDE = "magnitude"
TH_YOY = "yoy"
TH_INTENSITY_MIN = "intensity_min"
TH_INTENSITY_MAX = "intensity_max"

# 无量纲单位的文本形态（与 units.json 的 ratio 量纲基准一致）
_DIMENSIONLESS = ("1", "", None)

# 比率呈现小数位（百分比保留 2 位）
RATIO_TEXT_PLACES = 2
RATIO_TEXT_SCALE = scale_for(RATIO_TEXT_PLACES)

# 百分数换算（ratio 量纲：1 = 100%）
_PERCENT = as_decimal("100")


def _threshold(pack, key):
    """读取规则包阈值条目；不可用（未核对 / 缺值 / 缺单位）返回 ``None``。

    阈值一律**从规则包读出**，本模块不内联任何阈值数值（NFR-07）。
    """
    entry = (pack.get("quality", {}) or {}).get("thresholds", {}).get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("status") != "verified" or entry.get("value") is None:
        return None
    return as_decimal(entry["value"])


def _rules_by_type(pack):
    out = {}
    for rule in (pack.get("quality", {}) or {}).get("rules", []) or []:
        out.setdefault(rule.get("type"), []).append(rule)
    return out


def _clause_of(rule):
    return rule.get("clause")


def _issue(rule, source_id, message, level=None):
    return {
        "rule_id": rule.get("id"),
        "type": rule.get("type"),
        "level": level or rule.get("level"),
        "source_id": source_id,
        "message": message,
        "clause": _clause_of(rule),
        "advice": rule.get("advice"),
    }


def _lines_of(calc):
    return list((calc or {}).get("lines") or [])


def _declared_sources(profile):
    out = {}
    for item in (profile or {}).get("sources", []) or []:
        sid = item.get("source_id")
        if sid:
            out[sid] = item
    return out


def _unit_known(units, unit):
    if unit in _DIMENSIONLESS:
        return True
    if units is None:
        return True                      # 无单位表时不误报（校核降级为"未执行"由调用方决定）
    return units.known(unit)


# --------------------------------------------------------------------------
# 四类检查
# --------------------------------------------------------------------------

def _check_unit_consistency(pack, units, profile, calc, rules):
    """单位一致性：活动数据单位 ↔ 因子单位 ↔ 规则包口径可换算且量纲一致。

    两类发现：
      * **硬违规**（按规则 ``level`` 报出）：活动数据单位未知 / 因子分母与活动单位量纲不一致；
      * **口径不一致**（降级为 ``warning``）：同量纲但单位不同（引擎已显式换算，仍需统一录入口径）。
    """
    issues = []
    lines = {line["source_id"]: line for line in _lines_of(calc)}
    declared = _declared_sources(profile)

    for rule in rules:
        # 1) 档案声明的活动数据单位必须可识别（含未纳入核算的源：录入错误同样要拦）
        for sid in sorted(declared):
            activity = (declared[sid].get("activity") or {})
            unit = activity.get("unit")
            if activity.get("value") is None:
                continue
            if not _unit_known(units, unit):
                issues.append(_issue(
                    rule, sid,
                    "活动数据单位无法识别：%r（不在单位换算表中）" % (unit,)))

        # 2) 因子分母与活动数据量纲必须一致；同量纲不同单位则记为口径不一致
        for sid in sorted(lines):
            line = lines[sid]
            act_unit = (line.get("activity") or {}).get("unit")
            fac_unit = (line.get("factor") or {}).get("unit")
            _numerator, denominator = split_compound_unit(fac_unit)
            if denominator is None or units is None:
                continue
            if not _unit_known(units, act_unit):
                continue
            if not units.known(denominator):
                issues.append(_issue(
                    rule, sid, "因子单位分母无法识别：%r（因子单位 %s）" % (denominator, fac_unit)))
                continue
            if units.dimension_of(denominator) != units.dimension_of(act_unit):
                issues.append(_issue(
                    rule, sid,
                    "因子分母与活动数据量纲不一致：%s vs %s（因子单位 %s）"
                    % (denominator, act_unit, fac_unit)))
                continue
            if denominator != act_unit:
                issues.append(_issue(
                    rule, sid,
                    "活动数据单位 %s 与因子单位分母 %s 口径不一致（已显式换算）"
                    % (act_unit, denominator),
                    level=LEVEL_WARNING))
    return issues


def _check_magnitude(pack, profile, calc, rules):
    """量级异常：单源排放量占全厂合计的占比超过规则包阈值（粗筛）。"""
    threshold = _threshold(pack, TH_MAGNITUDE)
    if threshold is None:
        return None
    lines = _lines_of(calc)
    if len(lines) < 2:
        return []                       # 单源档案：占比恒为 1，无筛查信息量
    total = sum((as_decimal(line["emission_raw"]) for line in lines), as_decimal(0))
    if total == 0:
        return []
    issues = []
    for rule in rules:
        for line in lines:
            share = as_decimal(line["emission_raw"]) / total
            if share > threshold:
                issues.append(_issue(
                    rule, line["source_id"],
                    "单源排放量占全厂合计 %s，超过规则包量级筛查阈值 %s"
                    % (_ratio_text(share), _ratio_text(threshold))))
    return issues


def _check_yoy(pack, profile, calc, rules, baseline):
    """跨年度突变：同一源活动数据相对上一年度的变化率超过规则包阈值。"""
    if baseline is None:
        return None
    threshold = _threshold(pack, TH_YOY)
    if threshold is None:
        return None
    now = {line["source_id"]: line for line in _lines_of(calc)}
    before = {line["source_id"]: line for line in _lines_of(baseline)}
    issues = []
    for rule in rules:
        for sid in sorted(set(now) & set(before)):
            new_value = _activity_value(now[sid])
            old_value = _activity_value(before[sid])
            if new_value is None or old_value in (None, as_decimal(0)):
                continue
            change = abs(new_value - old_value) / abs(old_value)
            if change > threshold:
                issues.append(_issue(
                    rule, sid,
                    "活动数据跨年度变化率 %s，超过规则包阈值 %s（上年度 %s → 本年度 %s）"
                    % (_ratio_text(change), _ratio_text(threshold),
                       _plain(old_value), _plain(new_value))))
    return issues


def _check_intensity(pack, profile, calc, rules):
    """比强度合理性：全厂排放量 / 产量 是否落在规则包声明区间。"""
    low = _threshold(pack, TH_INTENSITY_MIN)
    high = _threshold(pack, TH_INTENSITY_MAX)
    if low is None or high is None:
        return None
    output = (profile or {}).get("output") or {}
    if output.get("value") is None:
        return None
    quantity = as_decimal(output["value"])
    if quantity == 0:
        return None
    total = sum((as_decimal(line["emission_raw"]) for line in _lines_of(calc)), as_decimal(0))
    intensity = total / quantity
    if low <= intensity <= high:
        return []
    issues = []
    for rule in rules:
        issues.append(_issue(
            rule, None,
            "比强度 %s 落在规则包区间 [%s, %s] 之外（排放量 %s / 产量 %s %s）"
            % (_ratio_text(intensity), _ratio_text(low), _ratio_text(high),
               _plain(total), _plain(quantity), output.get("unit") or "-")))
    return issues


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------

def run_checks(profile, calc, coord, pack, units=None, baseline=None):
    """执行四类数据质量检查，返回 :class:`QualityReport` 结构（只读，FR-04.4）。

    参数
    ----
    profile   : 企业档案（dict）
    calc      : 该档案的核算结果（``ghg.calc.compute`` 的输出）——**只读**，不得修改
    coord     : 坐标（:class:`ghg.coordinates.Coordinate`）
    pack      : **已过门控**的规则包（``effective_ruleset(coord, scope="check")``）
    units     : :class:`ghg.units.UnitTable`（单位一致性检查用；缺省则跳过单位项）
    baseline  : 上一年度同坐标的核算结果（``yoy_jump`` 用；缺省则跳过该项）

    ``pending`` 的规则与不可用阈值对应的检查**不执行**，记入 ``rules_skipped``（附原因）。
    """
    if calc is None:
        raise QualityError("校核层需要核算结果（calc 不得为空）")

    by_type = _rules_by_type(pack)
    issues = []
    executed = []
    skipped = []

    def _dispatch(check_type, runner, *args, **kwargs):
        rules = by_type.get(check_type)
        if not rules:
            return
        result = runner(*args, **kwargs)
        if result is None:
            skipped.append({
                "type": check_type,
                "rule_ids": [r.get("id") for r in rules],
                "reason": _skip_reason(check_type, baseline),
            })
            return
        executed.extend(r.get("id") for r in rules)
        issues.extend(result)

    _dispatch(TYPE_UNIT, _check_unit_consistency, pack, units, profile, calc,
              by_type.get(TYPE_UNIT) or [])
    _dispatch(TYPE_MAGNITUDE, _check_magnitude, pack, profile, calc,
              by_type.get(TYPE_MAGNITUDE) or [])
    _dispatch(TYPE_YOY, _check_yoy, pack, profile, calc,
              by_type.get(TYPE_YOY) or [], baseline)
    _dispatch(TYPE_INTENSITY, _check_intensity, pack, profile, calc,
              by_type.get(TYPE_INTENSITY) or [])

    counts = {level: 0 for level in LEVELS}
    for issue in issues:
        counts[issue["level"]] = counts.get(issue["level"], 0) + 1

    ordered = sorted(issues, key=lambda i: (LEVELS.index(i["level"])
                                            if i["level"] in LEVELS else len(LEVELS),
                                            i["rule_id"] or "", i["source_id"] or ""))
    return {
        "schema": SCHEMA_QUALITY,
        "coordinate": coord.key,
        "issues": ordered,
        "counts": counts,
        "issue_count": len(ordered),
        "rules_total": sum(len(v) for v in by_type.values()),
        "rules_executed": sorted(set(executed)),
        "rules_skipped": skipped,
    }


def _skip_reason(check_type, baseline):
    if check_type == TYPE_YOY and baseline is None:
        return "未提供上一年度核算结果（yoy_jump 需跨年度对比）"
    if check_type == TYPE_INTENSITY:
        return "档案未提供产量（output）或规则包比强度阈值未生效"
    if check_type == TYPE_MAGNITUDE:
        return "规则包量级阈值未生效"
    return "规则包阈值未生效（未核对）"


# --------------------------------------------------------------------------
# 呈现
# --------------------------------------------------------------------------

def _activity_value(line):
    """取明细行的活动数据数值（基本单位口径），无则 None。"""
    base = line.get("activity_base") or {}
    if base.get("value") is None:
        return None
    return as_decimal(base["value"])


def _plain(value):
    text = format(as_decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _ratio_text(value):
    """比率呈现（百分比，保留约定小数位）。"""
    percent = as_decimal(value) * _PERCENT
    return "%s%%" % _plain(percent.quantize(RATIO_TEXT_SCALE))


def render_quality_text(report):
    """人类可读的校核输出（CLI 用）。"""
    counts = report["counts"]
    lines = [
        "数据质量校核结果（坐标 %s）" % report["coordinate"],
        "  规则总数：%d；已执行：%d" % (report["rules_total"], len(report["rules_executed"])),
        "  问题计数：错误 %d / 警告 %d / 提示 %d（合计 %d）"
        % (counts.get(LEVEL_ERROR, 0), counts.get(LEVEL_WARNING, 0),
           counts.get(LEVEL_INFO, 0), report["issue_count"]),
    ]
    if not report["issues"]:
        lines.append("  （无命中问题）")
    for issue in report["issues"]:
        clause = issue.get("clause") or {}
        target = ("源 %s" % issue["source_id"]) if issue["source_id"] else "全厂"
        lines.append("  [%s] %s %s：%s"
                     % (issue["level"], issue["rule_id"], target, issue["message"]))
        if clause.get("code") or clause.get("article"):
            lines.append("        依据：%s %s"
                         % (clause.get("code") or "-", clause.get("article") or "-"))
        if issue.get("advice"):
            lines.append("        建议：%s" % issue["advice"])
    for skip in report["rules_skipped"]:
        lines.append("  [跳过] %s（%s）：%s"
                     % ("、".join(skip["rule_ids"]), skip["type"], skip["reason"]))
    return "\n".join(lines)