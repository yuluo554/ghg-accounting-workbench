"""M5 演示素材守门（plan/05 M5 DoD：「演示 GIF/截图入 docs/demo/」）。

素材由 ``tools/gen_demo.py`` 生成（离屏渲染 + 命令行记录），本测试守住三件事：

  1. **素材在位且非空**——DoD 要求的演示物确实进了仓库，不是"计划里写了"；
  2. **命令行记录含真实退出码谱**——演示的价值在于展示门控/失败路径，
     若只有 rc 0，说明演示跑的是"一路顺风"的假路径；
  3. **生成器可复跑**——素材是可再生的（换了界面重跑一次即可），
     而不是"某台机器上截的、再也做不出来"。

截图是二进制且依赖字体渲染，**不做字节比对**（不同机器字体不同是正常的）；
守的是"能生成、非空、尺寸合理"。
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO_DIR = os.path.join(REPO_ROOT, "docs", "demo")
GEN_SCRIPT = os.path.join(REPO_ROOT, "tools", "gen_demo.py")

SCREENSHOTS = ("01-calc.png", "02-check.png", "03-quota.png", "04-bench.png")
TRANSCRIPT = "demo-cli.txt"

#: 截图最小字节数（纯白空图约 1-2 KB；有内容的中文界面远大于此）
MIN_PNG_BYTES = 4096

#: 演示必须覆盖的退出码谱（门控拦截 1 / 输入不可用 2 都要出现）
REQUIRED_EXIT_CODES = ("→ 退出码 0", "→ 退出码 1", "→ 退出码 2")


def test_demo_dir_exists():
    assert os.path.isdir(DEMO_DIR), "缺少 docs/demo/（plan/05 M5 DoD 要求）"


@pytest.mark.parametrize("name", SCREENSHOTS)
def test_screenshot_present_and_non_trivial(name):
    path = os.path.join(DEMO_DIR, name)
    assert os.path.isfile(path), "缺少演示截图：%s" % name
    size = os.path.getsize(path)
    assert size >= MIN_PNG_BYTES, "截图疑似空白（%d 字节）：%s" % (size, name)
    with open(path, "rb") as fh:
        assert fh.read(8) == b"\x89PNG\r\n\x1a\n", "不是合法 PNG：%s" % name


def test_cli_transcript_present_and_covers_exit_codes():
    path = os.path.join(DEMO_DIR, TRANSCRIPT)
    assert os.path.isfile(path), "缺少命令行演示记录：%s" % TRANSCRIPT
    text = open(path, "r", encoding="utf-8").read()
    for marker in REQUIRED_EXIT_CODES:
        assert marker in text, "命令行演示缺退出码谱：%s" % marker
    assert "$ ghg bench" in text
    assert "$ ghg selftest" in text


def test_cli_transcript_has_no_cr():
    """演示记录是文本产物，同样守 LF（无 CR）。"""
    raw = open(os.path.join(DEMO_DIR, TRANSCRIPT), "rb").read()
    assert b"\r" not in raw


def test_gen_demo_script_present_and_offscreen():
    """生成器必须显式 offscreen（否则无显示器机器上跑不出来）。"""
    text = open(GEN_SCRIPT, "r", encoding="utf-8").read()
    assert "offscreen" in text
    assert "docs" in text and "demo" in text


def test_gen_demo_is_rerunnable(tmp_path):
    """生成器可复跑：指向临时目录重跑一次必须成功并产出同样清单。

    PySide6 属 ``gui`` extra；未安装时跳过（素材本身已在仓库里，由上面的用例守住）。
    """
    pytest.importorskip("PySide6", reason="重新生成素材需要 PySide6（gui extra）")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", GEN_SCRIPT, "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
    produced = sorted(os.listdir(str(tmp_path)))
    for name in SCREENSHOTS + (TRANSCRIPT,):
        assert name in produced, "重跑未产出：%s" % name