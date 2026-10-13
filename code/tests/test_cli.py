"""CLI 契约测试：退出码语义锁定（plan/03 §六）。

退出码是本工具的对外契约，测试在此锁死；后续重构不得漂移。
用 ``cli.main(argv)`` 直接调用（不经子进程），便于覆盖捕获与速度。
"""

import json
import os
from decimal import Decimal

import pytest

from ghg import cli, jsonio
from ghg.errors import EXIT_GATE, EXIT_INPUT, EXIT_OK


@pytest.fixture
def run(capsys):
    def _run(*argv):
        code = cli.main(list(argv))
        captured = capsys.readouterr()          # 只消费一次
        return code, captured.out, captured.err
    return _run


@pytest.fixture
def profile_file(tmp_path):
    """完整可核算档案（合成钢铁企业：应核算源齐全）→ 端到端出数。"""
    path = tmp_path / "profile.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "示例钢铁（合成）有限公司"},
        "sources": [
            {"source_id": "stationary_combustion",
             "activity": {"value": "100000", "unit": "t"}},
            {"source_id": "process_emission",
             "activity": {"value": "5000", "unit": "t"}},
            {"source_id": "carbon_product",
             "activity": {"value": "2000", "unit": "t"}},
        ],
    })
    return str(path)


@pytest.fixture
def incomplete_profile_file(tmp_path):
    """缺应核算源活动数据的档案 → 退出码 2（不得静默按空核算）。"""
    path = tmp_path / "incomplete.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "缺数据（合成）"},
        "sources": [],
    })
    return str(path)


# ---------- 基础子命令 ----------

def test_no_args_prints_help_and_exit_input(run):
    code, out, err = run()
    assert code == EXIT_INPUT
    assert "usage" in out.lower() or "用法" in out


def test_coords_ok(run):
    code, out, _ = run("coords")
    assert code == EXIT_OK
    assert "40" in out


def test_coords_json_is_parseable(run):
    code, out, _ = run("--json", "coords")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["count"] == 40


def test_units_ok(run):
    code, out, _ = run("units")
    assert code == EXIT_OK
    assert "mass" in out


def test_version_ok(run):
    code, out, _ = run("version")
    assert code == EXIT_OK
    assert "0.1.0" in out


def test_selftest_ok(run):
    code, out, _ = run("selftest")
    assert code == EXIT_OK
    assert "全部通过" in out


def test_selftest_json(run):
    code, out, _ = run("--json", "selftest")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["ok"] is True
    assert all(item["ok"] for item in payload["checks"])


# ---------- bench（M4 内置基准）----------

def test_bench_all_suites_exit_0(run):
    """M4 DoD：三类基准一条命令跑全 → 退出码 0（指标全部达标）。"""
    code, out, _ = run("bench")
    assert code == EXIT_OK
    assert "内置离线基准" in out
    assert "rules" in out and "factor" in out and "cases" in out
    assert "三类基准全部达标" in out


def test_bench_json_has_metrics_and_verdicts(run):
    code, out, _ = run("--json", "bench")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["metrics"]["rules_self_consistency_rate"] == "1"
    assert payload["metrics"]["case_false_positive_rate"] == "0"
    assert all(v["met"] for v in payload["verdicts"])


def test_bench_suite_filter(run):
    """--suite 只跑指定套件（其余指标不参与判定）。"""
    code, out, _ = run("--json", "bench", "--suite", "cases")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["suites_run"] == ["cases"]
    assert "rules" not in payload["suites"]
    assert payload["cases"]["cases_total"] > 0


def test_bench_unknown_suite_exit_2(run):
    """非法套件名 → 退出码 2（用法错误）。"""
    code, _, err = run("bench", "--suite", "nope")
    assert code == EXIT_INPUT
    assert "未知基准套件" in err


