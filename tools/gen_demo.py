#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""演示素材生成器（M5）：把界面渲染成 PNG + 生成命令行演示记录。

**为什么用脚本生成而不是手截屏**：
  * 可复跑——界面改了重跑一次即可，不依赖"谁的机器上截的"；
  * 无头可跑——``QT_QPA_PLATFORM=offscreen`` 下 Qt 仍能把窗口渲染进 QImage，
    所以 CI/无显示器机器也能产出素材；
  * 素材与产物同源——截图里的数字就是引擎当时的输出，不会出现"图是旧的、代码是新的"。

产物（默认写 ``docs/demo/``）：
  * ``01-calc.png`` … ``04-bench.png`` —— 四个页签的界面截图；
  * ``demo-cli.txt`` —— 命令行演示记录（含退出码，纯文本便于 diff 与粘贴）。

用法：``py -X utf8 tools/gen_demo.py``（可选 ``--out-dir`` / ``--data-dir``）。
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "code", "src"))
sys.path.insert(0, os.path.join(ROOT, "code", "gui"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: 截图清单：``(页面属性名, 输出文件名, 页签标题)``
SHOTS = (
    ("calc_page", "01-calc.png", "核算"),
    ("check_page", "02-check.png", "校核"),
    ("quota_page", "03-quota.png", "配额"),
    ("bench_page", "04-bench.png", "基准"),
)

#: 候选中文字体（offscreen 下 Qt 找不到系统字体目录，中文会渲染成豆腐块；
#: 显式注册一个可用的 CJK 字体，保证素材里的中文是可读的）
FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/Deng.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


def _register_cjk_font():
    """注册一个可用的中文字体；返回字体族名（找不到返回 ``None``）。"""
    from PySide6.QtGui import QFontDatabase

    for path in FONT_CANDIDATES:
        if not os.path.isfile(path):
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id == -1:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return families[0]
    return None

#: 命令行演示（按顺序执行；退出码一并记录）
CLI_DEMO = (
    ("coords", ["coords"]),
    ("rules show（门控通过）", ["rules", "show", "--standard", "gbt32150-2025",
                                "--year", "2024", "--industry", "steel"]),
    ("rules show（门控拦截）", ["rules", "show", "--standard", "gbt32150-2025",
                                "--year", "2026", "--industry", "power"]),
    ("calc（端到端出数）", ["calc", "--input",
                            "data/truth/profiles/steel-2024.json"]),
    ("check（干净档案）", ["check", "--input",
                           "data/truth/profiles/steel-2024.json"]),
    ("check（坏单位命中 error）", ["check", "--input",
                                   "data/truth/profiles/steel-2024-bad-unit.json"]),
    ("quota（缺外部输入 → rc 2）", ["quota", "--input",
                                    "data/truth/profiles/steel-2024.json"]),
    ("quota（显式给平衡值）", ["quota", "--input",
                               "data/truth/profiles/steel-2024.json",
                               "--benchmark-value", "2"]),
    ("bench（三类基准）", ["bench"]),
    ("selftest", ["selftest"]),
)


def capture_screenshots(out_dir, data_dir):
    """离屏渲染四个页签并抓图；返回写出的路径列表。"""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from ghg_gui.pages import build_window

    app = QApplication.instance() or QApplication([])
    family = _register_cjk_font()
    if family:
        app.setFont(QFont(family))
    else:                                        # pragma: no cover - 视机器字体而定
        sys.stderr.write("警告：未找到可用的中文字体，截图中文可能显示为方块\n")

    # 截图里显示的是相对仓库根的路径（不泄露开发机绝对路径），
    # 故渲染期间把 CWD 固定到仓库根，保证引擎能按该相对路径加载档案。
    previous_cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        window = build_window(data_dir)
        window.resize(1180, 720)

        # 让每个页面都先跑一次，截图里才有真实结果（不是空表格）
        _populate(window, data_dir)
    finally:
        os.chdir(previous_cwd)

    written = []
    for attr, filename, _label in SHOTS:
        page = getattr(window, attr)
        window.tabs.setCurrentWidget(page)
        app.processEvents()
        path = os.path.join(out_dir, filename)
        page.grab().save(path, "PNG")
        written.append(path)
    window.close()
    return written


def _populate(window, data_dir):
    """用内置示例档案把四个页面填上真实结果（截图不得是空表）。

    截图里的档案路径用**仓库相对形式**：演示素材是要发布的产物，原样写绝对路径
    会把开发机路径（``<盘符>:\\<仓库根>\\...``）留在 README 首屏截图里。
    引擎按相对路径解析（生成时 CWD = 仓库根），故结果与绝对路径完全一致。
    """
    steel = os.path.join(data_dir, "truth", "profiles", "steel-2024.json")
    shown = _display(steel)

    window.calc_page.profile_edit.setText(shown)
    window.calc_page.run_action()
    window.calc_page.refresh()

    window.check_page.profile_edit.setText(shown)
    window.check_page.run_action()
    window.check_page.refresh()

    window.quota_page.profile_edit.setText(shown)
    window.quota_page.benchmark_edit.setText("2")
    window.quota_page.output_edit.setText("166150")
    window.quota_page.run_action()
    window.quota_page.refresh()

    window.bench_page.run_action()
    window.bench_page.refresh()


def _sanitize(text):
    """把开发机绝对路径折叠成仓库相对形式（演示素材是要发布的产物）。

    CLI 的 ``selftest`` 会回显数据目录的**绝对路径**；原样落盘会把开发机路径
    （形如 ``<盘符>:\\<仓库根>\\...``）写进发布仓库。这里按仓库根做前缀替换，
    两种斜杠写法都覆盖。
    """
    for root in (ROOT, ROOT.replace("\\", "/")):
        text = text.replace(root + os.sep, "").replace(root + "/", "")
        text = text.replace(root, ".")
    return text


def cli_transcript(out_dir, data_dir):
    """跑一遍命令行演示，把命令、输出与退出码写进文本记录。

    子进程 stdout 在 Windows 上是文本模式，会把 ``\\n`` 翻成 ``\\r\\n``；
    这里统一归一为 LF（NFR-04：文本产物无 CR，便于 diff 与跨平台复现）。
    """
    lines = ["# 命令行演示记录（由 tools/gen_demo.py 生成）",
             "# 数据目录：%s" % _display(data_dir),
             "# 注意：退出码单独记录，不接管道（管道会吞掉真实退出码）",
             ""]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([os.path.join(ROOT, "code", "src")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for title, argv in CLI_DEMO:
        command = [sys.executable, "-X", "utf8", "-m", "ghg.cli",
                   "--data-dir", data_dir] + argv
        proc = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
        output = proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        lines += ["## %s" % title,
                  "$ ghg %s" % " ".join(argv),
                  _sanitize(output).rstrip(),
                  "→ 退出码 %d" % proc.returncode,
                  ""]
    path = os.path.join(out_dir, "demo-cli.txt")
    with open(path, "wb") as fh:
        fh.write(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def _display(path):
    """相对仓库根的展示路径；跨盘符（如临时目录）时回落到绝对路径。"""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成演示素材（截图 + 命令行记录）")
    parser.add_argument("--out-dir", default=os.path.join(ROOT, "docs", "demo"))
    parser.add_argument("--data-dir", default=os.path.join(ROOT, "data"))
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    shots = capture_screenshots(out_dir, args.data_dir)
    transcript = cli_transcript(out_dir, args.data_dir)

    print("演示素材已生成：")
    for path in shots:
        print("  [PNG] %s" % _display(path))
    print("  [TXT] %s" % _display(transcript))
    return 0


if __name__ == "__main__":
    sys.exit(main())