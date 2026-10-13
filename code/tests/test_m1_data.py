"""M1 数据先行测试：官方核对态、因子库台账、合成真值双路对账、生成器位级一致。

对账的思想（双路独立实现）：
  * 真值由 ``tools/gen_synthetic.py`` 按规则包**直接算式**算出并落盘（真相源）；
  * 引擎 ``ghg.calc`` 走**表达式树求值**路径（另一份实现）；
  两者对同一档案必须逐源一致——任何一路算错都会在此暴露（09 参考项目实证问题）。
"""

import hashlib
import os
import subprocess
import sys

import pytest

from ghg import jsonio
from ghg.calc import compute
from ghg.errors import MixedCoordinateError
from ghg.rules import RulesIndex, SCOPE_CALC
from ghg.units import UnitTable


@pytest.fixture(scope="session")
def truth(data_dir):
    return jsonio.load(os.path.join(data_dir, "truth", "expected.json"))


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ---------- 官方核对态 ----------

def test_standard_metadata_verified(rules_index):
    """通则元数据已挂官方原文核对（日期 / 代替关系 / 有效性）。"""
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    std = rules_index.pack(coord)["standard"]
    assert std["status"] == "verified"
    assert std["published"] == "2025-12-31"
    assert std["effective"] == "2026-07-01"
    assert std["supersedes"] == "GB/T 32150-2015"
    assert std["validity"] == "现行"
    assert std["clause"]["article"]

    old = rules_index.pack(rules_index.resolve("gbt32150-2015", 2024, "steel"))["standard"]
    assert old["status"] == "verified"
    assert old["validity"] == "废止"


def test_boundary_sources_verified_with_real_clauses(rules_index):
    """排放源纳入判定已核对：四行业各至少一条 required=True，且带真实条款与差异标记。"""
    seen_required = {}
    for coord in rules_index.coordinates():
        pack = rules_index.pack(coord)
        for src in pack["boundary"]["sources"]:
            assert src["status"] == "verified", "%s.%s 排放源未核对" % (coord.key, src["id"])
            assert src["clause"]["article"], "%s.%s 缺条款号" % (coord.key, src["id"])
            assert src["delta_vs_2015"] in ("same", "added", "removed", "adjusted")
            if src["required"]:
                seen_required[coord.industry] = True
    assert set(seen_required) == {"power", "steel", "cement", "aluminum"}


def test_calc_path_evidence_present(rules_index):
    """核算路径关键块（公式 / 因子 / 标准）在可通过坐标上均为 verified。"""
    effective = [c for c in rules_index.coordinates()
                 if rules_index.gate_report(c, scope=SCOPE_CALC)["effective"]]
    assert effective
    for coord in effective:
        pack = rules_index.pack(coord)
        assert pack["engine"]["formula"]["status"] == "verified"
        assert pack["factors"]["industry_default_values"]["default_factor"]["status"] == "verified"
        assert pack["standard"]["status"] == "verified"


# ---------- 因子库台账 ----------

def test_factor_ledger_records_source_and_access(data_dir):
    ledger = jsonio.load(os.path.join(data_dir, "factors", "manifest.json"))
    assert ledger["schema"] == "ghg-factor-ledger/v1"
    src = ledger["sources"][0]
    assert src["id"] == "mee-factor-db-v2"
    assert src["released"] == "2026-03-01"
    assert src["entry_url"].startswith("https://data.ncsc.org.cn")
    # WAF 阻断已如实登记（不编造因子数值）
    assert src["access_status"] == "blocked_waf_http_412"
    assert src["entries"] == []


# ---------- 合成真值：双路对账 ----------

def test_truth_covers_four_industries(truth):
    industries = {v["coordinate"].split("/")[2] for v in truth["profiles"].values()}
    assert industries == {"power", "steel", "cement", "aluminum"}


def test_engine_matches_truth_for_every_profile(data_dir, truth):
    """双路对账：引擎（表达式树）逐源 + 汇总必须与真值库（直接算式）一致。"""
    from ghg.coordinates import parse_coordinate
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    for name, expected in sorted(truth["profiles"].items()):
        profile = jsonio.load(os.path.join(data_dir, "truth", expected["file"]))
        coord = parse_coordinate(profile["coordinate"], index=index)
        pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
        result = compute(profile, coord, pack, units)
        got_total = result["total_raw"]
        assert got_total == expected["total"], "%s 汇总不一致：%s != %s" % (
            name, got_total, expected["total"])
        by_id = {line["source_id"]: line for line in result["lines"]}
        for exp_line in expected["lines"]:
            got = by_id[exp_line["source_id"]]
            from ghg.decimals import as_decimal
            assert as_decimal(got["emission_raw"]) == as_decimal(exp_line["emission"]), \
                "%s.%s 逐源不一致" % (name, exp_line["source_id"])


