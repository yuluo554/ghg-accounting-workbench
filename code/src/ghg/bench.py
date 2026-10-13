"""内置离线基准（FR-07，M4 落地）。

三类基准，一条命令跑全（``ghg bench``）：

  1. **规则自洽**（FR-07.1）—— 新旧通则 × 四行业 × 多年度共 40 份规则包逐条自洽扫描：
     表达式文法合法、公式引用可解析、系数状态自洽、排放源条目完备、门控作用域划分一致、
     双标尺差异声明与结构交叉一致、校核规则与配额方法学声明完备。
  2. **因子与单位一致**（FR-07.2）—— 单位换算全量往返、跨量纲拒绝、因子单位复合拆分可解析、
     同源因子跨年不漂移、跨通则同行业一致、因子优先级白名单一致。
  3. **边界与异常用例**（FR-07.3）—— 复用 ``data/truth/expected.json`` 的用例与档案：
     异常用例命中率、干净档案误报率（对照）、逐档案真值双路对账。

设计纪律（与全项目一致）：

  * **零 API 依赖 / 固定输入可复现**（FR-07.4）：只读 ``data/`` 冻结产物，无网络、无时钟、
    无随机；同一输入两次运行结果逐字节相同。
  * **门槛是数据不是代码**（plan/06 D4-1）：验收门槛从 ``manifest.bench.targets`` 读出，
    本模块不内联任何门槛数值（与 NFR-07 零政策字面量同一条纪律）。
  * **只读**：本模块不写任何文件、不改任何输入对象。

退出码（plan/03 §六）：0 = 三类基准达标；1 = 有指标未达标；2 = 用法/配置错误
（数据目录不可用、suite 名非法、manifest 缺门槛配置）。
"""

import os
import time
from decimal import Decimal

from . import __version__, jsonio
from .boundary import DELTA_VALUES, diff_boundary
from .calc import FORMULA_VARS, compute, _DECLARED_FACTOR_SOURCES
from .coordinates import Coordinate
from .decimals import as_decimal, scale_for, to_text
from .engine import collect_refs_by_op, validate
from .errors import (
    BenchConfigError,
    BoundaryError,
    FactorUnavailable,
    GhgError,
    MixedCoordinateError,
    QuotaUnavailable,
    RulesetNotEffective,
)
from .paths import find_data_dir
from .quality import (
    LEVEL_ERROR,
    LEVELS,
    TH_INTENSITY_MAX,
    TH_INTENSITY_MIN,
    TH_MAGNITUDE,
    TH_YOY,
    TYPE_INTENSITY,
    TYPE_MAGNITUDE,
    TYPE_UNIT,
    TYPE_YOY,
    run_checks,
)
from .quota import (
    METHOD_NONE,
    STATUS_NOT_APPLICABLE,
    compute_quota,
    quota_inputs_from_profile,
)
from .rules import (
    SCHEMA_RULESET,
    SCOPE_BLOCKS,
    SCOPE_CALC,
    SCOPE_CHECK,
    SCOPE_QUOTA,
    STATUS_INPUT_REQUIRED,
    STATUS_PENDING,
    STATUS_VERIFIED,
    RulesIndex,
    parse_payload_coordinate,
)
from .units import UnitTable, split_compound_unit

SCHEMA_BENCH = "ghg-benchreport/v1"

SUITE_RULES = "rules"
SUITE_FACTOR = "factor"
SUITE_CASES = "cases"
SUITES = (SUITE_RULES, SUITE_FACTOR, SUITE_CASES)

# 指标键（与 manifest.bench.targets 同名，便于逐项对门槛）
M_SELF_CONSISTENCY = "rules_self_consistency_rate"
M_FACTOR_UNIT = "factor_unit_consistency_rate"
M_CASE_HIT = "case_hit_rate"
M_CASE_FALSE_POSITIVE = "case_false_positive_rate"
M_RUNTIME = "runtime_seconds"

# 单位往返探针值（字符串，禁 float 进入计算路径）。这些是**测试探针**而非政策数值。
_PROBE_VALUES = ("1", "7", "123.456")

# 比率呈现小数位（与校核/配额层一致的口径）
RATE_PLACES = 6
_RATE_SCALE = scale_for(RATE_PLACES)

# 规则包内允许出现的 status 取值
_STATUS_VALUES = (STATUS_VERIFIED, STATUS_PENDING, STATUS_INPUT_REQUIRED)

# 校核层必须覆盖的四类检查（规则包 quality.rules[].type）
_QUALITY_TYPES = (TYPE_UNIT, TYPE_MAGNITUDE, TYPE_YOY, TYPE_INTENSITY)

# 校核层必须提供的四个阈值键
_QUALITY_THRESHOLD_KEYS = (TH_MAGNITUDE, TH_YOY, TH_INTENSITY_MIN, TH_INTENSITY_MAX)


