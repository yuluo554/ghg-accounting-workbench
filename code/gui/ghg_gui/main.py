"""桌面应用入口（PyInstaller 冻结态的 GUI exe 入口）。

用法：

  * 源码态：``py -X utf8 -m ghg_gui.main``（需 ``PYTHONPATH=code/src:code/gui``）；
  * 冻结态：``ghg-gui.exe``（由 ``tools/ghg_gui.spec`` 打包）。

参数与 CLI 对齐（``--data-dir`` 覆盖数据目录、``--selftest`` 无窗口自检），
**判定逻辑一律不在此**——自检复用 :mod:`ghg.cli` 的 ``selftest`` 子命令。
"""

import sys


def _selftest(argv):
    """无窗口自检（打包验收用）：直接复用 CLI 的 selftest 实现，避免第二套自检。

    ``--data-dir`` / ``--json`` 需连值一起透传（只筛开关会漏掉 ``--data-dir`` 的路径值）。
    """
    forwarded = []
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--data-dir" and idx + 1 < len(argv):
            forwarded += ["--data-dir", argv[idx + 1]]
            idx += 2
            continue
        if arg == "--json":
            forwarded.append("--json")
        idx += 1
    from ghg.cli import main as cli_main
    return cli_main(["--selftest"] + forwarded)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--selftest" in argv:
        return _selftest(argv)

    data_dir = None
    if "--data-dir" in argv:
        idx = argv.index("--data-dir")
        if idx + 1 < len(argv):
            data_dir = argv[idx + 1]

    from PySide6.QtWidgets import QApplication

    from .pages import build_window

    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = build_window(data_dir=data_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())