def test_profile_sha256_matches_truth(data_dir, truth):
    """真值库登记的档案 sha256 与实际文件一致（防"改了档案忘改真值"）。"""
    for name, expected in truth["profiles"].items():
        path = os.path.join(data_dir, "truth", expected["file"])
        assert _sha256(path) == expected["sha256"], "%s 档案 sha256 失配" % name


def test_synthetic_profiles_are_fictional(data_dir, truth):
    """假企业白名单：全部合成档案标注 synthetic 且名称含「（合成）」。"""
    for name, expected in truth["profiles"].items():
        profile = jsonio.load(os.path.join(data_dir, "truth", expected["file"]))
        assert profile["facility"]["synthetic"] is True
        assert "（合成）" in profile["facility"]["name"]


# ---------- 边界用例 ----------

def test_missing_required_source_raises(data_dir, truth):
    from ghg.coordinates import parse_coordinate
    from ghg.errors import BoundaryError
    case = truth["cases"]["missing_required_source"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    index = RulesIndex.load(data_dir)
    units = UnitTable.load(data_dir)
    coord = parse_coordinate(profile["coordinate"], index=index)
    pack = index.effective_ruleset(coord, scope=SCOPE_CALC)
    with pytest.raises(BoundaryError) as exc:
        compute(profile, coord, pack, units)
    assert case["missing_source_id"] in str(exc.value)


def test_mixed_coordinates_case_raises(data_dir, truth):
    from ghg.rules import parse_payload_coordinate
    case = truth["cases"]["mixed_coordinates"]
    profile = jsonio.load(os.path.join(data_dir, "truth", case["file"]))
    index = RulesIndex.load(data_dir)
    with pytest.raises(MixedCoordinateError):
        parse_payload_coordinate(profile, index=index)


# ---------- 生成器位级一致 ----------

def _run_generator(repo_root, script, work_dir):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(repo_root, script),
         "--data-dir", str(work_dir)],
        cwd=repo_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


@pytest.mark.parametrize("script", [
    os.path.join("tools", "gen_rulesets.py"),
    os.path.join("tools", "gen_factors.py"),
    os.path.join("tools", "gen_knowledge.py"),
    os.path.join("tools", "gen_synthetic.py"),
])
def test_generators_zero_cr_bytes(repo_root, script):
    """生成的产物不得含 CR 字节（EOL 门的一部分，覆盖 rules/factors/truth/knowledge）。"""
    for sub in ("rules", "factors", "truth", "knowledge"):
        base = os.path.join(repo_root, "data", sub)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                raw = open(os.path.join(dirpath, fname), "rb").read()
                assert b"\r" not in raw, "冻结产物含 CR：%s" % os.path.join(dirpath, fname)


def test_synthetic_regeneration_is_bitwise_identical(repo_root, tmp_path):
    """四生成器链式重跑（rules → factors → knowledge → synthetic）→ 逐份 sha256 与仓库一致。"""
    work = tmp_path / "gen"
    work.mkdir()
    for script in ("gen_rulesets.py", "gen_factors.py", "gen_knowledge.py", "gen_synthetic.py"):
        _run_generator(repo_root, os.path.join("tools", script), work)

    for sub in ("rules", "factors", "truth", "knowledge"):
        repo_base = os.path.join(repo_root, "data", sub)
        if not os.path.isdir(repo_base):
            continue
        for dirpath, _dirs, files in os.walk(repo_base):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), repo_base)
                other = os.path.join(str(work), sub, rel)
                assert os.path.isfile(other), "重生成缺少 %s/%s" % (sub, rel)
                assert _sha256(os.path.join(dirpath, fname)) == _sha256(other), \
                    "字节漂移：%s/%s" % (sub, rel)


def test_no_stdlib_random_in_generators(repo_root):
    """确定性纪律：生成器禁 stdlib random / 禁系统时钟。"""
    for script in ("gen_rulesets.py", "gen_factors.py", "gen_knowledge.py", "gen_synthetic.py"):
        path = os.path.join(repo_root, "tools", script)
        text = open(path, "r", encoding="utf-8").read()
        assert "import random" not in text, "%s 使用了 stdlib random" % script
        assert "from random" not in text, "%s 使用了 stdlib random" % script


def test_knowledge_clause_index_covers_all_sources(data_dir):
    """条款库：全部快照在位，且 sha256 与文件一致。"""
    index = jsonio.load(os.path.join(data_dir, "knowledge", "clauses.json"))
    assert index["schema"] == "ghg-clause-index/v1"
    assert len(index["sources"]) >= 10
    total = 0
    for src in index["sources"]:
        assert src["clauses"], "%s 缺条款要点" % src["id"]
        for snap in src["snapshot_files"]:
            assert snap["present"], "快照缺失：%s" % snap["file"]
            path = os.path.join(data_dir, "knowledge", "raw", snap["file"])
            assert _sha256(path) == snap["sha256"], "快照 sha256 失配：%s" % snap["file"]
            total += 1
    assert total >= 15
