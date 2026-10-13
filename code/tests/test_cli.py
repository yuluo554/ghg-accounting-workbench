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
    path = tmp_path / "profile.json"
    jsonio.write(str(path), {
        "coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "facility": {"name": "示例钢铁（合成）有限公司"},
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


def test_rules_check_all_blocked_exit_1(run):
    """M0 数据初态：全部坐标被拦截 → 退出码 1。"""
    code, out, _ = run("rules", "check")
    assert code == EXIT_GATE
    assert "被拦截" in out


def test_rules_show_blocked_exit_1(run):
    code, out, _ = run("rules", "show", "--standard", "gbt32150-2025",
                       "--year", "2026", "--industry", "steel")
    assert code == EXIT_GATE
    assert "拦截" in out


def test_rules_show_unknown_coord_exit_2(run):
    code, _, err = run("rules", "show", "--standard", "gbt32150-2025",
                       "--year", "1999", "--industry", "steel")
    assert code == EXIT_INPUT
    assert "不存在" in err


# ---------- calc / check 门控 ----------

def test_calc_blocked_by_gate_exit_1(run, profile_file):
    code, _, err = run("calc", "--input", profile_file)
    assert code == EXIT_GATE
    assert "未核对" in err


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


def test_check_blocked_by_gate_exit_1(run, profile_file):
    code, _, err = run("check", "--input", profile_file)
    assert code == EXIT_GATE


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
