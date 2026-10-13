"""M5 桌面形态测试（FR-08.2）—— **全程 offscreen，不依赖真实显示器**。

四条纪律：

1. **offscreen 常驻**：本模块在 import 前强制 ``QT_QPA_PLATFORM=offscreen``，
   无显示环境（CI / 无头机）也必须能跑——GUI 测试不得成为"只有本机能跑"的测试。
2. **只消费引擎 API**（导入门禁）：页面/模型模块不得直接 import
   ``ghg.calc`` / ``ghg.quality`` / ``ghg.quota`` / ``ghg.bench``——
   那意味着界面里长出了第二套引擎调用面。测试用 AST 静态检查锁定这条纪律。
3. **零判定逻辑**：界面结论必须与引擎结论逐字段一致（同输入同输出）。
4. **四页签可渲染**：每个页面在 offscreen 下能跑通并把结果填进表格。

PySide6 属 ``gui`` extra；未安装时整体跳过（核心层零依赖的纪律不因 GUI 测试被破坏）。
"""

import ast
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6", reason="GUI 测试需要 PySide6（gui extra）")

from ghg import jsonio                                        # noqa: E402
from ghg.rules import SCOPE_CALC, parse_payload_coordinate    # noqa: E402

from ghg_gui import models as M                               # noqa: E402
from ghg_gui.service import WorkbenchService                  # noqa: E402

GUI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui",
                       "ghg_gui")

# 界面层不得直接触碰的引擎模块（唯一入口是 ghg_gui.service）
FORBIDDEN_ENGINE_MODULES = ("ghg.calc", "ghg.quality", "ghg.quota", "ghg.bench")

# 唯一被允许直接 import 引擎判定模块的文件（GUI 与引擎之间的收口点）
GATEWAY_MODULE = "service.py"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(scope="session")
def service(data_dir):
    return WorkbenchService(data_dir)


@pytest.fixture
def steel(data_dir):
    return jsonio.load(os.path.join(data_dir, "truth", "profiles", "steel-2024.json"))


def _gui_modules():
    return sorted(name for name in os.listdir(GUI_DIR) if name.endswith(".py"))


# ---------- 导入门禁（FR-08.2「只消费引擎 API」）----------

def test_gui_modules_exist():
    assert _gui_modules(), "未找到 GUI 模块"