def test_bench_unmet_exit_1(run, tmp_path):
    """规则包损坏（公式引用不存在的系数）→ 基准报未达标 → 退出码 1（非 2）。

    退出码 1 与 2 的分工：1 = "仓库状态不健康"（数据坏了 / 门槛未达），
    2 = "用法错了"（suite 名非法 / 门槛配置缺失）。若把前者误报为后者，
    使用者会去查命令行参数，而真正的问题在数据。
    """
    import shutil

    work = tmp_path / "data"
    shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "data"), str(work))
    path = work / "rules" / "ruleset-gbt32150-2025-2024-steel.json"
    pack = jsonio.load(str(path))
    pack["engine"]["formula"]["expr"] = {
        "op": "mul",
        "args": [{"op": "var", "ref": "activity_data"},
                 {"op": "const", "ref": "no_such_coefficient"}],
    }
    jsonio.write(str(path), pack)
    code, out, _ = run("--data-dir", str(work), "bench")
    assert code == EXIT_GATE
    assert "未达标" in out


# ---------- convert ----------

def test_convert_ok(run):
    code, out, _ = run("convert", "--value", "1", "--from", "t", "--to", "kg")
    assert code == EXIT_OK
    assert "1000" in out


def test_convert_cross_dimension_exit_2(run):
    code, _, err = run("convert", "--value", "1", "--from", "t", "--to", "MWh")
    assert code == EXIT_INPUT
    assert "量纲" in err


def test_convert_unknown_unit_exit_2(run):
    code, _, err = run("convert", "--value", "1", "--from", "t", "--to", "stone")
    assert code == EXIT_INPUT


# ---------- rules ----------

def test_rules_without_subcommand_exit_2(run):
    code, _, err = run("rules")
    assert code == EXIT_INPUT
    assert "show" in err or "check" in err


def test_rules_check_reports_scoped_gates(run):
    """M1：门控分作用域；核算路径部分可通过（配额/校核仍 pending）。"""
    code, out, _ = run("rules", "check")
    assert code == EXIT_GATE          # 仍有坐标的核算路径被拦截（2026 发电）
    assert "核算路径可通" in out


def test_rules_show_effective_exit_0(run):
    """M1：核算路径已核对齐全的坐标 → rules show 退出码 0。"""
    code, out, _ = run("rules", "show", "--standard", "gbt32150-2025",
                       "--year", "2024", "--industry", "steel")
    assert code == EXIT_OK
    assert "核算路径门控：通过" in out


def test_rules_show_blocked_exit_1(run):
    """M1：核算路径仍被拦截的坐标（2026 发电，碳氧化率待因子库）→ 退出码 1。"""
    code, out, _ = run("rules", "show", "--standard", "gbt32150-2025",
                       "--year", "2026", "--industry", "power")
    assert code == EXIT_GATE
    assert "拦截" in out


def test_rules_show_unknown_coord_exit_2(run):
    code, _, err = run("rules", "show", "--standard", "gbt32150-2025",
                       "--year", "1999", "--industry", "steel")
    assert code == EXIT_INPUT
    assert "不存在" in err


# ---------- calc / check 门控与端到端 ----------

def test_calc_end_to_end_exit_0(run, profile_file):
    """M2 DoD：核算路径核对齐全的坐标上 calc 输出完整报告（退出码 0）。"""
    code, out, _ = run("calc", "--input", profile_file)
    assert code == EXIT_OK
    assert "排放总量" in out
    assert "示例钢铁" in out
    # 报告头三要素 + 逐源明细 + 因子来源表 + 数据溯源表（plan/04 §6.1）
    assert "报告头" in out and "规则包坐标" in out
    assert "逐排放源明细表" in out
    assert "因子来源表" in out
    assert "数据溯源表" in out


def test_calc_json_has_lines_and_total(run, profile_file):
    code, out, _ = run("--json", "calc", "--input", profile_file)
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["calc"]["line_count"] >= 1
    assert payload["calc"]["total"]
    assert all("emission" in line for line in payload["calc"]["lines"])
    counts = payload["provenance_counts"]
    assert counts["total"] == counts["detail_rows"] + counts["factor_rows"]


def test_calc_diff_standard_emits_boundary_diff(run, profile_file):
    """FR-01.3：带 --diff-standard 时输出双标尺差异。"""
    code, out, _ = run("--json", "calc", "--input", profile_file,
                       "--diff-standard", "gbt32150-2015")
    assert code == EXIT_OK
    diff = json.loads(out)["boundary_diff"]
    assert diff["base"] == "gbt32150-2015/2024/steel"
    assert diff["target"] == "gbt32150-2025/2024/steel"
    assert isinstance(diff["adjusted"], list) and diff["adjusted"]