# --------------------------------------------------------------------------
# 计数与呈现小工具
# --------------------------------------------------------------------------

class _Tally(object):
    """一个基准套件的逐项检查计数（全过 → 达成率 1）。"""

    def __init__(self, suite):
        self.suite = suite
        self.total = 0
        self.passed = 0
        self.failures = []

    def check(self, ok, label, detail=None):
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.failures.append({"check": label, "detail": detail})
        return bool(ok)

    def rate(self):
        if self.total == 0:
            return None
        return Decimal(self.passed) / Decimal(self.total)

    def as_dict(self):
        return {
            "suite": self.suite,
            "checks_total": self.total,
            "checks_passed": self.passed,
            "checks_failed": self.total - self.passed,
            "rate": _rate_text(self.rate()),
            "failures": self.failures,
        }


def _rate_text(value):
    """比率呈现（None → None）。"""
    if value is None:
        return None
    return to_text(as_decimal(value).quantize(_RATE_SCALE), RATE_PLACES)


def _top_key(path):
    """门控条目路径的顶层块名（``engine.coefficients.x`` → ``engine``）。"""
    return path.split(".", 1)[0].split("[", 1)[0]


# --------------------------------------------------------------------------
# 套件 1：规则自洽（FR-07.1）
# --------------------------------------------------------------------------

def _check_pack(tally, index, coord):
    """单个坐标规则包的自洽检查（逐项计入 tally）。"""
    key = coord.key
    pack = index.pack(coord)

    tally.check(pack.get("schema") == SCHEMA_RULESET, "schema %s" % key,
                "schema=%r" % pack.get("schema"))

    declared = pack.get("coordinate") or {}
    same_coord = (Coordinate(declared.get("standard"), declared.get("year"),
                             declared.get("industry")) == coord)
    tally.check(same_coord, "坐标声明 %s" % key, "声明=%r" % (declared,))

    # 表达式文法 + 引用可解析（var 落在引擎提供的变量集内；const 能解析到系数）
    formula = (pack.get("engine") or {}).get("formula") or {}
    expr = formula.get("expr")
    try:
        validate(expr)
        valid_expr = True
        detail = None
    except GhgError as exc:
        valid_expr = False
        detail = str(exc)
    tally.check(valid_expr, "表达式文法 %s" % key, detail)

    coefficients = (pack.get("engine") or {}).get("coefficients") or {}
    if valid_expr:
        refs = collect_refs_by_op(expr)
        bad_vars = [r for r in refs["var"] if r not in FORMULA_VARS]
        bad_consts = [r for r in refs["const"] if r not in coefficients]
        tally.check(not bad_vars and not bad_consts, "公式引用 %s" % key,
                    "未知变量=%s 未解析系数=%s" % (bad_vars, bad_consts))
    else:
        tally.check(False, "公式引用 %s" % key, "表达式非法，引用无法校验")

    # 系数状态自洽：verified 必须有值且带单位；非 verified 不得携带数值
    coef_ok = True
    coef_detail = []
    for name in sorted(coefficients):
        entry = coefficients[name] or {}
        status = entry.get("status")
        value = entry.get("value")
        if status not in _STATUS_VALUES:
            coef_ok = False
            coef_detail.append("%s:status=%r" % (name, status))
        if status == STATUS_VERIFIED:
            if value is None or not entry.get("unit"):
                coef_ok = False
                coef_detail.append("%s:verified 但缺值/单位" % name)
        elif value is not None:
            coef_ok = False
            coef_detail.append("%s:非 verified 却携带数值" % name)
    tally.check(coef_ok, "系数状态 %s" % key, "；".join(coef_detail))

    # 排放源条目完备：id 唯一、required 为布尔、delta 取值合法、status 合法
    sources = (pack.get("boundary") or {}).get("sources") or []
    src_ok = True
    src_detail = []
    ids = [s.get("id") for s in sources]
    if len(set(ids)) != len(ids):
        src_ok = False
        src_detail.append("id 重复")
    for src in sources:
        if not isinstance(src.get("required"), bool):
            src_ok = False
            src_detail.append("%s:required 非布尔" % src.get("id"))
        if src.get("delta_vs_2015") not in DELTA_VALUES:
            src_ok = False
            src_detail.append("%s:delta=%r" % (src.get("id"), src.get("delta_vs_2015")))
        if src.get("status") not in _STATUS_VALUES:
            src_ok = False
            src_detail.append("%s:status=%r" % (src.get("id"), src.get("status")))
    tally.check(src_ok and bool(sources), "排放源条目 %s" % key, "；".join(src_detail))

    # 门控作用域划分：各作用域 pending 的并集 == 整包 pending，且条目不越块
    whole = {item["path"] for item in index.gate_report(coord, scope=None)["pending"]}
    union = set()
    leak = []
    for scope in SCOPE_BLOCKS:
        blocks = SCOPE_BLOCKS[scope]
        for item in index.gate_report(coord, scope=scope)["pending"]:
            union.add(item["path"])
            if _top_key(item["path"]) not in blocks:
                leak.append("%s:%s" % (scope, item["path"]))
    tally.check(union == whole and not leak, "门控作用域划分 %s" % key,
                "并集差=%s 越块=%s" % (sorted(whole ^ union), leak))

    # 门控单点：effective_ruleset 与 gate_report 在每个作用域上判定一致
    single_ok = True
    single_detail = []
    for scope in (SCOPE_CALC, SCOPE_QUOTA, SCOPE_CHECK):
        try:
            index.effective_ruleset(coord, scope=scope)
            effective = True
        except RulesetNotEffective:
            effective = False
        if index.gate_report(coord, scope=scope)["effective"] != effective:
            single_ok = False
            single_detail.append(scope)
    tally.check(single_ok, "门控单点一致 %s" % key, "不一致作用域=%s" % single_detail)

    # 校核块：四类规则齐备、id 唯一、级别合法、四个阈值键在位
    quality = pack.get("quality") or {}
    rules = quality.get("rules") or []
    q_ok = True
    q_detail = []
    rule_ids = [r.get("id") for r in rules]
    if len(set(rule_ids)) != len(rule_ids):
        q_ok = False
        q_detail.append("规则 id 重复")
    if {r.get("type") for r in rules} != set(_QUALITY_TYPES):
        q_ok = False
        q_detail.append("四类检查未齐备")
    for rule in rules:
        if rule.get("level") not in LEVELS:
            q_ok = False
            q_detail.append("%s:level=%r" % (rule.get("id"), rule.get("level")))
    thresholds = quality.get("thresholds") or {}
    missing = [k for k in _QUALITY_THRESHOLD_KEYS if k not in thresholds]
    if missing:
        q_ok = False
        q_detail.append("缺阈值键=%s" % missing)
    for name in sorted(thresholds):
        entry = thresholds[name] or {}
        if entry.get("status") not in _STATUS_VALUES or not entry.get("unit"):
            q_ok = False
            q_detail.append("阈值 %s 状态/单位异常" % name)
    tally.check(q_ok, "校核块 %s" % key, "；".join(q_detail))

    # 配额块：方法学在允许集合内、参数条目状态合法
    quota = pack.get("quota") or {}
    allowed = list(quota.get("allowed_methods") or ())
    qu_ok = True
    qu_detail = []
    method = quota.get("method")
    if not method or (allowed and method not in allowed):
        qu_ok = False
        qu_detail.append("method=%r 不在 %s" % (method, allowed))
    for name in sorted(quota.get("params") or {}):
        entry = (quota["params"][name]) or {}
        if entry.get("status") not in _STATUS_VALUES:
            qu_ok = False
            qu_detail.append("参数 %s:status=%r" % (name, entry.get("status")))
    tally.check(qu_ok, "配额块 %s" % key, "；".join(qu_detail))

    # 报告块：通则编号 / 行业标签 / 免责声明三者齐备（报告头与 R3 依赖）
    report = pack.get("report") or {}
    r_ok = all(report.get(k) for k in ("standard_code", "industry_label", "disclaimer"))
    tally.check(r_ok, "报告块 %s" % key, "report=%s" % sorted(report))


