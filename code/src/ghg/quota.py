"""行业配额试算（FR-05，M3 落地）。

**方法学切换即切换公式分支**（FR-05.1）——公式分支由规则包 ``quota.method`` 决定，
代码不内联方法学名与公式：

  * ``benchmark``（发电：碳排放强度基准法）
        A = Qe × Be × Ff
        Qe 发电量 / Be 发电基准值 / Ff 调峰修正系数（官方原文见 ``data/knowledge/raw``）；
  * ``intensity_coefficient``（钢铁 / 水泥 / 铝冶炼：碳排放强度系数法）
        A = E × (1 + α)
        α 由"碳排放强度偏离度" X = (BP − Ii) / BP 经规则包 ``quota.derivation``
        的分段系数推出（对应方案表 3：|X| 小于带内取 斜率×X，越上限取 +封顶，越下限取 −封顶）；
  * ``historical_intensity``（历史强度法，扩展方法学）
        A = 产量 × 历史强度；
  * ``none``：不试算（显式返回"不适用"，而非静默给 0）。

**参数来源纪律（R2/R4 在试算层的落地）**：

  * ``verified`` 条目 → 直接用规则包数值（如发电 2025/2026 年度基准值）；
  * ``input_required`` 条目 → 该数值**不由规则包承载**（行业"平衡值"当年度由全国碳市场
    管理平台测算公布、方案正文未印；机组调峰修正系数随负荷率变化）→ **必须由调用方显式
    提供**；未提供即抛 :class:`QuotaUnavailable`（退出码 2），**绝不静默取 0 或 1**；
  * ``pending`` 条目 → 由门控在进入试算前拦截（退出码 1）。

**免责声明强制**（R3 / NFR-10）：:func:`compute_quota` 的返回结构**不含可选声明**——
``disclaimer_required`` 恒为 ``True``，``disclaimer`` 取规则包固定法律文本常量
（``report.disclaimer``）；渲染层必须输出该声明行。
"""

from decimal import Decimal

from .decimals import as_decimal, scale_for, to_text
from .errors import InputError, QuotaUnavailable
from .rules import STATUS_INPUT_REQUIRED, STATUS_VERIFIED

SCHEMA_QUOTA = "ghg-quotaresult/v1"

UNIT_EMISSION = "tCO2e"

METHOD_BENCHMARK = "benchmark"
METHOD_INTENSITY_COEFFICIENT = "intensity_coefficient"
METHOD_HISTORICAL_INTENSITY = "historical_intensity"
METHOD_NONE = "none"

STATUS_OK = "ok"
STATUS_NOT_APPLICABLE = "not_applicable"

# 产出数值的呈现小数位
QUOTA_PLACES = 3

# 百分比呈现小数位
PERCENT_PLACES = 2
PERCENT_SCALE = scale_for(PERCENT_PLACES)

# 百分数换算（ratio 量纲：1 = 100%）
_PERCENT = as_decimal("100")


def _plain(value):
    return to_text(value, QUOTA_PLACES)


def _entry_of(pack, path):
    """按点分路径取规则包条目；缺失返回 None。"""
    node = pack
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _verified(entry, label):
    """取已核对条目的数值；不可用即抛 :class:`QuotaUnavailable`。"""
    if not isinstance(entry, dict):
        raise QuotaUnavailable("配额参数缺失：%s" % label)
    if entry.get("status") != STATUS_VERIFIED or entry.get("value") is None:
        raise QuotaUnavailable("配额参数 %s 未核对（不得参与试算）" % label)
    return as_decimal(entry["value"])


