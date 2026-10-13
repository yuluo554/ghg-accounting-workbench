"""M4 内置基准测试（FR-07）。

纪律（与全项目一致）：
  * **门槛是数据**：验收门槛从 ``manifest.bench.targets`` 读出，测试断言"基准真的用了它"，
    而不是把门槛数值再抄一遍（NFR-07 同源纪律）；
  * **基准必须可证伪**：每个套件都要有"注入缺陷 → 基准必须报未过"的探活测试，
    否则"基准通过"可能只是"基准什么都没查"（M0 零字面量门禁探活的同一思路）；
  * **只读 / 确定性**：基准不改输入、两次运行结果逐字节相同、退出码语义锁定。
"""

import json
import os
import shutil

import pytest

from ghg import bench, jsonio
from ghg.errors import EXIT_GATE, EXIT_INPUT, EXIT_OK, BenchConfigError
from ghg.rules import RulesIndex
from ghg.units import UnitTable


@pytest.fixture(scope="session")
def bench_report(data_dir):
    return bench.run_bench(data_dir)


# ---------- 三类基准全绿（M4 DoD 主线）----------

def test_bench_all_suites_run_and_pass(bench_report):
    assert bench_report["ok"] is True, bench_report["suites"]
    assert list(bench_report["suites_run"]) == list(bench.SUITES)
    for name in bench.SUITES:
        suite = bench_report["suites"][name]
        assert suite["checks_failed"] == 0, suite["failures"]
        assert suite["checks_total"] > 0, "套件 %s 一项都没查" % name


def test_bench_metrics_meet_targets(bench_report):
    """四项指标全部对上门槛（门槛取自 manifest，非测试内联）。"""
    for verdict in bench_report["verdicts"]:
        assert verdict["met"] is True, verdict
    metrics = bench_report["metrics"]
    assert metrics[bench.M_SELF_CONSISTENCY] == "1"
    assert metrics[bench.M_FACTOR_UNIT] == "1"
    assert metrics[bench.M_CASE_HIT] == "1"
    assert metrics[bench.M_CASE_FALSE_POSITIVE] == "0"


def test_bench_runtime_within_nfr11(bench_report, rules_index):
    """NFR-11：单次全量运行 < 2 秒（门槛同样取自 manifest）。"""
    targets = rules_index.bench_targets()
    elapsed = bench_report["metrics"][bench.M_RUNTIME]
    assert elapsed is not None
    assert float(elapsed) <= float(str(targets[bench.M_RUNTIME]))


def test_bench_targets_come_from_manifest(data_dir, rules_index):
    """门槛真取自 manifest（把门槛调高 → 判定随之改变，证明代码未内联门槛）。"""
    targets = rules_index.bench_targets()
    assert bench.M_RUNTIME in targets
    assert bench.M_CASE_HIT in targets
    # 人为把命中率门槛提到不可能达到 → 同一指标判定必须翻转
    patched = dict(targets)
    patched[bench.M_CASE_HIT] = 2
    assert bench._compare(bench.M_CASE_HIT, 1, patched[bench.M_CASE_HIT]) is False
    assert bench._compare(bench.M_CASE_HIT, 1, targets[bench.M_CASE_HIT]) is True


def test_bench_missing_targets_is_config_error(data_dir, rules_index):
    """manifest 缺门槛配置 → BenchConfigError（退出码 2），不得回落到代码默认值。"""
    manifest = dict(rules_index._manifest)
    manifest.pop("bench", None)
    index = RulesIndex(rules_index.data_dir, manifest, rules_index.base_dir)
    with pytest.raises(BenchConfigError) as exc_info:
        index.bench_targets()
    assert exc_info.value.exit_code == EXIT_INPUT


# ---------- 套件可证伪（探活）----------

def _copy_data(tmp_path, data_dir):
    work = tmp_path / "data"
    shutil.copytree(data_dir, str(work))
    return str(work)