def _standard_pairs(index):
    """全部有向通则对（旧 → 新 两向都算，交叉校验双向都成立）。"""
    standards = index.standards
    return [(standards[i], standards[j])
            for i in range(len(standards)) for j in range(len(standards)) if i != j]


def _check_diff_pairs(tally, index):
    """双标尺差异声明与结构交叉一致（跨版本混算拦截的另一面）。"""
    for old_key, new_key in _standard_pairs(index):
        for year in index.years:
            for industry in index.industries:
                old = index.resolve(old_key, year, industry)
                new = index.resolve(new_key, year, industry)
                label = "双标尺 %s→%s" % (old.key, new.key)
                try:
                    diff = diff_boundary(old, new, index)
                except GhgError as exc:
                    tally.check(False, label, str(exc))
                    continue
                covered = (diff["added_count"] + diff["removed_count"]
                           + diff["adjusted_count"] + diff["unchanged_count"])
                old_ids = {s["id"] for s in index.pack(old)["boundary"]["sources"]}
                new_ids = {s["id"] for s in index.pack(new)["boundary"]["sources"]}
                expected = len(old_ids | new_ids)
                tally.check(covered == expected, label,
                            "覆盖 %d != 应有 %d" % (covered, expected))


def suite_rules(index):
    tally = _Tally(SUITE_RULES)
    for coord in index.coordinates():
        _check_pack(tally, index, coord)
    _check_diff_pairs(tally, index)
    return tally