def _resolve(entry, label, supplied):
    """解析一个试算参数：``verified`` → 规则包值；``input_required`` → 索取外部输入。

    返回 ``(数值, 来源标签)``。外部输入未提供即抛 :class:`QuotaUnavailable`
    （**不得静默取 0 或 1**）。
    """
    if isinstance(entry, dict) and entry.get("status") == STATUS_VERIFIED \
            and entry.get("value") is not None:
        return as_decimal(entry["value"]), "ruleset"
    if supplied is not None:
        return as_decimal(supplied), "caller"
    if isinstance(entry, dict) and entry.get("status") == STATUS_INPUT_REQUIRED:
        note = ((entry.get("clause") or {}).get("note") or "").strip()
        raise QuotaUnavailable(
            "配额参数 %s 需外部提供（规则包不承载该数值%s）；"
            "试算层不得静默取 0 —— 请通过参数显式给出" % (label, ("：" + note) if note else "")
        )
    raise QuotaUnavailable("配额参数 %s 不可用（未核对或缺失）" % label)


def _resolve_method(pack, override):
    """决定本次试算的方法学：显式覆盖 > 规则包声明；非法值即输入错误。"""
    quota = pack.get("quota", {}) or {}
    allowed = list(quota.get("allowed_methods") or ())
    method = override or quota.get("method")
    if not method:
        raise QuotaUnavailable("规则包未声明配额方法学（quota.method）")
    if allowed and method not in allowed:
        raise InputError("配额方法学 %r 不在规则包允许集合内：%s" % (method, allowed))
    return method


def _derive_alpha(pack, benchmark_value, intensity):
    """由碳排放强度偏离度 X = (BP − Ii) / BP 推出强度系数 α（方案表 3 分段）。

    分段常数一律取自规则包 ``quota.derivation``（``slope`` / ``band`` / ``cap``），
    代码零阈值字面量（NFR-07）。
    """
    derivation = (pack.get("quota", {}) or {}).get("derivation") or {}
    slope = _verified(derivation.get("slope"), "quota.derivation.slope")
    band = _verified(derivation.get("band"), "quota.derivation.band")
    cap = _verified(derivation.get("cap"), "quota.derivation.cap")
    if benchmark_value == 0:
        raise QuotaUnavailable("行业平衡值（BP）为 0，无法计算碳排放强度偏离度")
    x = (benchmark_value - intensity) / benchmark_value
    if x >= band:
        return cap, x
    if x <= -band:
        return -cap, x
    return slope * x, x


def _trial_inputs(params):
    """从调用方参数里取出试算输入（None 表示未提供）。数值一律规整为标量。"""
    params = params or {}
    return {
        "benchmark_value": _scalar(params.get("benchmark_value"), "benchmark_value"),
        "correction_factor": _scalar(params.get("correction_factor"), "correction_factor"),
        "output": _scalar(params.get("output"), "output"),
        "historical_intensity": _scalar(params.get("historical_intensity"),
                                        "historical_intensity"),
    }


def _scalar(value, label):
    """把试算输入规整为可计算标量。

    接受 ``Decimal`` / 字符串 / 整数，或形如 ``{"value": ..., "unit": ...}`` 的条目；
    其余类型抛 :class:`QuotaUnavailable`（输入不可用 → 退出码 2，不得静默取 0）。
    """
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
        if value is None:
            raise QuotaUnavailable("配额试算输入 %s 缺少 value 字段" % label)
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise QuotaUnavailable("配额试算输入 %s 类型非法：%r" % (label, type(value).__name__))
    try:
        return as_decimal(value)
    except (ArithmeticError, ValueError):
        raise QuotaUnavailable("配额试算输入 %s 无法解析为数值：%r" % (label, value))


def quota_inputs_from_profile(profile):
    """从企业档案抽取试算输入（产量 / 历史强度 / 档案自报参数）。

    档案可携带 ``quota_inputs`` 子对象显式给出试算参数（合成算例与批处理用）；
    ``output`` 优先取档案顶层字段，其次取 ``quota_inputs.output``。
    返回值中的数值一律规整为标量（``output`` 可写作 ``{"value":..,"unit":..}``）。
    """
    profile = profile or {}
    explicit = dict(profile.get("quota_inputs") or {})
    output = profile.get("output")
    if output is not None and explicit.get("output") is None:
        explicit["output"] = output
    return {key: _scalar(value, key) for key, value in explicit.items()}


