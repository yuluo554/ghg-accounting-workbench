"""零政策字面量门禁测试（NFR-07）—— 含**通道探活**。

探活的意义：M0 数据初态下规则包数值 token 集为空，扫描必然 0 命中——若不配探活，
"门禁通过"可能只是"门禁什么都没扫"。因此这里显式构造一个含数值的规则包，断言
门禁**真的能命中**，再断言真仓库源码 0 命中。
"""

import importlib.util
import os
import sys

from ghg import jsonio
from ghg.rules import RulesIndex

TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools")


def _load_gate_module():
    path = os.path.join(TOOLS_DIR, "check_zero_literals.py")
    spec = importlib.util.spec_from_file_location("ghg_check_zero_literals", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate_module()


def test_gate_module_loads_and_has_marker():
    assert gate.OK_MARKER == "ZERO_LITERAL_GATE_OK"
    assert gate.MIN_TOKEN_LEN >= 2


def test_pattern_matches_whole_token_only():
    pattern = gate._build_pattern(["1000"])
    assert pattern.findall("1000") == ["1000"]
    assert pattern.findall("10000") == []      # 子串不得命中
    assert pattern.findall("11000") == []


def test_scan_detects_injected_token(tmp_path, data_dir):
    """通道探活：注入一个政策数值的规则包 → 门禁必须命中。"""
    # 构造临时数据目录：拷贝最小 manifest + 一个含数值的规则包
    src_rules = os.path.join(data_dir, "rules")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    for name in ("units.json", "manifest.json"):
        with open(os.path.join(src_rules, name), "rb") as fh:
            (rules_dir / name).write_bytes(fh.read())

    coord = RulesIndex.load(data_dir).coordinates()[0]
    pack = RulesIndex.load(data_dir).pack(coord)
    pack["engine"]["coefficients"]["oxidation_rate"]["value"] = 1473
    pack["engine"]["coefficients"]["oxidation_rate"]["status"] = "verified"
    jsonio.write(str(rules_dir / "probe-ruleset.json"), pack)

    manifest = jsonio.load(str(rules_dir / "manifest.json"))
    manifest["coordinates"] = [{
        "standard": coord.standard, "year": coord.year, "industry": coord.industry,
        "file": "probe-ruleset.json", "sha256": "0" * 64,
    }]
    jsonio.write(str(rules_dir / "manifest.json"), manifest)

    tokens = gate.collect_tokens(str(tmp_path))
    assert "1473" in tokens, "探活失败：注入的数值未被采集"

    # 目标源文件里放一个令牌，扫描必须命中
    target_dir = tmp_path / "src"
    target_dir.mkdir()
    probe = target_dir / "probe.py"
    probe.write_text("MAGIC = 1473\n", encoding="utf-8")
    hits = gate.scan(str(tmp_path), str(tmp_path), targets=[str(probe)])
    assert any(h["token"] == "1473" for h in hits), "门禁未命中注入的字面量"


def test_repo_source_is_clean(repo_root, data_dir):
    """真仓库源码必须 0 命中（M0 初态 token 集为空，故天然通过；探活见上）。"""
    hits = gate.scan(repo_root, data_dir)
    assert hits == [], "源码命中政策字面量：%s" % hits


def test_repo_source_clean_when_tokens_present(repo_root, data_dir):
    """即使把 token 集人为放大，源码也不应命中（防"抄进代码的第二份真相"）。"""
    tokens = ["987654", "123456", "555555"]
    hits = gate.scan(repo_root, data_dir, tokens=tokens)
    assert hits == [], "源码命中放大 token 集：%s" % hits