# --------------------------------------------------------------------------
# 套件 2：因子与单位一致（FR-07.2）
# --------------------------------------------------------------------------

def _factor_units_of(pack):
    """规则包内参与**换算**的单位（因子单位 + 系数单位）。"""
    out = []
    defaults = (pack.get("factors") or {}).get("industry_default_values") or {}
    entry = defaults.get("default_factor")
    if isinstance(entry, dict) and entry.get("unit"):
        out.append(("factors.default_factor", entry["unit"]))
    for name in sorted(defaults.get("by_category") or {}):
        item = defaults["by_category"][name] or {}
        if item.get("unit"):
            out.append(("factors.by_category.%s" % name, item["unit"]))
    for name in sorted((pack.get("engine") or {}).get("coefficients") or {}):
        item = pack["engine"]["coefficients"][name] or {}
        if item.get("unit"):
            out.append(("engine.coefficients.%s" % name, item["unit"]))
    return out


def suite_factor(index, units):
    tally = _Tally(SUITE_FACTOR)

    # 1) 单位换算全量往返（同量纲：unit → base → unit 必须回到原值）
    unit_names = units.unit_list()
    for unit in unit_names:
        base = units.base_of(unit)
        for probe in _PROBE_VALUES:
            label = "单位往返 %s→%s→%s" % (unit, base, unit)
            try:
                back = units.convert(units.convert(probe, unit, base), base, unit)
                ok = as_decimal(back) == as_decimal(probe)
                tally.check(ok, label, "回值=%s（原 %s）" % (back, probe))
            except GhgError as exc:
                tally.check(False, label, str(exc))

    # 2) 基准单位换算因子恒为 1（表内自洽）
    for dimension in sorted(units.dimensions()):
        base = units.base_of(next(u for u in unit_names
                                  if units.dimension_of(u) == dimension))
        tally.check(units.scale(base) == Decimal(1), "基准单位因子 %s" % dimension,
                    "scale=%s" % units.scale(base))

    # 3) 跨量纲换算必须被拒（防 t 换 MWh 这类量纲混用）
    dims = sorted(units.dimensions())
    for i in range(len(dims)):
        for j in range(len(dims)):
            if i == j:
                continue
            from_unit = next(u for u in unit_names if units.dimension_of(u) == dims[i])
            to_unit = next(u for u in unit_names if units.dimension_of(u) == dims[j])
            label = "跨量纲拒绝 %s→%s" % (from_unit, to_unit)
            try:
                units.convert("1", from_unit, to_unit)
                tally.check(False, label, "未拒绝")
            except GhgError:
                tally.check(True, label)

    # 4) 因子/系数单位复合拆分可解析（分母须在单位表内，分子为排放单位）
    seen = set()
    for coord in index.coordinates():
        for where, unit in _factor_units_of(index.pack(coord)):
            if (where, unit) in seen:
                continue
            seen.add((where, unit))
            label = "因子单位拆分 %s=%s" % (where, unit)
            numerator, denominator = split_compound_unit(unit)
            if denominator is None:
                ok = units.known(unit) or numerator == "tCO2e"
                tally.check(ok, label, "单一单位不在单位表内")
                continue
            ok = (numerator == "tCO2e" or units.known(numerator)) and units.known(denominator)
            tally.check(ok, label, "分子=%r 分母=%r" % (numerator, denominator))

    # 5) 同源因子跨年不漂移（同一通则 + 行业，缺省因子数值与单位逐年一致）
    drift = {}
    for coord in index.coordinates():
        entry = ((index.pack(coord).get("factors") or {})
                 .get("industry_default_values") or {}).get("default_factor") or {}
        drift.setdefault((coord.standard, coord.industry), {})[coord.year] = (
            entry.get("value"), entry.get("unit"))
    for group in sorted(drift):
        values = {year: drift[group][year] for year in sorted(drift[group])}
        tally.check(len(set(values.values())) == 1,
                    "同源因子跨年一致 %s/%s" % group,
                    "逐年取值=%s" % values)

    # 6) 跨通则同行业同年因子一致（缺省因子取自行业指南附录 A，与通则版本无关）
    cross = {}
    for coord in index.coordinates():
        entry = ((index.pack(coord).get("factors") or {})
                 .get("industry_default_values") or {}).get("default_factor") or {}
        cross.setdefault((coord.year, coord.industry), {})[coord.standard] = (
            entry.get("value"), entry.get("unit"))
    for group in sorted(cross):
        values = {std: cross[group][std] for std in sorted(cross[group])}
        tally.check(len(set(values.values())) == 1,
                    "跨通则因子一致 %s/%s" % group,
                    "逐通则取值=%s" % values)

    # 7) 因子优先级：全坐标一致，且覆盖代码声明的合法来源白名单
    priorities = {tuple((index.pack(c).get("factors") or {}).get("priority") or ())
                  for c in index.coordinates()}
    tally.check(len(priorities) == 1, "因子优先级一致", "取值集=%s" % sorted(priorities))
    if len(priorities) == 1:
        priority = priorities.pop()
        missing = [s for s in _DECLARED_FACTOR_SOURCES if s not in priority]
        tally.check(not missing, "因子优先级覆盖白名单", "缺=%s" % missing)

    # 8) 按类别覆盖的键须落在该包排放源类别集合内（防"孤儿类别"覆盖）
    for coord in index.coordinates():
        pack = index.pack(coord)
        by_category = ((pack.get("factors") or {}).get("industry_default_values") or {}) \
            .get("by_category") or {}
        if not by_category:
            continue
        categories = {s.get("category") for s in pack["boundary"]["sources"]}
        orphan = [k for k in sorted(by_category) if k not in categories]
        tally.check(not orphan, "类别覆盖键 %s" % coord.key, "孤儿类别=%s" % orphan)

    return tally