def test_calc_report_file_written(run, profile_file, tmp_path):
    """FR-06.1：--report 落 Markdown 文件（UTF-8，LF，无 CR）。"""
    out_path = tmp_path / "report.md"
    code, _, _ = run("calc", "--input", profile_file, "--report", str(out_path))
    assert code == EXIT_OK
    raw = out_path.read_bytes()
    assert b"\r" not in raw
    assert "企业温室气体排放核算报告" in raw.decode("utf-8")


# ---------- report（M5 可核证报告导出，FR-06）----------

def test_report_writes_three_formats(run, profile_file, tmp_path):
    """FR-06.1：report 子命令一次落盘 MD + CSV + XLSX 三产物。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, _ = run("report", "--input", profile_file, "--out-dir", str(out_dir))
    assert code == EXIT_OK
    assert (out_dir / "report.md").is_file()
    assert (out_dir / "report.xlsx").is_file()
    assert (out_dir / "逐排放源明细表.csv").is_file()
    assert "溯源完整性" in out


def test_report_markdown_has_all_sections(run, profile_file, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, _, _ = run("report", "--input", profile_file, "--out-dir", str(out_dir),
                     "--format", "md")
    assert code == EXIT_OK
    text = (out_dir / "report.md").read_bytes().decode("utf-8")
    for section in ("报告头", "核算边界", "逐排放源明细表", "因子来源表",
                    "核算过程", "数据质量校核结果", "配额试算", "依据清单", "数据溯源表"):
        assert section in text, "报告缺少章节：%s" % section


def test_report_no_cr_bytes(run, profile_file, tmp_path):
    """NFR-04：**文本**落盘产物一律 LF（无 CR）。XLSX 是 ZIP 二进制，不适用该判据。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    run("report", "--input", profile_file, "--out-dir", str(out_dir))
    text_files = [p for p in out_dir.iterdir() if p.suffix in (".md", ".csv")]
    assert text_files, "未找到文本产物"
    for path in text_files:
        assert b"\r" not in path.read_bytes(), "文本产物含 CR：%s" % path.name


def test_report_with_check_and_quota_sections(run, profile_file, tmp_path):
    """--with-check / --with-quota 追加 §5/§6 章节（各走对应作用域门控）。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, _ = run("report", "--input", profile_file, "--out-dir", str(out_dir),
                       "--with-check", "--with-quota", "--benchmark-value", "2",
                       "--output", "100000")
    assert code == EXIT_OK
    assert "校核章节" in out and "配额章节" in out
    text = (out_dir / "report.md").read_bytes().decode("utf-8")
    assert "免责声明" in text


def test_report_with_quota_missing_external_input_exit_2(run, profile_file, tmp_path):
    """配额章节缺外部输入 → 退出码 2（不得静默取 0 写进报告）。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, _, err = run("report", "--input", profile_file, "--out-dir", str(out_dir),
                       "--with-quota", "--output", "100000")
    assert code == EXIT_INPUT
    assert "外部提供" in err


def test_report_json_lists_files(run, profile_file, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, _ = run("--json", "report", "--input", profile_file,
                       "--out-dir", str(out_dir), "--format", "md")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["formats"] == ["md"]
    assert payload["files"]["md"]


def test_report_unknown_format_exit_2(run, profile_file, tmp_path):
    code, _, err = run("report", "--input", profile_file, "--out-dir", str(tmp_path),
                       "--format", "pdf")
    assert code == EXIT_INPUT
    assert "不支持的报告格式" in err


def test_report_missing_out_dir_exit_2(run, profile_file, tmp_path):
    code, _, err = run("report", "--input", profile_file,
                       "--out-dir", str(tmp_path / "nope"))
    assert code == EXIT_INPUT
    assert "输出目录" in err


def test_report_blocked_by_gate_exit_1(run, tmp_path):
    """核算路径 pending 的坐标（2026 发电）→ 报告导出同样被门控拦截。"""
    path = tmp_path / "power2026.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2026, "industry": "power"},
        "facility": {"name": "示例发电（合成）"},
        "sources": [{"source_id": "stationary_combustion",
                     "activity": {"value": "1000", "unit": "t"}}],
    })
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, _, err = run("report", "--input", str(path), "--out-dir", str(out_dir))
    assert code == EXIT_GATE
    assert "未核对" in err


