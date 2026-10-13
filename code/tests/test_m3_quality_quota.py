"""M3 校核层与配额试算测试（FR-04 / FR-05）。

对账纪律（沿用 M1/M2 双路独立实现）：
  * 配额真值由 ``tools/gen_synthetic.py`` 按方案原文公式**直接算式**算出并落盘；
  * 引擎 ``ghg.quota.compute_quota`` 走**方法学分支**路径；
  两者对同一算例必须逐字段一致。

校核层三条硬约束的测试锚点：
  * **只读**：``run_checks`` 前后 ``profile`` / ``calc`` 逐字节不变（FR-04.4）；
  * **阈值全部取自规则包**：改规则包阈值即改变结论（证明代码零阈值字面量，NFR-07）；
  * **分级正确**：故意错配/量级/跨年/比强度异常档案各自命中且级别符合规则包声明。
"""

import json
import os

import pytest

from ghg import jsonio
from ghg.calc import compute
from ghg.coordinates import parse_coordinate
from ghg.decimals import as_decimal
from ghg.errors import InputError, QuotaUnavailable
from ghg.quality import (
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_WARNING,
    TYPE_INTENSITY,
    TYPE_MAGNITUDE,
    TYPE_UNIT,
    TYPE_YOY,
    render_quality_text,
    run_checks,
)
from ghg.quota import (
    STATUS_NOT_APPLICABLE,
    STATUS_OK,
    compute_quota,
    quota_inputs_from_profile,
    render_quota_text,
)
from ghg.rules import SCOPE_CALC, SCOPE_CHECK, SCOPE_QUOTA, RulesIndex
from ghg.units import UnitTable


@pytest.fixture(scope="session")
def truth(data_dir):
    return jsonio.load(os.path.join(data_dir, "truth", "expected.json"))


def _load(data_dir, truth, name):
    return jsonio.load(os.path.join(data_dir, "truth", truth["profiles"][name]["file"]))


def _case_profile(data_dir, truth, key):
    return jsonio.load(os.path.join(data_dir, "truth", truth["cases"][key]["file"]))


def _calc_of(data_dir, profile):
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
    return index, coord, units, compute(profile, coord, pack, units)


def _check(data_dir, profile, baseline=None):
    index, coord, units, calc = _calc_of(data_dir, profile)
    pack = index.effective_ruleset(coord, scope=SCOPE_CHECK)
    return run_checks(profile, calc, coord, pack, units=units, baseline=baseline)


def _issues(report, rule_id):
    return [i for i in report["issues"] if i["rule_id"] == rule_id]


# ---------- 门控：校核与配额路径 M3 起可通过 ----------

def test_quality_and_quota_paths_are_effective(rules_index):
    """M3：校核阈值已定值、配额参数已就位 → 两条路径门控全部放行。"""
    coords = rules_index.coordinates()
    assert all(rules_index.gate_report(c, scope=SCOPE_CHECK)["effective"] for c in coords)
    assert all(rules_index.gate_report(c, scope=SCOPE_QUOTA)["effective"] for c in coords)


def test_quality_thresholds_are_verified_with_values(rules_index):
    """校核阈值必须已核对且有值（M3 定值）；否则校核层不得报结论。"""
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    thresholds = rules_index.pack(coord)["quality"]["thresholds"]
    assert thresholds
    for key, entry in thresholds.items():
        assert entry["status"] == "verified", "阈值 %s 未核对" % key
        assert entry["value"] is not None, "阈值 %s 无数值" % key
        assert entry.get("unit")


def test_check_gate_returns_gate_exit_when_quality_pending(rules_index):
    """plan/04 §4.3：quality 全 pending 时 `check` 必须由门控返回退出码 1（不静默通过）。

    把 quality 块改回 pending → 校核路径门控拦截（RulesetNotEffective，退出码 1）；
    核算路径不受牵连（分作用域）。
    """
    from ghg.errors import EXIT_GATE, RulesetNotEffective
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    pack = jsonio.loads(jsonio.dumps(rules_index.pack(coord)))
    pack["quality"]["thresholds"]["magnitude"]["status"] = "pending"
    pack["quality"]["thresholds"]["magnitude"]["value"] = None
    index = RulesIndex(rules_index.data_dir, rules_index._manifest, rules_index.base_dir)
    index._cache[coord.key] = (rules_index._by_key[coord.key], pack)
    with pytest.raises(RulesetNotEffective) as exc_info:
        index.effective_ruleset(coord, scope=SCOPE_CHECK)
    assert exc_info.value.exit_code == EXIT_GATE
    # 分作用域：核算路径不受 quality pending 牵连
    assert index.gate_report(coord, scope=SCOPE_CALC)["effective"] is True


# ---------- 四类检查：命中与分级 ----------