# --------------------------------------------------------------------------
# 套件 3：边界与异常用例（FR-07.3）
# --------------------------------------------------------------------------

def _truth_path(data_dir, rel):
    return os.path.join(data_dir, "truth", rel)


def _case_file(data_dir, truth, case):
    """用例的档案路径：显式 ``file`` 优先；否则按 ``coordinate`` 在档案目录里定位。

    后者服务于"机制演示"型用例（如 ``quota_method_none`` 只声明坐标，不另产档案）——
    档案名由生成器决定，基准层不内联命名规则，故直接扫 ``truth/profiles/`` 读坐标比对。
    """
    if case.get("file"):
        return case["file"]
    coord_key = case.get("coordinate")
    if not coord_key:
        return None
    profiles_dir = os.path.join(data_dir, "truth", "profiles")
    if not os.path.isdir(profiles_dir):
        return None
    for name in sorted(os.listdir(profiles_dir)):
        if not name.endswith(".json"):
            continue
        rel = "profiles/%s" % name
        payload = jsonio.load(os.path.join(profiles_dir, name))
        coord = payload.get("coordinate")
        if isinstance(coord, dict):
            key = "%s/%s/%s" % (coord.get("standard"), coord.get("year"),
                                coord.get("industry"))
            if key == coord_key:
                return rel
    return None


def _calc_of(index, units, payload):
    coord = parse_payload_coordinate(payload, index=index)
    return coord, compute(payload, coord, index.effective_ruleset(coord, scope=SCOPE_CALC),
                          units)


def _quality_case(index, units, data_dir, case):
    payload = jsonio.load(_truth_path(data_dir, case["file"]))
    coord, calc = _calc_of(index, units, payload)
    baseline = None
    if case.get("baseline_file"):
        base_payload = jsonio.load(_truth_path(data_dir, case["baseline_file"]))
        base_coord, baseline = _calc_of(index, units, base_payload)
        del base_coord
    report = run_checks(payload, calc, coord,
                        index.effective_ruleset(coord, scope=SCOPE_CHECK),
                        units=units, baseline=baseline)
    hits = [i for i in report["issues"] if i["rule_id"] == case["expected_rule"]]
    if not hits:
        return False, "未命中 %s" % case["expected_rule"]
    hit = hits[0]
    if hit["level"] != case["expected_level"]:
        return False, "级别 %s != 期望 %s" % (hit["level"], case["expected_level"])
    want_source = case.get("expected_source_id")
    if want_source and hit["source_id"] != want_source:
        return False, "源 %s != 期望 %s" % (hit["source_id"], want_source)
    return True, "%s@%s" % (hit["rule_id"], hit["level"])


def _quota_case(index, units, data_dir, case):
    payload = jsonio.load(_truth_path(data_dir, case["file"]))
    coord, calc = _calc_of(index, units, payload)
    params = quota_inputs_from_profile(payload)
    for key in ("benchmark_value", "correction_factor"):
        if key in case:
            params[key] = case[key]
    pack = index.effective_ruleset(coord, scope=SCOPE_QUOTA)

    expected = case.get("expected")
    if expected == "error_quota_unavailable":
        try:
            compute_quota(pack, coord, calc["total_raw"], params={})
            return False, "未抛出 QuotaUnavailable（不得静默取 0）"
        except QuotaUnavailable:
            return True, "QuotaUnavailable"
    if expected == "not_applicable":
        patched = jsonio.loads(jsonio.dumps(pack))
        patched["quota"]["method"] = METHOD_NONE
        report = compute_quota(patched, coord, calc["total_raw"], params={})
        if report["status"] != STATUS_NOT_APPLICABLE or report["allocated"] is not None:
            return False, "status=%s allocated=%r" % (report["status"], report["allocated"])
        return True, "not_applicable"
    if isinstance(expected, dict):
        report = compute_quota(pack, coord, calc["total_raw"], params=params)
        if report["method"] != case.get("method"):
            return False, "方法学 %s != %s" % (report["method"], case.get("method"))
        for field in sorted(expected):
            if as_decimal(report[field + "_raw"]) != as_decimal(expected[field]):
                return False, "%s: %s != %s" % (field, report[field + "_raw"],
                                                expected[field])
        return True, "逐字段对账通过"
    return False, "未知配额用例期望：%r" % (expected,)


