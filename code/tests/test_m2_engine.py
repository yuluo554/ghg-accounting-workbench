"""M2 核算引擎测试：边界识别 / 双标尺差异 / 完整编排 / 溯源完整性 / 失败路径。

对账纪律（沿用 M1 双路独立实现）：
  * 真值由 ``tools/gen_synthetic.py`` 按规则包**直接算式**算出（含单位换算与因子优先级）；
  * 引擎走 ``ghg.pipeline.compute_full`` → ``ghg.calc`` 的**表达式树求值**路径；
  两者对同一档案必须逐源 + 汇总一致。
"""

import os

import pytest

from ghg import jsonio
from ghg.boundary import diff_boundary, identify_boundary
from ghg.calc import compute
from ghg.coordinates import parse_coordinate
from ghg.decimals import as_decimal
from ghg.errors import (
    BoundaryError,
    CoordinateError,
    FactorUnavailable,
    ProvenanceError,
    RulesetNotEffective,
)
from ghg.pipeline import compute_full, render_report_text, resolve_rule_entry
from ghg.rules import SCOPE_CALC, RulesIndex
from ghg.units import UnitTable


@pytest.fixture(scope="session")
def truth(data_dir):
    return jsonio.load(os.path.join(data_dir, "truth", "expected.json"))


def _load(data_dir, truth, name):
    return jsonio.load(os.path.join(data_dir, "truth", truth["profiles"][name]["file"]))


def _effective(data_dir, profile):
    index = RulesIndex.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
    return index, coord, pack


# ---------- 边界识别（FR-01.1）----------

def test_identify_boundary_includes_required_with_input(data_dir, truth):
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    report = identify_boundary(profile, coord, pack)
    assert report["included"] == ["carbon_product", "process_emission", "stationary_combustion"]
    assert report["missing_inputs"] == []
    # 每条纳入项都挂条款依据文本（FR-01.1）
    for src in report["sources"]:
        assert src["reason"]
        if src["included"]:
            assert src["clause"]["article"]