def test_rules_suite_detects_broken_formula_ref(tmp_path, data_dir):
    """探活：表达式引用不存在的系数 → rules 套件必须报未过。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2024-steel.json")
    pack = jsonio.load(path)
    pack["engine"]["formula"]["expr"] = {
        "op": "mul",
        "args": [{"op": "var", "ref": "activity_data"},
                 {"op": "const", "ref": "no_such_coefficient"}],
    }
    jsonio.write(path, pack)
    index = RulesIndex.load(work)
    tally = bench.suite_rules(index)
    assert tally.total - tally.passed >= 1
    assert any("公式引用" in f["check"] for f in tally.failures)


def test_rules_suite_detects_scope_leak(tmp_path, data_dir):
    """探活：pending 条目落在**任何作用域都不覆盖的块**（如 provenance）→ 作用域划分必须报未过。

    ``engine`` 块属核算作用域，在其中加 pending 条目属正常门控（不构成"划分错误"）；
    真正的划分漏洞是"整包能看到、但没有任何作用域认领"的条目——那意味着该条目可以
    绕过全部门控进入计算路径。
    """
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2024-steel.json")
    pack = jsonio.load(path)
    pack["provenance"]["pending_extra"] = {"status": "pending", "value": None}
    jsonio.write(path, pack)
    index = RulesIndex.load(work)
    tally = bench.suite_rules(index)
    assert any("门控作用域划分" in f["check"] for f in tally.failures)


def test_factor_suite_detects_cross_year_drift(tmp_path, data_dir):
    """探活：同源因子跨年改值 → factor 套件必须报未过。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2025-steel.json")
    pack = jsonio.load(path)
    pack["factors"]["industry_default_values"]["default_factor"]["value"] = "9.99"
    jsonio.write(path, pack)
    index = RulesIndex.load(work)
    tally = bench.suite_factor(index, UnitTable.load(work))
    assert any("同源因子跨年一致" in f["check"] for f in tally.failures)


def test_factor_suite_detects_orphan_category_override(tmp_path, data_dir):
    """探活：按类别覆盖出现"孤儿类别" → factor 套件必须报未过。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2024-steel.json")
    pack = jsonio.load(path)
    pack["factors"]["industry_default_values"]["by_category"] = {
        "not_a_real_category": {"value": "1", "unit": "tCO2e_per_t",
                                "status": "verified"},
    }
    jsonio.write(path, pack)
    index = RulesIndex.load(work)
    tally = bench.suite_factor(index, UnitTable.load(work))
    assert any("类别覆盖键" in f["check"] for f in tally.failures)


def test_factor_suite_detects_unresolvable_factor_unit(tmp_path, data_dir):
    """探活：因子单位分母不在单位表内 → factor 套件必须报未过。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2024-steel.json")
    pack = jsonio.load(path)
    pack["factors"]["industry_default_values"]["default_factor"]["unit"] = \
        "tCO2e_per_stone"
    jsonio.write(path, pack)
    index = RulesIndex.load(work)
    tally = bench.suite_factor(index, UnitTable.load(work))
    assert any("因子单位拆分" in f["check"] for f in tally.failures)