def _error_case(index, units, data_dir, case):
    """失败路径用例：期望抛出指定异常类型。"""
    expected = case["expected"]
    payload = jsonio.load(_truth_path(data_dir, case["file"]))
    if expected == "error_mixed_coordinates":
        try:
            parse_payload_coordinate(payload, index=index)
            return False, "未拦截跨坐标混算"
        except MixedCoordinateError:
            return True, "MixedCoordinateError"
    if expected == "error_factor_unavailable":
        coord = parse_payload_coordinate(payload, index=index)
        pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
        stripped = {k: v for k, v in pack.items() if k != "factors"}
        try:
            compute(payload, coord, stripped, units)
            return False, "未抛出 FactorUnavailable"
        except FactorUnavailable:
            return True, "FactorUnavailable"
    if expected in ("error_missing_required_source", "error_missing_activity_value"):
        try:
            _calc_of(index, units, payload)
            return False, "未抛出 BoundaryError"
        except BoundaryError:
            return True, "BoundaryError"
    return False, "未知失败用例期望：%r" % (expected,)


def _run_case(index, units, data_dir, case):
    if "expected_rule" in case:
        return _quality_case(index, units, data_dir, case)
    if case.get("expected") in ("error_quota_unavailable", "not_applicable") \
            or isinstance(case.get("expected"), dict):
        return _quota_case(index, units, data_dir, case)
    return _error_case(index, units, data_dir, case)


def _safe(runner, *args):
    """跑一个检查项，把引擎异常折算成"该项未过"。

    基准的职责是判定"当前仓库状态是否健康"：若规则包损坏到求值即抛
    :class:`GhgError`（如公式引用不存在的系数），这**本身就是基准失败**——
    必须计入"未过"并以退出码 1 报出，而不是让异常冒泡成退出码 2（那会把
    "数据坏了"误报成"用法错了"）。
    """
    try:
        return runner(*args)
    except GhgError as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)


def _guarded_suite(name, suite_fn, *args):
    """跑一个套件；异常折算成"该套件整体未过"（同 :func:`_safe` 的理由）。"""
    try:
        return suite_fn(*args)
    except GhgError as exc:
        tally = _Tally(name)
        tally.check(False, "套件 %s 中断" % name, "%s: %s" % (type(exc).__name__, exc))
        return tally


def _resolve_case_file(data_dir, truth, case):
    """返回补全 ``file`` 的用例副本（缺档案且无法定位 → 原样返回，由用例检查报错）。"""
    if case.get("file") or not case.get("coordinate"):
        return case
    rel = _case_file(data_dir, truth, case)
    if rel is None:
        return case
    resolved = dict(case)
    resolved["file"] = rel
    return resolved


def _profile_checks(tally, index, units, truth, data_dir):
    """逐档案真值双路对账（引擎路径 vs 生成器直接算式）。"""
    for name in sorted(truth["profiles"]):
        expected = truth["profiles"][name]
        payload = jsonio.load(_truth_path(data_dir, expected["file"]))
        try:
            coord, calc = _calc_of(index, units, payload)
        except GhgError as exc:
            tally.check(False, "档案对账 %s" % name, str(exc))
            continue
        del coord
        if calc["total_raw"] != expected["total"]:
            tally.check(False, "档案对账 %s" % name,
                        "汇总 %s != 真值 %s" % (calc["total_raw"], expected["total"]))
            continue
        by_id = {line["source_id"]: line for line in calc["lines"]}
        if sorted(by_id) != sorted(line["source_id"] for line in expected["lines"]):
            tally.check(False, "档案对账 %s" % name, "纳入源集合不一致")
            continue
        mismatched = []
        for exp_line in expected["lines"]:
            got = by_id[exp_line["source_id"]]
            if got["emission_raw"] != exp_line["emission"]:
                mismatched.append(exp_line["source_id"])
        tally.check(not mismatched, "档案对账 %s" % name, "逐源不符=%s" % mismatched)