def compute_quota(pack, coord, actual, params=None):
    """按规则包方法学试算配额，返回 :class:`QuotaResult` 结构（FR-05.1/FR-05.2）。

    参数
    ----
    pack   : **已过门控**的规则包（``effective_ruleset(coord, scope="quota")``）
    coord  : 坐标（:class:`ghg.coordinates.Coordinate`）
    actual : 核算排放量（tCO2e；Decimal / 字符串）
    params : 试算输入（``benchmark_value`` / ``correction_factor`` / ``output`` /
             ``historical_intensity`` / ``method``）；缺省从规则包与外部输入解析。

    返回的 ``allocated`` / ``gap`` / ``gap_ratio`` 在 ``method == "none"`` 时为 ``None``
    （显式"不适用"，不是 0）。
    """
    quota = pack.get("quota", {}) or {}
    method = _resolve_method(pack, (params or {}).get("method"))
    supplied = _trial_inputs(params)
    actual_value = as_decimal(actual)

    notes = []
    allocated = None
    parameters = {}
    deviation = None

    if method == METHOD_NONE:
        notes.append("规则包声明本坐标不适用配额试算（method=none），未产生配额量")
    elif method == METHOD_BENCHMARK:
        output = supplied["output"]
        if output is None:
            raise QuotaUnavailable(
                "基准法试算需要产量/发电量（output）——试算层不得静默取 0")
        benchmark, bm_source = _resolve(
            _entry_of(pack, "quota.params.benchmark_value"), "quota.params.benchmark_value",
            supplied["benchmark_value"])
        factor, ff_source = _resolve(
            _entry_of(pack, "quota.params.correction_factor"), "quota.params.correction_factor",
            supplied["correction_factor"])
        allocated = as_decimal(output) * benchmark * factor
        parameters = {
            "output": _plain(as_decimal(output)),
            "benchmark_value": {"value": _plain(benchmark), "source": bm_source},
            "correction_factor": {"value": _plain(factor), "source": ff_source},
        }
    elif method == METHOD_INTENSITY_COEFFICIENT:
        # A = E × (1 + α)；α 由偏离度 X=(BP−Ii)/BP 经规则包分段常数推出（表 3）。
        # 调用方可显式给出 correction_factor 以跳过推导（用于"α 已由主管部门核定"的情形）。
        explicit_alpha = supplied["correction_factor"]
        if explicit_alpha is not None:
            alpha = as_decimal(explicit_alpha)
            alpha_source = "caller"
            notes.append("强度系数 α 由调用方显式给定（未按表 3 偏离度分段推导）")
        else:
            output = supplied["output"]
            if output is None:
                raise QuotaUnavailable(
                    "强度系数法推导 α 需要产量（output）以计算企业实际强度 Ii；"
                    "或直接显式给出 correction_factor")
            benchmark, bm_source = _resolve(
                _entry_of(pack, "quota.params.benchmark_value"),
                "quota.params.benchmark_value", supplied["benchmark_value"])
            intensity = actual_value / as_decimal(output)
            alpha, deviation = _derive_alpha(pack, benchmark, intensity)
            alpha_source = "derived"
            parameters["benchmark_value"] = {"value": _plain(benchmark), "source": bm_source}
            parameters["output"] = _plain(as_decimal(output))
            parameters["intensity"] = _plain(intensity)
            parameters["deviation"] = _plain(deviation)
        allocated = actual_value * (as_decimal(1) + alpha)
        parameters["correction_factor"] = {"value": _plain(alpha), "source": alpha_source}
    elif method == METHOD_HISTORICAL_INTENSITY:
        output = supplied["output"]
        if output is None:
            raise QuotaUnavailable(
                "历史强度法试算需要产量（output）——试算层不得静默取 0")
        intensity = supplied["historical_intensity"]
        if intensity is None:
            raise QuotaUnavailable(
                "历史强度法试算需要历史强度（historical_intensity）——试算层不得静默取 0")
        allocated = as_decimal(output) * as_decimal(intensity)
        parameters = {
            "output": _plain(as_decimal(output)),
            "historical_intensity": {"value": _plain(as_decimal(intensity)), "source": "caller"},
        }
    else:                                    # pragma: no cover - 由 _resolve_method 挡住
        raise InputError("未实现的配额方法学：%r" % method)

    if allocated is None:
        gap = None
        gap_ratio = None
        status = STATUS_NOT_APPLICABLE
    else:
        gap = allocated - actual_value
        gap_ratio = (gap / actual_value) if actual_value != 0 else None
        status = STATUS_OK

    disclaimer = (pack.get("report", {}) or {}).get("disclaimer")
    return {
        "schema": SCHEMA_QUOTA,
        "coordinate": coord.key,
        "method": method,
        "method_clause": quota.get("method_clause"),
        "status": status,
        "actual": _plain(actual_value),
        "allocated": None if allocated is None else _plain(allocated),
        "gap": None if gap is None else _plain(gap),
        "gap_ratio": None if gap_ratio is None else _plain(gap_ratio),
        # 全精度口径（对账用；呈现层用上面的量化值）
        "actual_raw": str(actual_value),
        "allocated_raw": None if allocated is None else str(allocated),
        "gap_raw": None if gap is None else str(gap),
        "gap_ratio_raw": None if gap_ratio is None else str(gap_ratio),
        "unit": UNIT_EMISSION,
        "parameters": parameters,
        "notes": notes,
        # 免责声明强制（R3 / NFR-10）：结构体不含可选声明，恒定要求渲染层输出
        "disclaimer_required": True,
        "disclaimer": disclaimer,
    }