# ---------- 顶层 --selftest（打包产物验收入口，FR-08.3）----------

def test_top_level_selftest_flag_exit_0(run):
    """`exe --selftest` 等价于 selftest 子命令（PyInstaller 入口无需子命令）。"""
    code, out, _ = run("--selftest")
    assert code == EXIT_OK
    assert "全部通过" in out


def test_top_level_selftest_with_data_dir(run, data_dir):
    code, out, _ = run("--data-dir", data_dir, "--selftest")
    assert code == EXIT_OK
    assert data_dir in out


def test_selftest_reports_report_export_check(run):
    """自检含"报告导出可用（含溯源完整性）"一项（M5 新增验收面）。"""
    code, out, _ = run("selftest")
    assert code == EXIT_OK
    assert "报告导出可用" in out


def test_calc_blocked_by_gate_exit_1(run, tmp_path):
    """核算路径仍 pending 的坐标（2026 发电）→ 门控退出码 1。"""
    path = tmp_path / "power2026.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2026, "industry": "power"},
        "facility": {"name": "示例发电（合成）有限公司"},
        "sources": [{"source_id": "stationary_combustion",
                     "activity": {"value": "1000", "unit": "t"}}],
    })
    code, _, err = run("calc", "--input", str(path))
    assert code == EXIT_GATE
    assert "未核对" in err


def test_calc_missing_required_source_exit_2(run, incomplete_profile_file):
    """缺应核算源活动数据 → 退出码 2（FR-01.4，不得静默按空清单核算）。"""
    code, _, err = run("calc", "--input", incomplete_profile_file)
    assert code == EXIT_INPUT
    assert "缺少" in err


def test_calc_mixed_coordinates_exit_2(run, tmp_path):
    path = tmp_path / "mixed.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "baseline": {"standard": "gbt32150-2015", "year": 2022, "industry": "steel"},
    })
    code, _, err = run("calc", "--input", str(path))
    assert code == EXIT_INPUT
    assert "多个规则包坐标" in err


def test_calc_missing_coordinate_exit_2(run, tmp_path):
    path = tmp_path / "nocoord.json"
    jsonio.write(str(path), {"facility": {"name": "无坐标"}})
    code, _, err = run("calc", "--input", str(path))
    assert code == EXIT_INPUT
    assert "未声明" in err


def test_calc_missing_file_exit_2(run, tmp_path):
    code, _, err = run("calc", "--input", str(tmp_path / "nope.json"))
    assert code == EXIT_INPUT


def test_check_clean_profile_exit_0(run, profile_file):
    """M3：校核层已落地——干净档案输出分级问题清单，无 error → 退出码 0。"""
    code, out, _ = run("check", "--input", profile_file)
    assert code == EXIT_OK
    assert "问题计数" in out
    assert "错误 0" in out


def test_check_error_level_exit_2(run, tmp_path):
    """校核命中 error（选填源录入未知活动数据单位）→ 退出码 2（输入不可用）。"""
    path = tmp_path / "bad_unit.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "坏单位（合成）"},
        "sources": [
            {"source_id": "stationary_combustion",
             "activity": {"value": "1000", "unit": "t"}},
            {"source_id": "process_emission",
             "activity": {"value": "500", "unit": "t"}},
            {"source_id": "carbon_product",
             "activity": {"value": "200", "unit": "t"}},
            {"source_id": "purchased_electricity",
             "activity": {"value": "1000", "unit": "stone"}},
        ],
    })
    code, out, _ = run("check", "--input", str(path))
    assert code == EXIT_INPUT
    assert "Q-UNIT-01" in out