def _quality_report(index, units, data_dir, rel, baseline_rel=None):
    """跑一个档案的四类校核（``baseline_rel`` 给出时同时算同比基线）。"""
    payload = jsonio.load(_truth_path(data_dir, rel))
    coord, calc = _calc_of(index, units, payload)
    baseline = None
    if baseline_rel:
        base_payload = jsonio.load(_truth_path(data_dir, baseline_rel))
        _bc, baseline = _calc_of(index, units, base_payload)
    return run_checks(payload, calc, coord,
                      index.effective_ruleset(coord, scope=SCOPE_CHECK),
                      units=units, baseline=baseline)


def _control_checks(tally, index, units, truth, data_dir):
    """误报对照：干净档案必须零命中（FR-07.3 误报率的分母与分子）。

    返回 ``(对照档案数, 误报数)``。对照集由真值库 ``controls`` 显式声明
    （数据驱动，不在基准代码里内联档案名）。
    """
    controls = truth.get("controls") or {}
    clean = list(controls.get("quality_clean") or [])
    yoy = controls.get("quality_yoy_clean")
    if yoy:
        clean.append(yoy)

    total = 0
    false_positives = 0
    for item in clean:
        total += 1
        label = item["file"]
        try:
            report = _quality_report(index, units, data_dir, item["file"],
                                     item.get("baseline_file"))
        except GhgError as exc:
            false_positives += 1
            tally.check(False, "误报对照 %s" % label, str(exc))
            continue
        if report["issue_count"]:
            false_positives += 1
            tally.check(False, "误报对照 %s" % label,
                        "命中 %s" % [i["rule_id"] for i in report["issues"]])
        else:
            tally.check(True, "误报对照 %s" % label)
    return total, false_positives


def _grading_checks(tally, index, units, truth, data_dir):
    """分级降级：可换算/可解释的档案只报 warning，不得升为 error（plan/06 D3-4）。"""
    for item in (truth.get("controls") or {}).get("quality_non_error") or []:
        label = item["file"]
        try:
            report = _quality_report(index, units, data_dir, label,
                                     item.get("baseline_file"))
        except GhgError as exc:
            tally.check(False, "分级降级 %s" % label, str(exc))
            continue
        ok = report["issue_count"] > 0 and report["counts"].get(LEVEL_ERROR, 0) == 0
        tally.check(ok, "分级降级 %s" % label,
                    "命中 %d，其中 error %d"
                    % (report["issue_count"], report["counts"].get(LEVEL_ERROR, 0)))


def suite_cases(index, units, truth, data_dir):
    """边界与异常用例套件（FR-07.3）。

    返回 ``(tally, stats)``：``tally`` 汇总**全部**检查（用例 + 逐档案对账 + 误报对照 +
    分级降级）用于套件达标判定；``stats`` 单列命中率与误报率的分子分母，使指标语义与
    README 基准表一致（命中率只看用例；误报率只看干净对照档案）。
    """
    tally = _Tally(SUITE_CASES)
    cases = truth.get("cases") or {}
    hit = 0
    for key in sorted(cases):
        ok, detail = _safe(_run_case, index, units, data_dir,
                           _resolve_case_file(data_dir, truth, cases[key]))
        tally.check(ok, "异常用例 %s" % key, detail)
        if ok:
            hit += 1
    _profile_checks(tally, index, units, truth, data_dir)
    controls_total, false_positives = _control_checks(tally, index, units, truth, data_dir)
    _grading_checks(tally, index, units, truth, data_dir)
    stats = {
        "cases_total": len(cases),
        "cases_hit": hit,
        "controls_total": controls_total,
        "false_positives": false_positives,
    }
    return tally, stats


# --------------------------------------------------------------------------
# 编排：三类基准 + 门槛判定
# --------------------------------------------------------------------------

def _compare(metric, value, target):
    """按指标语义比较（比率类为下限，运行时长类为上限）。"""
    if value is None:
        return False
    if metric == M_RUNTIME:
        return as_decimal(value) <= as_decimal(target)
    return as_decimal(value) >= as_decimal(target)


def _verdicts(metrics, targets):
    """逐指标对门槛判定。

    **只判定本次实际测到的指标**（``metrics`` 里有的）：``--suite`` 只跑一类时，未运行的
    套件对应指标不参与判定——否则会把"没测"误报成"未达标"。全量运行（缺省）时五项目标
    全部参与，与 M4 DoD 一致。
    """
    out = []
    for metric in sorted(targets):
        if metric not in metrics:
            continue
        value = metrics[metric]
        target = targets[metric]
        out.append({
            "metric": metric,
            "value": None if value is None else _rate_text(value),
            "target": _rate_text(target),
            "comparator": "le" if metric == M_RUNTIME else "ge",
            "met": _compare(metric, value, target),
        })
    return out