def test_clean_profile_produces_no_issues(data_dir, truth):
    """误报率锚点：常规档案（含产量）在四类检查上零命中。"""
    profile = _load(data_dir, truth, "steel-2024")
    report = _check(data_dir, profile)
    assert report["issue_count"] == 0, report["issues"]
    assert set(report["rules_executed"]) == {"Q-UNIT-01", "Q-MAG-01", "Q-INT-01"}


def test_bad_unit_case_hits_error(data_dir, truth):
    """故意错配单位（未知单位）→ Q-UNIT-01 命中且级别为 error。"""
    case = truth["cases"]["quality_bad_unit"]
    profile = _case_profile(data_dir, truth, "quality_bad_unit")
    report = _check(data_dir, profile)
    hits = _issues(report, case["expected_rule"])
    assert hits, "单位一致性检查未命中"
    assert hits[0]["level"] == case["expected_level"]
    assert hits[0]["source_id"] == case["expected_source_id"]
    assert report["counts"][LEVEL_ERROR] >= 1


def test_magnitude_outlier_case_hits_warning(data_dir, truth):
    case = truth["cases"]["quality_magnitude_outlier"]
    profile = _case_profile(data_dir, truth, "quality_magnitude_outlier")
    report = _check(data_dir, profile)
    hits = _issues(report, case["expected_rule"])
    assert hits, "量级检查未命中"
    assert hits[0]["level"] == case["expected_level"]
    assert hits[0]["source_id"] == case["expected_source_id"]


def test_yoy_clean_case_has_no_yoy_hit(data_dir, truth):
    """误报对照：同比变化率为 0 的档案不得命中跨年突变检查。"""
    case = truth["cases"]["quality_yoy_jump"]
    clean = jsonio.load(os.path.join(data_dir, "truth", case["clean_file"]))
    baseline = jsonio.load(os.path.join(data_dir, "truth", case["baseline_file"]))
    _, _, _, base_calc = _calc_of(data_dir, baseline)
    report = _check(data_dir, clean, baseline=base_calc)
    assert _issues(report, case["expected_rule"]) == []
    assert "Q-YOY-01" in report["rules_executed"], "yoy 检查应已执行（基线已提供）"


def test_yoy_jump_case_hits_warning(data_dir, truth):
    case = truth["cases"]["quality_yoy_jump"]
    jump = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    baseline = jsonio.load(os.path.join(data_dir, "truth", case["baseline_file"]))
    _, _, _, base_calc = _calc_of(data_dir, baseline)
    report = _check(data_dir, jump, baseline=base_calc)
    hits = _issues(report, case["expected_rule"])
    assert hits, "跨年突变检查未命中"
    assert hits[0]["level"] == case["expected_level"]
    assert hits[0]["source_id"] == case["expected_source_id"]


def test_intensity_out_of_range_hits_info(data_dir, truth):
    case = truth["cases"]["quality_intensity_out_of_range"]
    profile = _case_profile(data_dir, truth, "quality_intensity_out_of_range")
    report = _check(data_dir, profile)
    hits = _issues(report, case["expected_rule"])
    assert hits, "比强度检查未命中"
    assert hits[0]["level"] == case["expected_level"]
    assert report["counts"][LEVEL_INFO] >= 1


def test_yoy_skipped_without_baseline(data_dir, truth):
    """未提供上一年度基线时 yoy 检查**跳过并说明原因**，不得静默通过。"""
    profile = _load(data_dir, truth, "steel-2024")
    report = _check(data_dir, profile)
    skipped = {s["type"]: s for s in report["rules_skipped"]}
    assert TYPE_YOY in skipped
    assert skipped[TYPE_YOY]["reason"]
    assert "Q-YOY-01" not in report["rules_executed"]


# ---------- 只读层（FR-04.4）----------

def test_run_checks_does_not_mutate_inputs(data_dir, truth):
    """校核层只读：profile / calc 在 run_checks 前后逐字节不变。"""
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, units, calc = _calc_of(data_dir, profile)
    pack = index.effective_ruleset(coord, scope=SCOPE_CHECK)
    before_profile = jsonio.dumps(profile)
    before_calc = jsonio.dumps(calc)
    run_checks(profile, calc, coord, pack, units=units)
    assert jsonio.dumps(profile) == before_profile
    assert jsonio.dumps(calc) == before_calc


# ---------- 阈值来自规则包（代码零阈值字面量）----------