def test_identify_boundary_flags_missing_required(data_dir, truth):
    case = truth["cases"]["missing_required_source"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    index, coord, pack = _effective(data_dir, profile)
    report = identify_boundary(profile, coord, pack)
    assert report["missing_inputs"] == [case["missing_source_id"]]
    assert case["missing_source_id"] not in report["included"]


def test_identify_boundary_rejects_unknown_source(data_dir, truth):
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    bad = dict(profile)
    bad["sources"] = list(profile["sources"]) + [
        {"source_id": "not_a_real_source", "activity": {"value": "1", "unit": "t"}}]
    with pytest.raises(BoundaryError):
        identify_boundary(bad, coord, pack)


def test_identify_boundary_include_optional(data_dir, truth):
    """选填源在提供活动数据且显式 include_optional 时纳入。"""
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    enriched = dict(profile)
    enriched["sources"] = list(profile["sources"]) + [
        {"source_id": "purchased_electricity", "activity": {"value": "1000", "unit": "MWh"}}]
    without = identify_boundary(enriched, coord, pack)
    assert "purchased_electricity" not in without["included"]
    with_opt = identify_boundary(enriched, coord, pack, include_optional=True)
    assert "purchased_electricity" in with_opt["included"]


# ---------- 双标尺差异（FR-01.3）----------

def test_diff_boundary_shapes(rules_index):
    old = rules_index.resolve("gbt32150-2015", 2024, "steel")
    new = rules_index.resolve("gbt32150-2025", 2024, "steel")
    diff = diff_boundary(old, new, rules_index)
    assert diff["base"] == "gbt32150-2015/2024/steel"
    assert diff["target"] == "gbt32150-2025/2024/steel"
    assert diff["added"] == [] and diff["removed"] == []
    assert diff["unchanged"] == ["process_emission"]
    adjusted_ids = sorted({row["id"] for row in diff["adjusted"]})
    assert "stationary_combustion" in adjusted_ids
    for row in diff["adjusted"]:
        assert set(row) >= {"id", "field", "from", "to", "declared_delta"}
        assert row["declared_delta"] == "adjusted"


def test_diff_boundary_requires_two_standards(rules_index):
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    with pytest.raises(CoordinateError):
        diff_boundary(coord, coord, rules_index)


def test_diff_boundary_is_deterministic(rules_index):
    old = rules_index.resolve("gbt32150-2015", 2024, "cement")
    new = rules_index.resolve("gbt32150-2025", 2024, "cement")
    assert diff_boundary(old, new, rules_index) == diff_boundary(old, new, rules_index)


def test_diff_boundary_added_and_removed(data_dir, rules_index):
    """added / removed 分支：向 2025 包注入一条旧版没有的源，并从新版删一条旧版有的源。"""
    from ghg.rules import RulesIndex as _Index
    old_coord = rules_index.resolve("gbt32150-2015", 2024, "power")
    new_coord = rules_index.resolve("gbt32150-2025", 2024, "power")
    old_pack = jsonio.loads(jsonio.dumps(rules_index.pack(old_coord)))
    new_pack = jsonio.loads(jsonio.dumps(rules_index.pack(new_coord)))

    # 新版新增一条（旧版无）；新版删除一条旧版有的（fugitive_emission）
    new_pack["boundary"]["sources"].append({
        "id": "injected_new_source", "name": "注入源（合成）", "category": "other",
        "required": False, "delta_vs_2015": "added",
        "clause": {"code": "SYNTH", "article": "1"}, "status": "verified",
    })
    new_pack["boundary"]["sources"] = [
        s for s in new_pack["boundary"]["sources"] if s["id"] != "fugitive_emission"]

    index = _Index(rules_index.data_dir, rules_index._manifest, rules_index.base_dir)
    index._cache[old_coord.key] = (rules_index._by_key[old_coord.key], old_pack)
    index._cache[new_coord.key] = (rules_index._by_key[new_coord.key], new_pack)

    diff = diff_boundary(old_coord, new_coord, index)
    assert diff["added"] == ["injected_new_source"]
    assert diff["removed"] == ["fugitive_emission"]


def test_diff_boundary_rejects_inconsistent_declaration(data_dir, rules_index):
    """声明 delta_vs_2015=same 但结构字段实际变化 → BoundaryError（第二份真相检测）。"""
    from ghg.rules import RulesIndex as _Index
    old_coord = rules_index.resolve("gbt32150-2015", 2024, "power")
    new_coord = rules_index.resolve("gbt32150-2025", 2024, "power")
    old_pack = jsonio.loads(jsonio.dumps(rules_index.pack(old_coord)))
    new_pack = jsonio.loads(jsonio.dumps(rules_index.pack(new_coord)))
    for src in new_pack["boundary"]["sources"]:
        if src["id"] == "fugitive_emission":
            src["required"] = not src["required"]      # 结构变化，但声明仍为 same
    index = _Index(rules_index.data_dir, rules_index._manifest, rules_index.base_dir)
    index._cache[old_coord.key] = (rules_index._by_key[old_coord.key], old_pack)
    index._cache[new_coord.key] = (rules_index._by_key[new_coord.key], new_pack)
    with pytest.raises(BoundaryError):
        diff_boundary(old_coord, new_coord, index)


def test_factor_by_category_dispatch(data_dir, truth):
    """按类别分派：规则包为某类别配置 by_category 覆盖时，选择器取该条目。"""
    from ghg.rules import RulesIndex as _Index
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    patched = jsonio.loads(jsonio.dumps(pack))
    by_category = patched["factors"]["industry_default_values"].setdefault("by_category", {})
    # process 类别缺省因子取行业缺省值的一半（合成覆盖，便于断言确实走了 by_category）
    half = as_decimal(pack["factors"]["industry_default_values"]["default_factor"]["value"]) / 2
    by_category["process"] = {
        "value": str(half), "unit": "tCO2e_per_t", "status": "verified",
        "clause": {"code": "SYNTH", "article": "1"},
    }
    new_index = _Index(index.data_dir, index._manifest, index.base_dir)
    new_index._cache[coord.key] = (index._by_key[coord.key], patched)
    report = compute_full(profile, coord, new_index, units, generated_at="FIXED")
    by_id = {l["source_id"]: l for l in report["calc"]["lines"]}
    assert by_id["process_emission"]["factor"]["source"] == "industry_default:process"
    assert by_id["stationary_combustion"]["factor"]["source"] == "industry_default"
    # 溯源表能解析到 by_category 下的具体条目
    node = resolve_rule_entry(patched,
                              "factors.industry_default_values.by_category.process")
    assert node["value"] == str(half)


# ---------- 算例回归 100%（引擎 vs 真值库）----------

def test_pipeline_matches_truth_for_every_profile(data_dir, truth):
    """M2 DoD：全部算例（含单位换算 / 因子优先级）逐源 + 汇总 100% 对账。"""
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    for name, expected in sorted(truth["profiles"].items()):
        profile = jsonio.load(os.path.join(data_dir, "truth", expected["file"]))
        coord = parse_coordinate(profile["coordinate"], index=index)
        report = compute_full(profile, coord, index, units, generated_at="FIXED")
        calc = report["calc"]
        assert calc["total_raw"] == expected["total"], "%s 汇总不一致" % name
        by_id = {line["source_id"]: line for line in calc["lines"]}
        assert sorted(by_id) == sorted(l["source_id"] for l in expected["lines"])
        for exp_line in expected["lines"]:
            got = by_id[exp_line["source_id"]]
            assert as_decimal(got["emission_raw"]) == as_decimal(exp_line["emission"]), \
                "%s.%s 逐源不一致" % (name, exp_line["source_id"])


def test_unit_conversion_case_is_explicit(data_dir, truth):
    """FR-02.3：以 kg 录入的活动数据必须经显式换算链落到 t 口径。"""
    profile = _load(data_dir, truth, "steel-2024-unit-kg")
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    result = compute(profile, coord, pack, units)
    line = [l for l in result["lines"] if l["source_id"] == "stationary_combustion"][0]
    assert line["activity"]["unit"] == "kg"
    assert line["activity_base"]["unit"] == "t"
    assert line["unit_chain"], "单位换算链不得为空"
    assert any(step["from_unit"] == "kg" and step["to_unit"] == "t"
               for step in line["unit_chain"])


def test_measured_factor_takes_priority(data_dir, truth):
    """FR-02.4：实测 / 官方因子库优先于行业缺省，且因子来源标签正确。"""
    profile = _load(data_dir, truth, "steel-2024-measured-factor")
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    result = compute(profile, coord, pack, units)
    by_id = {l["source_id"]: l for l in result["lines"]}
    assert by_id["stationary_combustion"]["factor"]["source"] == "measured"
    assert by_id["process_emission"]["factor"]["source"] == "official_db"
    assert by_id["carbon_product"]["factor"]["source"] == "industry_default"
    # 优先级次序与规则包声明一致
    assert pack["factors"]["priority"] == ["measured", "official_db", "industry_default"]


# ---------- 完整编排与溯源完整性（FR-06.2 / plan/04 §6.3）----------

def test_compute_full_report_structure(data_dir, truth):
    profile = _load(data_dir, truth, "steel-2024")
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    report = compute_full(profile, coord, index, units, generated_at="FIXED")
    head = report["report_head"]
    for key in ("coordinate", "tool_version", "generated_at", "disclaimer"):
        assert head.get(key), "报告头缺 %s" % key
    assert report["factor_table"], "因子来源表不得为空"
    counts = report["provenance_counts"]
    assert counts["total"] == counts["detail_rows"] + counts["factor_rows"]


def test_provenance_rows_resolve_to_rule_entries(data_dir, truth):
    """溯源表每一行的 rule_entry_id 必须能在该坐标包内解析到具体条目。"""
    profile = _load(data_dir, truth, "steel-2024")
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
    report = compute_full(profile, coord, index, units, generated_at="FIXED")
    for row in report["provenance"]:
        node = resolve_rule_entry(pack, row["rule_entry_id"])
        assert node, "溯源条目解析为空：%s" % row["rule_entry_id"]


def test_provenance_dangling_reference_raises(data_dir, truth):
    """悬空溯源引用必须抛 ProvenanceError（不得导出半溯源报告）。"""
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    with pytest.raises(ProvenanceError):
        resolve_rule_entry(pack, "boundary.sources.no_such_source")
    with pytest.raises(ProvenanceError):
        resolve_rule_entry(pack, "factors.nope.nothing")


def test_compute_full_is_deterministic(data_dir, truth):
    """同输入同规则包 → 结构化结果逐字段相同（NFR-04）。"""
    profile = _load(data_dir, truth, "steel-2024")
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    a = compute_full(profile, coord, index, units, generated_at="FIXED")
    b = compute_full(profile, coord, index, units, generated_at="FIXED")
    assert a == b


def test_render_report_contains_all_sections(data_dir, truth):
    profile = _load(data_dir, truth, "steel-2024")
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    report = compute_full(profile, coord, index, units, diff_standard="gbt32150-2015",
                          generated_at="FIXED")
    text = render_report_text(report)
    for section in ("报告头", "核算边界", "双标尺差异", "逐排放源明细表",
                    "因子来源表", "数据溯源表", "排放总量"):
        assert section in text, "报告缺章节：%s" % section


# ---------- 失败路径退出码（M2 DoD）----------

def test_factor_unavailable_raises(data_dir, truth):
    """因子三层皆不可用 → FactorUnavailable（退出码 2，不得静默取 0/1）。"""
    case = truth["cases"]["factor_unavailable"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    stripped = {k: v for k, v in pack.items() if k != "factors"}
    with pytest.raises(FactorUnavailable):
        compute(profile, coord, stripped, units)


def test_bad_format_missing_activity_value_raises(data_dir, truth):
    """坏格式（activity.value 为 null）→ BoundaryError（退出码 2）。"""
    case = truth["cases"]["bad_format_missing_activity_value"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    with pytest.raises(BoundaryError):
        compute(profile, coord, pack, units)


def test_gate_blocks_calc_path(data_dir, truth):
    """核算路径仍有 pending 的坐标（2026 发电）→ RulesetNotEffective（退出码 1）。"""
    index = RulesIndex.load(data_dir)
    coord = index.resolve("gbt32150-2025", 2026, "power")
    with pytest.raises(RulesetNotEffective):
        index.effective_ruleset(coord, scope=SCOPE_CALC)


def test_factor_source_label_rejects_unknown(data_dir, truth):
    """档案自报非法因子来源 → FactorUnavailable（不得冒名缺省因子）。"""
    profile = _load(data_dir, truth, "steel-2024")
    index, coord, pack = _effective(data_dir, profile)
    units = UnitTable.load(data_dir)
    bad = jsonio.loads(jsonio.dumps(profile))
    bad["sources"][0]["factor"] = {"value": "1", "unit": "tCO2e_per_t", "source": "made_up"}
    with pytest.raises(FactorUnavailable):
        compute(bad, coord, pack, units)