def render_quota_text(report):
    """人类可读的配额试算输出（CLI 用）。免责声明强制输出。"""
    lines = [
        "配额试算结果（坐标 %s）" % report["coordinate"],
        "  方法学：%s" % report["method"],
    ]
    clause = report.get("method_clause") or {}
    if clause.get("code") or clause.get("article"):
        lines.append("  依据：%s %s" % (clause.get("code") or "-", clause.get("article") or "-"))
    lines.append("  核算排放量：%s %s" % (report["actual"], report["unit"]))
    if report["status"] == STATUS_NOT_APPLICABLE:
        lines.append("  试算配额量：（不适用——规则包声明本坐标不适用配额试算）")
        lines.append("  履约缺口：（不适用）")
    else:
        lines.append("  试算配额量：%s %s" % (report["allocated"], report["unit"]))
        gap = as_decimal(report["gap"])
        direction = "缺口" if gap > 0 else "盈余"
        ratio = report["gap_ratio"]
        ratio_text = "" if ratio is None else "（占排放量 %s）" % _percent_text(ratio)
        lines.append("  履约预判：%s %s %s %s"
                     % (direction, _plain(abs(gap)), report["unit"], ratio_text))
    for key in sorted(report["parameters"]):
        value = report["parameters"][key]
        if isinstance(value, dict):
            lines.append("  参数 %s：%s（来源：%s）" % (key, value.get("value"), value.get("source")))
        else:
            lines.append("  参数 %s：%s" % (key, value))
    for note in report["notes"]:
        lines.append("  说明：%s" % note)
    if report.get("disclaimer_required"):
        lines.append("  免责声明：%s" % (report.get("disclaimer") or "（缺失——不得对外输出）"))
    return "\n".join(lines)


def _percent_text(ratio):
    percent = as_decimal(ratio) * _PERCENT
    return "%s%%" % _plain(percent.quantize(PERCENT_SCALE))