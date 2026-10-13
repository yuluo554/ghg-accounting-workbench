"""冻结产物守门（NFR-04 / 字节冻结分层设防）。

三条独立守门：
  1. **无 CR**：data/ 下所有文本产物不得含 CR 字节（Windows 默认 CRLF 漂移会打挂
     跨机器复现，`.gitattributes` 只管检出/提交、不管脚本怎么写文件）；
  2. **位级一致**：临时目录重生成 → 逐份 sha256 与仓库现值一致；
  3. **manifest 对账**：manifest 内登记的 sha256 与文件实际 sha256 一致（防"改了文件忘改台账"）。
"""

import hashlib
import os
import subprocess
import sys

from ghg import jsonio

GENERATOR = os.path.join("tools", "gen_rulesets.py")


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _rules_files(rules_dir):
    return sorted(f for f in os.listdir(rules_dir) if f.endswith(".json"))


# ---------- 1. 无 CR ----------

def test_frozen_data_has_no_cr_bytes(data_dir):
    rules_dir = os.path.join(data_dir, "rules")
    offenders = []
    for name in _rules_files(rules_dir):
        raw = open(os.path.join(rules_dir, name), "rb").read()
        if b"\r" in raw:
            offenders.append(name)
    assert offenders == [], "冻结产物含 CR（EOL 门失败）：%s" % offenders


# ---------- 2. 位级一致（重生成）----------

def test_regeneration_is_bitwise_identical(repo_root, tmp_path):
    work = tmp_path / "gen"
    work.mkdir()
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(repo_root, GENERATOR),
         "--data-dir", str(work)],
        cwd=repo_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")

    repo_rules = os.path.join(repo_root, "data", "rules")
    gen_rules = os.path.join(str(work), "rules")
    repo_files = _rules_files(repo_rules)
    gen_files = _rules_files(gen_rules)
    assert repo_files == gen_files, "生成文件清单与仓库不一致"

    for name in repo_files:
        assert _sha256(os.path.join(repo_rules, name)) == \
            _sha256(os.path.join(gen_rules, name)), "文件字节漂移：%s" % name


# ---------- 3. manifest 对账 ----------

def test_manifest_sha256_matches_files(data_dir):
    rules_dir = os.path.join(data_dir, "rules")
    manifest = jsonio.load(os.path.join(rules_dir, "manifest.json"))
    assert len(manifest["coordinates"]) == 40
    for item in manifest["coordinates"]:
        path = os.path.join(rules_dir, item["file"])
        assert os.path.isfile(path), "manifest 指向的文件缺失：%s" % item["file"]
        assert _sha256(path) == item["sha256"], "manifest sha256 失配：%s" % item["file"]
    units_path = os.path.join(rules_dir, manifest["units_file"]["file"])
    assert _sha256(units_path) == manifest["units_file"]["sha256"]


def test_manifest_coordinates_are_full_cartesian(data_dir):
    rules_dir = os.path.join(data_dir, "rules")
    manifest = jsonio.load(os.path.join(rules_dir, "manifest.json"))
    got = {(i["standard"], i["year"], i["industry"]) for i in manifest["coordinates"]}
    expected = {(s, y, i)
                for s in manifest["standards"]
                for y in manifest["years"]
                for i in manifest["industries"]}
    assert got == expected
