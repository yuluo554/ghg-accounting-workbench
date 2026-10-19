"""M5 打包白名单与冻结态断言（FR-08.3）。

三条纪律：

1. **白名单显式**：随 exe 分发的 ``data/**`` 必须是 ``tools/ghg_packaging.py`` 里
   显式登记的清单——不是"整个 data/ 拷进去"。新增数据目录必须登记，
   否则 ``assert_whitelist_clean`` 直接失败（本测试锁定这条）。
2. **排除项生效**：``data/knowledge/raw/`` 是官方原文核对留档（约 11 MB），
   不是运行时依赖，不得进包（整树拷贝会让发布包无谓膨胀）。
3. **定位标记完整**：白名单必须让 ``data/rules/manifest.json`` 落在
   ``<包>/data/rules/`` 下——``find_data_dir`` 就是靠这个标记定位的；
   若把目录树拍平到 ``data/``，冻结态 exe 会找不到数据（M5 实测踩过）。

PyInstaller 属 ``build`` extra；未安装时跳过与真实打包相关的用例（其余断言仍执行）。
"""

import os
import sys

import pytest

TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import ghg_packaging as P                                        # noqa: E402


# ---------- 白名单内容 ----------

def test_data_whitelist_covers_runtime_needs():
    """运行时必需的四类数据都在白名单里（规则包 / 因子台账 / 真值库 / 条款索引）。"""
    rels = {rel for rel, _purpose in P.DATA_WHITELIST}
    assert "rules" in rels
    assert "factors" in rels
    assert "truth" in rels
    assert "knowledge/clauses.json" in rels


def test_data_whitelist_entries_carry_purpose():
    """每条白名单都必须写明运行时用途（"为什么进包"要能一句话答上来）。"""
    for rel, purpose in P.DATA_WHITELIST:
        assert purpose and len(purpose) >= 4, "白名单项 %s 缺用途说明" % rel


def test_raw_snapshots_are_excluded():
    """官方原文快照（约 11 MB）是核对留档，非运行时依赖 → 不进包。"""
    assert "knowledge/raw" in P.DATA_EXCLUDE
    rels = {rel for rel, _purpose in P.DATA_WHITELIST}
    assert not any(rel.startswith("knowledge/raw") for rel in rels)


def test_whitelist_clean_against_repo(data_dir):
    """仓库 data/ 下不得存在未登记目录（新增数据目录必须显式登记）。"""
    assert P.assert_whitelist_clean() is True


def test_whitelist_clean_rejects_unregistered_dir(tmp_path):
    """探活：塞一个未登记的 data 子目录 → 自检必须报错（否则白名单形同虚设）。"""
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    (data / "surprise").mkdir()
    with pytest.raises(RuntimeError) as excinfo:
        P.assert_whitelist_clean(str(tmp_path))
    assert "surprise" in str(excinfo.value)


# ---------- datas 布局（冻结态定位标记）----------

def test_data_datas_preserves_directory_tree():
    """目录源必须保持相对路径，不得拍平（否则 rules/manifest.json 定位标记丢失）。"""
    datas = P.data_datas()
    by_dest = {dest.replace("\\", "/"): src for src, dest in datas}
    assert "data/rules" in by_dest
    assert "data/truth" in by_dest
    # 条款库是**文件源**：目标是其所在目录，文件名由 PyInstaller 追加
    assert "data/knowledge" in by_dest


def test_data_datas_sources_exist():
    for src, _dest in P.data_datas():
        assert os.path.exists(src), "白名单源不存在：%s" % src


def test_data_datas_manifest_marker_is_reachable():
    """关键不变量：``data/rules/manifest.json`` 必须能从 datas 目标推出。"""
    datas = dict((dest.replace("\\", "/"), src) for src, dest in P.data_datas())
    rules_src = datas["data/rules"]
    assert os.path.isfile(os.path.join(rules_src, "manifest.json"))


def test_data_datas_missing_source_raises(tmp_path):
    with pytest.raises(RuntimeError):
        P.data_datas(str(tmp_path))


# ---------- pathex / 隐藏导入 ----------

def test_code_pathex_points_at_both_packages(repo_root):
    paths = [p.replace("\\", "/") for p in P.code_pathex(repo_root)]
    assert any(p.endswith("code/src") for p in paths)
    assert any(p.endswith("code/gui") for p in paths)


def test_gui_hidden_imports_declared():
    """GUI 入口在函数内 import PySide6，spec 静态分析看不到 → 必须显式声明。"""
    assert any(name.startswith("PySide6.QtWidgets") for name in P.GUI_HIDDEN_IMPORTS)


def test_exe_names_are_ascii():
    """发布产物名必须 ASCII（Release 附件名与跨平台解压友好）。"""
    for name in (P.CLI_EXE_NAME, P.GUI_EXE_NAME):
        assert name.isascii()


# ---------- 规格文件 ----------