def test_thresholds_come_from_ruleset(data_dir, truth):
    """把规则包量级阈值调到不可能超过 → 量级异常档案不再命中（证明阈值真取自规则包）。"""
    case = truth["cases"]["quality_magnitude_outlier"]
    profile = _case_profile(data_dir, truth, "quality_magnitude_outlier")
    index, coord, units, calc = _calc_of(data_dir, profile)
    pack = index.effective_ruleset(coord, scope=SCOPE_CHECK)
    patched = jsonio.loads(jsonio.dumps(pack))
    patched["quality"]["thresholds"]["magnitude"]["value"] = as_decimal("1.0")
    new_index = RulesIndex(index.data_dir, index._manifest, index.base_dir)
    new_index._cache[coord.key] = (index._by_key[coord.key], patched)
    report = run_checks(profile, calc, coord, patched, units=units)
    assert _issues(report, case["expected_rule"]) == []


def test_pending_threshold_skips_check_not_silently_passes(data_dir, truth):
    """阈值未核对（pending）→ 该检查跳过并说明原因，绝不静默按"通过"处理。"""
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, units, calc = _calc_of(data_dir, profile)
    pack = index.effective_ruleset(coord, scope=SCOPE_CHECK)
    patched = jsonio.loads(jsonio.dumps(pack))
    patched["quality"]["thresholds"]["magnitude"]["status"] = "pending"
    patched["quality"]["thresholds"]["magnitude"]["value"] = None
    report = run_checks(profile, calc, coord, patched, units=units)
    skipped = {s["type"] for s in report["rules_skipped"]}
    assert TYPE_MAGNITUDE in skipped
    assert "Q-MAG-01" not in report["rules_executed"]


def test_issues_carry_clause_and_advice(data_dir, truth):
    """FR-04.3：每条问题挂规则依据 id / 条款 / 建议。"""
    profile = _case_profile(data_dir, truth, "quality_bad_unit")
    report = _check(data_dir, profile)
    assert report["issues"]
    for issue in report["issues"]:
        assert issue["rule_id"]
        assert issue["level"] in (LEVEL_ERROR, LEVEL_WARNING, LEVEL_INFO)
        assert issue["clause"] and issue["clause"]["article"]
        assert issue["advice"]
        assert issue["message"]


def test_render_quality_text_lists_counts_and_issues(data_dir, truth):
    profile = _case_profile(data_dir, truth, "quality_bad_unit")
    report = _check(data_dir, profile)
    text = render_quality_text(report)
    assert "问题计数" in text
    assert "Q-UNIT-01" in text
    assert "依据" in text


# ---------- 配额试算（FR-05）----------

def _quota(data_dir, profile, params):
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    calc = compute(profile, coord, index.effective_ruleset(coord, scope=SCOPE_CALC), units)
    pack = index.effective_ruleset(coord, scope=SCOPE_QUOTA)
    merged = quota_inputs_from_profile(profile)
    merged.update(params)
    return compute_quota(pack, coord, calc["total_raw"], params=merged)