def test_cases_suite_detects_injected_false_positive(tmp_path, data_dir):
    """探活：把干净对照档案改成异常 → 误报率 > 0 且基准判未达标。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "truth", "profiles", "steel-2024.json")
    payload = jsonio.load(path)
    for src in payload["sources"]:
        if src["source_id"] == "stationary_combustion":
            src["activity"]["value"] = "99999999"
    jsonio.write(path, payload)
    report = bench.run_bench(work)
    assert report["ok"] is False
    assert report["cases"]["false_positives"] >= 1
    assert report["metrics"][bench.M_CASE_FALSE_POSITIVE] != "0"


def test_cases_suite_detects_missed_case(tmp_path, data_dir):
    """探活：把某个用例的期望规则改成不存在的 id → 命中率下降且基准判未达标。"""
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "truth", "expected.json")
    expected = jsonio.load(path)
    expected["cases"]["quality_bad_unit"]["expected_rule"] = "Q-NOPE-99"
    jsonio.write(path, expected)
    report = bench.run_bench(work)
    assert report["ok"] is False
    assert report["cases"]["cases_hit"] < report["cases"]["cases_total"]


def test_corrupt_ruleset_is_unmet_not_usage_error(tmp_path, data_dir):
    """数据坏了 → 基准必须报"未达标"（退出码 1），不得冒泡成"用法错误"（退出码 2）。

    规则包损坏到求值即抛 GhgError（公式引用不存在的系数）时，若异常冒泡，
    CLI 会把"数据坏了"误报成"用法错了"（退出码 2），掩盖真实问题。
    """
    work = _copy_data(tmp_path, data_dir)
    path = os.path.join(work, "rules", "ruleset-gbt32150-2025-2024-steel.json")
    pack = jsonio.load(path)
    pack["engine"]["formula"]["expr"] = {
        "op": "mul",
        "args": [{"op": "var", "ref": "activity_data"},
                 {"op": "const", "ref": "no_such_coefficient"}],
    }
    jsonio.write(path, pack)
    report = bench.run_bench(work)                 # 不得抛异常
    assert report["ok"] is False
    assert report["metrics"][bench.M_SELF_CONSISTENCY] != "1"
    assert report["cases"]["cases_hit"] < report["cases"]["cases_total"]


# ---------- 只读 / 确定性 / 覆盖度 ----------

def test_bench_does_not_mutate_data(data_dir, tmp_path):
    """基准只读：跑完后 data/ 下 JSON 的 sha256 逐份不变。"""
    import hashlib

    def snapshot(root):
        out = {}
        for dirpath, _dirs, files in os.walk(root):
            for name in sorted(files):
                if name.endswith(".json"):
                    p = os.path.join(dirpath, name)
                    with open(p, "rb") as fh:
                        out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
        return out

    before = snapshot(data_dir)
    bench.run_bench(data_dir)
    assert snapshot(data_dir) == before


def test_bench_is_deterministic(data_dir):
    """确定性（NFR-04）：两次运行除运行时长外逐字段一致。"""
    first = bench.run_bench(data_dir)
    second = bench.run_bench(data_dir)
    for report in (first, second):
        report["metrics"].pop(bench.M_RUNTIME, None)
        report["verdicts"] = [v for v in report["verdicts"]
                              if v["metric"] != bench.M_RUNTIME]
    assert first == second


def test_bench_unknown_suite_rejected(data_dir):
    with pytest.raises(BenchConfigError):
        bench.run_bench(data_dir, suites=["nope"])


def test_bench_suite_filter_runs_only_selected(data_dir):
    """--suite 只跑指定套件；未运行的指标不参与判定（不得误报未达标）。"""
    report = bench.run_bench(data_dir, suites=[bench.SUITE_RULES])
    assert list(report["suites_run"]) == [bench.SUITE_RULES]
    assert list(report["suites"]) == [bench.SUITE_RULES]
    assert report["ok"] is True
    metrics = {v["metric"] for v in report["verdicts"]}
    assert metrics == {bench.M_SELF_CONSISTENCY}
    assert bench.M_RUNTIME not in report["metrics"]


def test_bench_covers_every_coordinate_and_case(data_dir, bench_report, rules_index):
    """覆盖度：40 包 × 每包 12 项检查 + 12 用例 + 干净对照，一项不少。"""
    truth = jsonio.load(os.path.join(data_dir, "truth", "expected.json"))
    rules = bench_report["suites"][bench.SUITE_RULES]
    assert rules["checks_total"] >= len(rules_index.coordinates()) * 12
    assert bench_report["cases"]["cases_total"] == len(truth["cases"])
    controls = truth["controls"]["quality_clean"] + \
        [truth["controls"]["quality_yoy_clean"]]
    assert bench_report["cases"]["controls_total"] == len(controls)


def test_render_bench_text_reports_metrics(bench_report):
    text = bench.render_bench_text(bench_report)
    assert "规则自洽" in text or "rules" in text
    assert "达标" in text
    assert "结论" in text


def test_bench_report_is_json_serializable(data_dir, bench_report):
    assert json.loads(jsonio.dumps(bench_report)) is not None