def run_bench(data_dir=None, suites=None, index=None, units=None, truth=None):
    """跑全部（或指定）基准套件，返回 :class:`BenchReport` 结构。

    参数
    ----
    data_dir : 数据目录（缺省自动定位）
    suites   : 套件名序列（缺省全部三类）；非法名抛 :class:`BenchConfigError`
    index / units / truth : 可注入（测试用），缺省各自从 ``data_dir`` 加载

    返回结构含逐套件计数、四项指标、门槛判定与运行时长；**只读**，不写任何文件。
    """
    selected = list(suites or SUITES)
    unknown = [s for s in selected if s not in SUITES]
    if unknown:
        raise BenchConfigError("未知基准套件：%s（可用：%s）"
                               % ("、".join(unknown), "、".join(SUITES)))
    if not selected:
        raise BenchConfigError("基准套件为空（可用：%s）" % "、".join(SUITES))

    resolved = find_data_dir(data_dir)
    if index is None:
        index = RulesIndex.load(resolved)
    if units is None:
        units = UnitTable.load(resolved)
    if truth is None:
        truth = jsonio.load(os.path.join(resolved, "truth", "expected.json"))
    targets = index.bench_targets()

    started = time.perf_counter()

    tallies = {}
    case_stats = {}
    if SUITE_RULES in selected:
        tallies[SUITE_RULES] = _guarded_suite(SUITE_RULES, suite_rules, index)
    if SUITE_FACTOR in selected:
        tallies[SUITE_FACTOR] = _guarded_suite(SUITE_FACTOR, suite_factor, index, units)
    if SUITE_CASES in selected:
        try:
            tally, case_stats = suite_cases(index, units, truth, resolved)
        except GhgError as exc:
            tally = _Tally(SUITE_CASES)
            tally.check(False, "套件 %s 中断" % SUITE_CASES,
                        "%s: %s" % (type(exc).__name__, exc))
        tallies[SUITE_CASES] = tally

    metrics = {}
    if SUITE_RULES in tallies:
        metrics[M_SELF_CONSISTENCY] = tallies[SUITE_RULES].rate()
    if SUITE_FACTOR in tallies:
        metrics[M_FACTOR_UNIT] = tallies[SUITE_FACTOR].rate()
    if SUITE_CASES in tallies:
        total = case_stats["cases_total"]
        metrics[M_CASE_HIT] = (Decimal(case_stats["cases_hit"]) / Decimal(total)
                               if total else None)
        controls = case_stats["controls_total"]
        metrics[M_CASE_FALSE_POSITIVE] = (
            Decimal(case_stats["false_positives"]) / Decimal(controls)
            if controls else None)

    elapsed = Decimal(repr(time.perf_counter() - started))
    if all(suite in selected for suite in SUITES):
        metrics[M_RUNTIME] = elapsed

    verdicts = _verdicts(metrics, targets)
    ok = all(v["met"] for v in verdicts)

    return {
        "schema": SCHEMA_BENCH,
        "tool_version": __version__,
        "suites_run": selected,
        "suites": {name: tallies[name].as_dict() for name in sorted(tallies)},
        "cases": case_stats,
        "metrics": {k: _rate_text(v) for k, v in sorted(metrics.items())},
        "targets": {k: _rate_text(v) for k, v in sorted(targets.items())},
        "verdicts": verdicts,
        "ok": ok,
    }


def render_bench_text(report):
    """人类可读的基准输出（CLI 用）。"""
    full = list(report["suites_run"]) == list(SUITES)
    lines = ["内置离线基准（FR-07；工具版本 %s%s）"
             % (report["tool_version"], "" if full else "；本次仅跑 %s"
                % "、".join(report["suites_run"]))]
    for name in report["suites_run"]:
        suite = report["suites"][name]
        lines.append("  [套件] %s：%d/%d 通过（达成率 %s）"
                     % (name, suite["checks_passed"], suite["checks_total"],
                        suite["rate"]))
        for failure in suite["failures"][:5]:
            lines.append("       - 未过：%s（%s）" % (failure["check"], failure["detail"]))
        extra = len(suite["failures"]) - 5
        if extra > 0:
            lines.append("       … 其余 %d 项见 --json" % extra)
    lines.append("  指标：")
    for verdict in report["verdicts"]:
        mark = "达标" if verdict["met"] else "未达标"
        operator = "<=" if verdict["comparator"] == "le" else ">="
        lines.append("    [%s] %s = %s（门槛 %s %s）"
                     % (mark, verdict["metric"], verdict["value"],
                        operator, verdict["target"]))
    if report["cases"]:
        lines.append("  异常用例命中：%d/%d；干净对照档案 %d 个，误报 %d 个"
                     % (report["cases"]["cases_hit"], report["cases"]["cases_total"],
                        report["cases"]["controls_total"],
                        report["cases"]["false_positives"]))
    scope = "三类基准" if full else "本次套件"
    lines.append("  结论：%s" % ("%s全部达标" % scope if report["ok"]
                                else "%s存在未达标指标" % scope))
    return "\n".join(lines)
