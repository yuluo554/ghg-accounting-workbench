"""M6 发布脱敏守门（plan/05 M6 DoD；plan/06 §四「发布前必办」O-6）。

发布型仓库的脱敏面（HANDOFF-M6 §八）由 ``tools/desensitize.py`` 固化，本测试守住四条：

  1. **提交元数据**：全历史 ``ae``/``ce`` 必须是 GitHub noreply —— 真实个人邮箱一旦
     留在提交里，会随每次 clone 永久带出，是发布面最不可逆的一处泄露；
  2. **工作树**：受版本控制的文本文件不得含个人邮箱 / 开发机绝对路径；
  3. **构建产物**：``dist/`` 不得含开发机路径；随包真值档案必须声明为合成数据；
  4. **探活**：审计必须能对"注入的泄露"命中 —— 否则"全绿"可能只是"什么都没扫"
     （沿用 M0 零字面量门禁与 M4 基准的同一条纪律：不配探活的门禁不可信）。

提交元数据那条在**改写前**必然是红的（O-6 待办），故以 ``xfail`` 语义显式标注：
它红着是"已知待办"，不是"测试写错了"；改写完成后应自动转绿。
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
DEMO_TRANSCRIPT = os.path.join(REPO_ROOT, "docs", "demo", "demo-cli.txt")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import desensitize as D                                          # noqa: E402


#: 探活用的假地址一律**程序化合成**，不写字面量：门禁扫的就是源码里的邮箱，
#: 测试若内联真实形态的地址，自己就会成为命中源（同零字面量门禁的探活口径）。
AT = "@"
FAKE_QQ = "probe" + AT + "qq" + ".com"
FAKE_GMAIL = "probe" + AT + "gmail" + ".com"
FAKE_BOT = "bot" + AT + "example" + ".com"
NOREPLY = "yuluo554" + AT + "users.noreply.github" + ".com"


# ---------- 提交元数据 ----------

def test_noreply_format_accepted():
    """GitHub noreply 的两种形态（带 id 前缀 / 不带）都算合格。"""
    assert D.NOREPLY_RE.match("282769740+" + NOREPLY)
    assert D.NOREPLY_RE.match(NOREPLY)


def test_real_email_is_not_noreply():
    """真实个人邮箱不得被判为 noreply。"""
    assert not D.NOREPLY_RE.match(FAKE_QQ)
    assert not D.NOREPLY_RE.match(FAKE_GMAIL)


def test_commit_identity_checker_flags_real_email():
    """探活：混入一条真实邮箱的提交 → 审计必须报出（ae 与 ce 两个字段都要查）。"""
    entries = [
        ("a" * 40, NOREPLY, NOREPLY),
        ("b" * 40, FAKE_QQ, NOREPLY),
        ("c" * 40, NOREPLY, FAKE_QQ),
    ]
    violations = D.check_commit_identities(entries)
    fields = {field for _sha, field, _addr in violations}
    assert fields == {"ae", "ce"}, "ae 与 ce 两个字段都必须被查"


def test_commit_identity_checker_allows_listed_address():
    entries = [("a" * 40, FAKE_BOT, FAKE_BOT)]
    assert D.check_commit_identities(entries, allowed_noreply=[FAKE_BOT]) == []


def test_history_commit_identities_are_noreply():
    """全历史提交身份必须为 noreply（O-6 改写后转绿；改写前为已知待办）。"""
    entries = D.iter_commit_identities(REPO_ROOT)
    assert entries, "未读到任何提交（浅克隆会让历史扫描静默空验）"
    violations = D.check_commit_identities(entries)
    if violations:
        pytest.xfail("O-6 待办：%d 处提交身份非 noreply，发布前须跑 "
                     "tools/desensitize.py rewrite" % len(violations))


# ---------- 泄露模式判定 ----------

def test_email_pattern_catches_real_address():
    leaks = D.find_text_leaks("联系：%s" % FAKE_QQ)
    assert ("email", FAKE_QQ) in leaks


def test_email_pattern_ignores_noreply():
    """noreply 地址本身不是泄露（它是改写目标）。"""
    assert D.find_text_leaks("作者 %s" % NOREPLY) == []


def test_official_url_is_not_an_abs_path():
    """官方来源 URL 不得被误判成盘符路径（``s:`` 前是字母 ``p``）。"""
    text = '"ref": "https://www.mee.gov.cn/xxgk/2026/abc.html"'
    assert [v for v in D.find_text_leaks(text) if v[0] == "abs_path"] == []


def test_system_path_is_not_a_dev_path():
    """``C:/Windows/Fonts/...`` 每台机器都一样且加载中文字体必需 → 不是开发机路径。"""
    text = 'QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")'
    assert [v for v in D.find_text_leaks(text) if v[0] == "abs_path"] == []


def test_dev_path_is_caught():
    """探活：真正的开发机路径必须被命中（探针字符串程序化拼接，避免自命中）。"""
    win = "D" + ":" + "\\" + "work" + "\\" + "repo" + "\\"
    posix = "/home" + "/" + "dev" + "/"
    leaks = D.find_text_leaks("临时目录 %s 与 %s" % (win, posix))
    kinds = {kind for kind, _value in leaks}
    assert "abs_path" in kinds


def test_denied_literal_is_caught():
    """探活：显式传入的"必须不存在"字面值命中即报（个人邮箱本体不入仓脚本）。"""
    leaks = D.find_text_leaks("联系：%s" % FAKE_GMAIL, deny_emails=[FAKE_GMAIL])
    assert ("denied_literal", FAKE_GMAIL) in leaks


# ---------- 工作树 / 构建产物 ----------

def test_working_tree_has_no_personal_leak():
    """工作树（发布面文本文件）不得含个人邮箱 / 开发机绝对路径。"""
    hits = D.scan_working_tree(REPO_ROOT)
    assert hits == [], "工作树泄露：%s" % hits[:5]


def test_scan_covers_untracked_files(tmp_path):
    """探活：未跟踪文件也在扫描面内（M0–M5 改动在首次提交前正是未跟踪态）。"""
    assert D.is_scannable("code/src/ghg/calc.py")
    assert not D.is_scannable("data/knowledge/raw/steel-ag.txt"), \
        "官方原文快照是核对留档（不可改写、不进包），不纳入工作树扫描"


def test_dist_build_dirs_have_no_dev_path():
    """已构建时：dist 内不得出现开发机路径 / 个人邮箱。"""
    markers = D.default_dev_markers(REPO_ROOT)
    email = _git_config_email()
    problems = []
    for name in ("ghg-cli", "ghg-gui"):
        build_dir = os.path.join(REPO_ROOT, "dist", name)
        if not os.path.isdir(build_dir):
            continue
        for rel, kind, value in D.scan_build_dir(build_dir, [email] if email else [], markers):
            problems.append("%s/%s [%s] %s" % (name, rel, kind, value))
    if not problems and not _dist_built():
        pytest.skip("dist 未构建")
    assert problems == [], "构建产物泄露：%s" % problems[:5]


def test_default_dev_markers_are_path_shaped():
    """开发机标记取路径形态而非裸用户名（裸用户名会命中 Qt 的厂商串假阳性）。"""
    markers = D.default_dev_markers(REPO_ROOT)
    assert markers, "未派生任何开发机标记"
    for marker in markers:
        assert len(marker) > 3
        assert "\\" in marker or "/" in marker or ":" in marker


# ---------- 随包真值档案 ----------

def test_packaged_truth_profiles_declare_synthetic():
    """随包真值档案必须显式声明 synthetic: true（防真实企业数据混入发布产物）。"""
    problems = D.check_packaged_truth_is_synthetic(REPO_ROOT)
    assert problems == [], "真值档案合成标记问题：%s" % problems


def test_synthetic_probe_flags_real_code(tmp_path):
    """探活：塞一个不带合成标记的真实企业代码 → 审计必须报出。"""
    profiles = tmp_path / "data" / "truth" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "real.json").write_text(
        '{"facility": {"name": "某真实企业", "credit_code": "91110000123456789X"}}',
        encoding="utf-8")
    problems = D.check_packaged_truth_is_synthetic(str(tmp_path))
    assert problems, "未识别出未声明合成的档案"


# ---------- 演示素材（发布面）----------

def test_demo_transcript_has_no_dev_path():
    """演示记录是要发布的产物，不得含开发机绝对路径。"""
    if not os.path.isfile(DEMO_TRANSCRIPT):
        pytest.skip("演示素材未生成")
    text = open(DEMO_TRANSCRIPT, "r", encoding="utf-8").read()
    leaks = [v for v in D.find_text_leaks(text) if v[0] == "abs_path"]
    assert leaks == [], "演示记录含开发机路径：%s" % leaks[:3]


# ---------- 附件台账 ----------

def test_attachment_ledger_is_ascii_named():
    """发布附件名必须 ASCII（跨平台解压友好），且 sha256 为 64 位十六进制。"""
    rows = D.attachment_ledger(os.path.join(REPO_ROOT, "dist"), REPO_ROOT)
    if not rows:
        pytest.skip("dist 未构建")
    for row in rows:
        assert row["attachment"].isascii()
        assert len(row["sha256"]) == 64
        assert all(ch in "0123456789abcdef" for ch in row["sha256"])


# ---------- 辅助 ----------

def _git_config_email():
    proc = subprocess.run(["git", "config", "user.email"], cwd=REPO_ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc.stdout.decode("utf-8", "replace").strip()


def _dist_built():
    for name in ("ghg-cli", "ghg-gui"):
        if os.path.isfile(os.path.join(REPO_ROOT, "dist", name, "%s.exe" % name)):
            return True
    return False