def test_spec_files_present_and_reference_packaging():
    for name in ("ghg_cli.spec", "ghg_gui.spec"):
        path = os.path.join(TOOLS_DIR, name)
        assert os.path.isfile(path), "缺少打包规格：%s" % name
        text = open(path, "r", encoding="utf-8").read()
        assert "ghg_packaging" in text, "%s 未引用白名单单一真相源" % name
        assert "data_datas" in text, "%s 未使用白名单 datas" % name


def test_cli_spec_excludes_gui_stack():
    """CLI 形态不该带 PySide6（13 MB vs 101 MB，实测差 88 MB）。"""
    text = open(os.path.join(TOOLS_DIR, "ghg_cli.spec"), "r", encoding="utf-8").read()
    assert "PySide6" in text          # 出现在 excludes 里
    assert "excludes=" in text


def test_gui_spec_console_disabled():
    """GUI 形态不得弹控制台窗口。"""
    text = open(os.path.join(TOOLS_DIR, "ghg_gui.spec"), "r", encoding="utf-8").read()
    assert "console=False" in text


def test_build_extra_pins_modern_pyinstaller():
    """打包 extra 钉 PyInstaller 6.x，且不再需要 ``setuptools<81``。

    规格变更（v0.1.1，2026-10-19）：原断言要求 ``setuptools<81``，起因是 PyInstaller
    5.x 仍 ``import pkg_resources``（setuptools 81 起移除该模块）。PyInstaller 6.x
    已不再依赖 ``pkg_resources``，故 build extra 统一为 ``pyinstaller>=6.22,<7``，
    并把 ``setuptools<81`` 这条全局降级去掉——留着它反而会压低构建工具版本。
    实测（py3.12 + PyInstaller 6.22.3 + PySide6 6.12.0）：两个 spec 均构建成功、
    双 exe ``--selftest`` rc 0。这条仍是**正向断言**：pin 丢了或退回 5.x 都会失败。
    """
    pyproject = os.path.join(P.repo_root(), "code", "pyproject.toml")
    text = open(pyproject, "r", encoding="utf-8").read()
    build_line = [ln for ln in text.splitlines()
                  if ln.startswith("build =")][0]
    assert "pyinstaller>=6.22,<7" in build_line, \
        "build extra 未钉 PyInstaller 6.22：%s" % build_line
    assert "setuptools<81" not in text, \
        "PyInstaller 6.x 不再需要 setuptools<81，该降级应移除"


# ---------- 真实打包产物（可选：已构建时校验）----------

def _dist_exe(name):
    root = P.repo_root()
    return os.path.join(root, "dist", name, "%s.exe" % name)


def _dist_data_candidates(exe_name):
    """dist 内数据目录的候选位置（按 PyInstaller 版本）。

    PyInstaller 5 把 datas 放在 ``<exe_dir>/data``；PyInstaller 6 起统一放进
    ``<exe_dir>/_internal/data``。``ghg.paths._frozen_candidates`` 两处都查，
    故断言也要覆盖两种布局——只认旧布局会让 PyInstaller 6 的产物**假通过/假失败**。
    """
    exe_dir = os.path.dirname(_dist_exe(exe_name))
    return [os.path.join(exe_dir, "data"),
            os.path.join(exe_dir, "_internal", "data")]


@pytest.mark.parametrize("exe_name", [P.CLI_EXE_NAME, P.GUI_EXE_NAME])
def test_built_exe_has_data_inside_dist(exe_name):
    """已构建时：dist 内必须含 data/rules/manifest.json（冻结态定位标记）。"""
    exe = _dist_exe(exe_name)
    if not os.path.isfile(exe):
        pytest.skip("未构建 %s（先跑 py -m PyInstaller tools/%s.spec）" % (exe_name, exe_name))
    markers = [os.path.join(d, "rules", "manifest.json") for d in _dist_data_candidates(exe_name)]
    assert any(os.path.isfile(m) for m in markers), \
        "dist 内缺定位标记（查过 %s）" % "、".join(markers)


def test_built_exe_data_excludes_raw_snapshots():
    """已构建时：dist 内不得出现 knowledge/raw（核对留档不进包）。"""
    for exe_name in (P.CLI_EXE_NAME, P.GUI_EXE_NAME):
        exe = _dist_exe(exe_name)
        if not os.path.isfile(exe):
            continue
        for data_dir in _dist_data_candidates(exe_name):
            raw_dir = os.path.join(data_dir, "knowledge", "raw")
            assert not os.path.isdir(raw_dir), "dist 含官方原文快照：%s" % raw_dir


def test_built_exe_selftest_exit_0():
    """已构建时：``exe --selftest`` 必须退出码 0（含"数据目录在 dist 内"断言）。"""
    import subprocess
    exe = _dist_exe(P.CLI_EXE_NAME)
    if not os.path.isfile(exe):
        pytest.skip("未构建 CLI exe")
    proc = subprocess.run([exe, "--selftest"], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert "冻结态数据目录在 exe 目录内" in out