def test_gui_modules_do_not_import_engine_internals():
    """静态导入门禁：界面模块只能经 ``ghg_gui.service`` 触达引擎。

    允许 import 的 ghg 模块是"无判定语义"的公共面（errors/jsonio/paths/decimals/
    pipeline 编排单点）；**禁止**直接 import 承担判定的 calc/quality/quota/bench——
    否则界面里会出现第二套核算/校核/配额/基准调用，与 CLI 行为漂移。
    ``service.py`` 是唯一例外：它是 GUI 与引擎之间的**收口点**（本身即为此而存在）。
    """
    offenders = []
    for name in _gui_modules():
        if name == GATEWAY_MODULE:
            continue
        path = os.path.join(GUI_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_ENGINE_MODULES:
                offenders.append("%s: from %s import ..." % (name, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_ENGINE_MODULES:
                        offenders.append("%s: import %s" % (name, alias.name))
    assert offenders == [], "界面层绕过了 service 直接调用引擎判定模块：%s" % offenders


def test_gui_has_no_policy_numeric_literals(repo_root, data_dir):
    """GUI 源码同样受零政策字面量门禁约束（与引擎/CLI 同一条纪律）。"""
    import importlib.util
    import sys
    tools_dir = os.path.join(repo_root, "tools")
    spec = importlib.util.spec_from_file_location(
        "ghg_gate_for_gui", os.path.join(tools_dir, "check_zero_literals.py"))
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    hits = gate.scan(repo_root, data_dir,
                     targets=[os.path.join("code", "gui", "ghg_gui")])
    assert hits == [], "GUI 源码命中政策字面量：%s" % hits


# ---------- 服务层（引擎 API 门面）----------

def test_service_exposes_coordinate_space_from_manifest(service):
    assert service.coordinates()
    assert len(service.coordinates()) == 40
    assert service.standards() and service.industries() and service.years()


def test_service_gate_summary_reports_three_scopes(service, rules_index):
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    summary = service.gate_summary(coord)
    assert set(summary) == {"calc", "quota", "check"}
    assert summary["calc"]["effective"] is True


def test_service_sample_profiles_exist(service):
    samples = service.sample_profiles()
    assert samples, "未找到内置示例档案"
    assert all(path.endswith(".json") for path in samples)


def test_service_calc_matches_engine(service, rules_index, unit_table, steel):
    """界面结论必须与引擎结论逐字段一致（同输入同输出）。"""
    from ghg.pipeline import compute_full
    coord = parse_payload_coordinate(steel, index=rules_index)
    engine = compute_full(steel, coord, rules_index, unit_table, generated_at="t")
    ui = service.calc(steel, generated_at="t")
    assert ui["calc"]["total"] == engine["calc"]["total"]
    assert [l["emission"] for l in ui["calc"]["lines"]] == \
        [l["emission"] for l in engine["calc"]["lines"]]
    assert ui["provenance_counts"] == engine["provenance_counts"]


# ---------- 视图模型（零 Qt 依赖）----------

def test_calc_model_rows_match_lines(service, steel):
    model = M.CalcPageModel(service).run(steel)
    assert model.status == M.STATUS_OK
    assert len(model.rows) == 3
    assert "排放总量" in model.summary


def test_calc_model_failure_is_reported_not_raised(service, tmp_path):
    """引擎异常必须转成界面失败态（而不是让界面崩栈）。"""
    bad = tmp_path / "bad.json"
    jsonio.write(str(bad), {"facility": {"name": "无坐标"}})
    model = M.CalcPageModel(service).run(jsonio.load(str(bad)))
    assert model.status == M.STATUS_FAIL
    assert model.error


def test_check_model_summary_counts_levels(service, data_dir):
    bad = jsonio.load(os.path.join(data_dir, "truth", "profiles", "steel-2024-bad-unit.json"))
    model = M.CheckPageModel(service).run(bad)
    assert model.status == M.STATUS_OK
    assert model.has_error() is True
    assert any(row[0] == "error" for row in model.rows)


def test_quota_model_renders_mandatory_disclaimer(service, steel):
    model = M.QuotaPageModel(service).run(steel, params={"benchmark_value": "2"})
    assert model.status == M.STATUS_OK
    assert model.disclaimer(), "配额页必须输出免责声明（R3 / NFR-10）"


def test_quota_model_missing_external_input_is_failure(service, steel):
    model = M.QuotaPageModel(service).run(steel, params={})
    assert model.status == M.STATUS_FAIL
    assert "外部提供" in model.error


def test_bench_model_matches_engine(service):
    model = M.BenchPageModel(service).run()
    assert model.status == M.STATUS_OK
    assert any(row[0] == "rules_self_consistency_rate" for row in model.rows)
    assert all(row[3] == "达标" for row in model.rows)


def test_bench_model_suite_filter(service):
    model = M.BenchPageModel(service).run(suites=["cases"])
    assert model.status == M.STATUS_OK
    assert "cases" in model.summary


def test_build_models_returns_four_pages(service):
    models = M.build_models(service)
    assert set(models) == {"calc", "check", "quota", "bench"}


# ---------- Qt 页面（offscreen 渲染）----------

def test_main_window_has_four_tabs(qapp, service):
    from ghg_gui.pages import build_window
    window = build_window(service.data_dir)
    try:
        assert window.tabs.count() == 4
        labels = [window.tabs.tabText(i) for i in range(4)]
        assert labels == ["核算", "校核", "配额", "基准"]
    finally:
        window.close()


def test_every_page_runs_offscreen_and_fills_table(qapp, service):
    """四页签在 offscreen 下逐个跑通（不依赖真实显示器）。"""
    from ghg_gui.pages import build_window
    window = build_window(service.data_dir)
    try:
        window.calc_page.profile_edit.setText(_steel_path(service))
        window.calc_page.run_action()
        window.calc_page.refresh()
        assert window.calc_page.table.rowCount() == 3
        assert window.calc_page.status_label.text()

        window.check_page.profile_edit.setText(_steel_path(service))
        window.check_page.run_action()
        window.check_page.refresh()
        assert window.check_page.status_label.text()

        window.quota_page.profile_edit.setText(_steel_path(service))
        window.quota_page.benchmark_edit.setText("2")
        window.quota_page.run_action()
        window.quota_page.refresh()
        assert window.quota_page.table.rowCount() > 0
        assert "免责声明" in window.quota_page.output.toPlainText()

        window.bench_page.run_action()
        window.bench_page.refresh()
        assert window.bench_page.table.rowCount() > 0
    finally:
        window.close()


def test_calc_page_gate_failure_shows_failure_status(qapp, service, tmp_path):
    """门控拦截的坐标 → 页面显示失败态（不得静默显示空结果）。"""
    from ghg_gui.pages import build_window
    path = tmp_path / "power2026.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2026, "industry": "power"},
        "facility": {"name": "示例发电（合成）"},
        "sources": [{"source_id": "stationary_combustion",
                     "activity": {"value": "1000", "unit": "t"}}],
    })
    window = build_window(service.data_dir)
    try:
        window.calc_page.profile_edit.setText(str(path))
        window.calc_page.run_action()
        window.calc_page.refresh()
        assert window.calc_page.model.status == M.STATUS_FAIL
        assert "未核对" in window.calc_page.status_label.text()
    finally:
        window.close()


def test_gui_selftest_entry_returns_zero(qapp, service):
    """``ghg-gui --selftest`` 入口：无窗口自检复用 CLI 实现，退出码 0。"""
    from ghg_gui.main import main
    assert main(["--selftest", "--data-dir", service.data_dir]) == 0


def test_service_export_writes_three_products(service, tmp_path, steel):
    """GUI 的报告导出走 ``service.export``（与 CLI `report` 同一引擎入口）。"""
    written = service.export(steel, str(tmp_path), formats=("md", "csv", "xlsx"))
    assert written["md"] and written["csv"] and written["xlsx"]
    assert os.path.isfile(written["md"][0])
    assert os.path.isfile(written["xlsx"][0])
    raw = open(written["md"][0], "rb").read()
    assert b"\r" not in raw


def test_service_export_rejects_missing_dir(service, steel, tmp_path):
    from ghg.errors import InputError
    with pytest.raises(InputError):
        service.export(steel, str(tmp_path / "nope"))


def test_calc_page_export_button_gated_on_success(qapp, service):
    """导出按钮只在核算成功后可用（失败态不得导出半成品）。"""
    from ghg_gui.pages import build_window
    window = build_window(service.data_dir)
    try:
        assert window.calc_page.export_button.isEnabled() is False
        window.calc_page.profile_edit.setText(_steel_path(service))
        window.calc_page.run_action()
        window.calc_page.refresh()
        assert window.calc_page.export_button.isEnabled() is True
    finally:
        window.close()


def test_calc_page_export_writes_files(qapp, service, tmp_path, monkeypatch):
    """点击导出（目录由对话框返回，测试里 monkeypatch 掉对话框）→ 产物落盘。"""
    from PySide6.QtWidgets import QFileDialog

    from ghg_gui.pages import build_window
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(tmp_path)))
    window = build_window(service.data_dir)
    try:
        window.calc_page.profile_edit.setText(_steel_path(service))
        window.calc_page.run_action()
        window.calc_page.refresh()
        window.calc_page._on_export()
        produced = sorted(os.listdir(str(tmp_path)))
        assert "report.md" in produced
        assert "report.xlsx" in produced
        assert "数据溯源表.csv" in produced
        assert "报告已导出" in window.calc_page.output.toPlainText()
    finally:
        window.close()


def _steel_path(service):
    return os.path.join(service.data_dir, "truth", "profiles", "steel-2024.json")