def test_check_baseline_yoy_jump(run, tmp_path):
    """--baseline 提供上一年度档案 → 跨年突变检查执行并命中。"""
    base = tmp_path / "base.json"
    now = tmp_path / "now.json"
    sources = lambda v: [{"source_id": "stationary_combustion",
                          "activity": {"value": v, "unit": "t"}},
                         {"source_id": "process_emission",
                          "activity": {"value": "500", "unit": "t"}},
                         {"source_id": "carbon_product",
                          "activity": {"value": "200", "unit": "t"}}]
    jsonio.write(str(base), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2023, "industry": "steel"},
        "facility": {"name": "基线（合成）"}, "sources": sources("1000")})
    jsonio.write(str(now), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "本期（合成）"}, "sources": sources("5000")})
    code, out, _ = run("check", "--input", str(now), "--baseline", str(base))
    assert "Q-YOY-01" in out


def test_check_json_report(run, profile_file):
    code, out, _ = run("--json", "check", "--input", profile_file)
    assert code == EXIT_OK
    payload = json.loads(out)
    assert "issues" in payload and "counts" in payload


# ---------- quota ----------

def test_quota_benchmark_with_external_factor(run, tmp_path):
    """发电基准法：调峰修正系数（外部输入）由命令行显式给出 → 退出码 0 + 免责声明。"""
    path = tmp_path / "power.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2025, "industry": "power"},
        "facility": {"name": "示例发电（合成）有限公司"},
        "output": {"value": "100000", "unit": "MWh"},
        "sources": [{"source_id": "stationary_combustion",
                     "activity": {"value": "10000", "unit": "t"}}],
    })
    code, out, _ = run("quota", "--input", str(path), "--correction-factor", "1")
    assert code == EXIT_OK
    assert "配额试算结果" in out
    assert "免责声明" in out


def test_quota_missing_external_input_exit_2(run, tmp_path):
    """外部输入缺失（调峰修正系数）→ 退出码 2（不得静默取 1）。"""
    path = tmp_path / "power.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2025, "industry": "power"},
        "facility": {"name": "示例发电（合成）有限公司"},
        "output": {"value": "100000", "unit": "MWh"},
        "sources": [{"source_id": "stationary_combustion",
                     "activity": {"value": "10000", "unit": "t"}}],
    })
    code, _, err = run("quota", "--input", str(path))
    assert code == EXIT_INPUT
    assert "外部提供" in err


def test_quota_json_has_disclaimer_required(run, tmp_path):
    path = tmp_path / "steel.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "示例钢铁（合成）有限公司"},
        "output": {"value": "100000", "unit": "t"},
        "sources": [
            {"source_id": "stationary_combustion",
             "activity": {"value": "100000", "unit": "t"}},
            {"source_id": "process_emission",
             "activity": {"value": "5000", "unit": "t"}},
            {"source_id": "carbon_product",
             "activity": {"value": "2000", "unit": "t"}},
        ],
    })
    code, out, _ = run("--json", "quota", "--input", str(path), "--benchmark-value", "2")
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["disclaimer_required"] is True
    assert payload["method"] == "intensity_coefficient"
    assert payload["allocated"]


# ---------- UTF-8 stdio ----------

def test_ensure_utf8_stdio_idempotent():
    cli._ensure_utf8_stdio()      # 二次调用不得抛错
    cli._ensure_utf8_stdio()


def test_utf8_stdio_handles_cp1252_stream(monkeypatch):
    """复现 CI cp1252 管道：非 UTF-8 流必须被 reconfigure，否则中文输出崩溃。"""
    import io

    class FakeStream(io.TextIOWrapper):
        def __init__(self):
            super().__init__(io.BytesIO(), encoding="cp1252", errors="strict")

    fake_out = FakeStream()
    fake_err = FakeStream()
    monkeypatch.setattr(cli.sys, "stdout", fake_out)
    monkeypatch.setattr(cli.sys, "stderr", fake_err)
    cli._ensure_utf8_stdio()
    assert (fake_out.encoding or "").lower() in ("utf-8", "utf8")
    # 现在写中文必须成功（不再 UnicodeEncodeError）
    fake_out.write("温室气体核算")