def test_quota_benchmark_matches_truth(data_dir, truth):
    """发电基准法：与真值库（方案原文公式直接算式）逐字段对账。"""
    case = truth["cases"]["quota_benchmark"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    report = _quota(data_dir, profile, {"correction_factor": case["correction_factor"]})
    assert report["method"] == case["method"]
    assert report["status"] == STATUS_OK
    for key in ("actual", "allocated", "gap", "gap_ratio"):
        assert as_decimal(report[key + "_raw"]) == as_decimal(case["expected"][key]), \
            "配额 %s 不一致：%s != %s" % (key, report[key + "_raw"], case["expected"][key])


def test_quota_intensity_coefficient_matches_truth(data_dir, truth):
    """强度系数法：α 由偏离度经规则包分段常数推出，与真值库对账。"""
    case = truth["cases"]["quota_intensity_coefficient"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    report = _quota(data_dir, profile, {"benchmark_value": case["benchmark_value"]})
    assert report["method"] == case["method"]
    for key in ("actual", "allocated", "gap", "gap_ratio"):
        assert as_decimal(report[key + "_raw"]) == as_decimal(case["expected"][key]), \
            "配额 %s 不一致" % key


def test_quota_method_switch_switches_formula_branch(data_dir, truth):
    """FR-05.1：方法学切换即切换公式分支（基准法 vs 强度系数法）。"""
    index = RulesIndex.load(data_dir)
    power = index.resolve("gbt32150-2025", 2025, "power")
    steel = index.resolve("gbt32150-2025", 2024, "steel")
    assert index.pack(power)["quota"]["method"] == "benchmark"
    assert index.pack(steel)["quota"]["method"] == "intensity_coefficient"
    # 显式覆盖方法学：同一坐标可用另一分支试算（分支由参数决定，非硬编码）
    pack = index.effective_ruleset(power, scope=SCOPE_QUOTA)
    report = compute_quota(pack, power, "1000", params={
        "method": "historical_intensity", "output": "1000", "historical_intensity": "0.9"})
    assert report["method"] == "historical_intensity"
    assert as_decimal(report["allocated_raw"]) == as_decimal("900")


def test_quota_none_method_is_not_applicable(data_dir, truth):
    """method=none → 显式"不适用"（配额量为 None，而非静默取 0）。"""
    index = RulesIndex.load(data_dir)
    coord = index.resolve("gbt32150-2025", 2025, "power")
    pack = index.effective_ruleset(coord, scope=SCOPE_QUOTA)
    patched = jsonio.loads(jsonio.dumps(pack))
    patched["quota"]["method"] = "none"
    report = compute_quota(patched, coord, "1000", params={})
    assert report["status"] == STATUS_NOT_APPLICABLE
    assert report["allocated"] is None and report["allocated_raw"] is None
    assert report["gap"] is None


def test_quota_missing_external_input_raises(data_dir, truth):
    """行业平衡值（外部输入）未提供 → QuotaUnavailable（退出码 2，不得静默取 0）。"""
    case = truth["cases"]["quota_missing_benchmark"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    with pytest.raises(QuotaUnavailable):
        _quota(data_dir, profile, {})


def test_quota_unknown_method_rejected(data_dir, truth):
    index = RulesIndex.load(data_dir)
    coord = index.resolve("gbt32150-2025", 2024, "steel")
    pack = index.effective_ruleset(coord, scope=SCOPE_QUOTA)
    with pytest.raises(InputError):
        compute_quota(pack, coord, "1000", params={"method": "made_up"})


def test_quota_disclaimer_is_mandatory(data_dir, truth):
    """R3/NFR-10：免责声明强制——结构体恒定要求渲染层输出，且文本非空。"""
    case = truth["cases"]["quota_benchmark"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    report = _quota(data_dir, profile, {"correction_factor": case["correction_factor"]})
    assert report["disclaimer_required"] is True
    assert report["disclaimer"]
    assert "以主管部门核定" in report["disclaimer"]
    assert "以主管部门核定" in render_quota_text(report)


def test_quota_is_deterministic(data_dir, truth):
    case = truth["cases"]["quota_intensity_coefficient"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    params = {"benchmark_value": case["benchmark_value"]}
    assert _quota(data_dir, profile, params) == _quota(data_dir, profile, params)


def test_quota_alpha_derivation_band_boundaries(data_dir, truth):
    """表 3 分段：偏离度越带 → ±封顶；带内 → 斜率×偏离度（分段常数取自规则包）。"""
    index = RulesIndex.load(data_dir)
    coord = index.resolve("gbt32150-2025", 2024, "steel")
    pack = index.effective_ruleset(coord, scope=SCOPE_QUOTA)
    derivation = pack["quota"]["derivation"]
    cap = as_decimal(derivation["cap"]["value"])
    slope = as_decimal(derivation["slope"]["value"])
    band = as_decimal(derivation["band"]["value"])
    # 企业强度远优于基准（X 越上限）→ α = +cap
    report = compute_quota(pack, coord, "100", params={"benchmark_value": "100", "output": "1000"})
    assert as_decimal(report["parameters"]["correction_factor"]["value"]) == cap
    # 带内：X 取带的一半 → α = slope × X（未触封顶）
    inside = band / 2
    # Ii = BP × (1 − X)；取 BP=1、output=1 直接构造
    report2 = compute_quota(pack, coord, str(as_decimal(1) - inside),
                            params={"benchmark_value": "1", "output": "1"})
    alpha = as_decimal(report2["parameters"]["correction_factor"]["value"])
    deviation = as_decimal(report2["parameters"]["deviation"])
    assert deviation == inside
    assert alpha == slope * deviation
    assert abs(alpha) < cap


# ---------- 配额算例真值与档案 sha256 对账 ----------

def test_quota_case_profiles_sha256_match_truth(data_dir, truth):
    for key in ("quota_benchmark", "quota_intensity_coefficient"):
        case = truth["cases"][key]
        path = os.path.join(data_dir, "truth", case["file"])
        import hashlib
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == case["sha256"]


def test_quality_case_profiles_sha256_match_truth(data_dir, truth):
    import hashlib
    for key in ("quality_bad_unit", "quality_magnitude_outlier",
                "quality_intensity_out_of_range"):
        case = truth["cases"][key]
        path = os.path.join(data_dir, "truth", case["file"])
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == case["sha256"], key
    yoy = truth["cases"]["quality_yoy_jump"]
    for field in ("file", "clean_file", "baseline_file"):
        path = os.path.join(data_dir, "truth", yoy[field])
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == yoy[field.replace("file", "sha256")]


def test_json_dumps_roundtrip_for_quality_report(data_dir, truth):
    """校核报告可确定性序列化（供报告导出复用）。"""
    profile = _load(data_dir, truth, "steel-2024")
    report = _check(data_dir, profile)
    assert json.loads(jsonio.dumps(report)) is not None