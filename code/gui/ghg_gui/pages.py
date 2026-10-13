"""Qt 页面控件（PySide6）—— **只渲染视图模型，控件内零判定逻辑**（FR-08.2）。

每个页面 = 一个 :class:`~ghg_gui.models.ViewModel` + 一组控件：
  * ``_Page`` 提供「输入区 + 运行按钮 + 状态摘要 + 结果表格」的通用骨架；
  * 具体页面只实现"取输入 → 调视图模型 → 把行塞进表格"三件事。

**导入门禁**（``test_m5_gui.py`` 锁定）：本模块只 import ``ghg_gui.models`` /
``ghg_gui.service``，不得直接 import ``ghg.calc`` / ``ghg.quality`` / ``ghg.quota`` /
``ghg.bench``——那意味着界面里长出了第二套引擎调用面。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import (
    BenchPageModel,
    CalcPageModel,
    CheckPageModel,
    QuotaPageModel,
    STATUS_FAIL,
    STATUS_OK,
)

# 文件对话框过滤器（档案为 JSON）
PROFILE_FILTER = "企业档案 JSON (*.json);;全部文件 (*)"

# 状态配色（仅视觉，不含判定）
_COLOR_OK = "#1a7f37"
_COLOR_FAIL = "#b42318"


class _Page(QWidget):
    """页面骨架：输入区 + 运行按钮 + 状态摘要 + 结果表格 + 可选输出区。"""

    def __init__(self, model, service, parent=None):
        super().__init__(parent)
        self.model = model
        self.service = service

        self._layout = QVBoxLayout(self)
        self._form = QFormLayout()
        self._layout.addLayout(self._form)

        self._controls = QHBoxLayout()
        self._layout.addLayout(self._controls)

        self.status_label = QLabel("就绪")
        self.status_label.setWordWrap(True)
        self._layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 0, self)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._layout.addWidget(self.table)

        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setVisible(False)
        self._layout.addWidget(self.output)

        self._build()

    # ---- 子类实现 ----
    def _build(self):                      # pragma: no cover - 子类覆盖
        pass

    def run_action(self):                  # pragma: no cover - 子类覆盖
        raise NotImplementedError

    # ---- 通用工具 ----
    def add_profile_picker(self, on_change=None):
        """「选择档案」一行：文本框 + 浏览按钮（缺省填内置示例档案）。"""
        row = QHBoxLayout()
        self.profile_edit = QLineEdit(self)
        samples = self.service.sample_profiles()
        if samples:
            self.profile_edit.setText(samples[0])
        row.addWidget(self.profile_edit)
        button = QPushButton("浏览…", self)
        button.clicked.connect(self._pick_profile)
        row.addWidget(button)
        container = QWidget(self)
        container.setLayout(row)
        self._form.addRow("企业档案", container)
        if on_change is not None:
            self.profile_edit.textChanged.connect(on_change)
        return self.profile_edit

    def _pick_profile(self):
        path, _selected = QFileDialog.getOpenFileName(self, "选择企业档案", "", PROFILE_FILTER)
        if path:
            self.profile_edit.setText(path)

    def add_run_button(self, label="运行"):
        self.run_button = QPushButton(label, self)
        self.run_button.clicked.connect(self._on_run)
        self._controls.addWidget(self.run_button)
        self._controls.addStretch(1)
        return self.run_button

    def _on_run(self):
        try:
            self.run_action()
        except Exception as exc:            # noqa: BLE001 - 界面层兜底，避免弹栈崩溃
            self.model._fail(exc)
        self.refresh()

    def refresh(self):
        """把视图模型的状态/表格刷进控件（唯一的渲染点）。"""
        self.status_label.setText(self.model.summary or "（无输出）")
        color = _COLOR_FAIL if self.model.status == STATUS_FAIL else _COLOR_OK
        if self.model.status == STATUS_FAIL:
            self.status_label.setStyleSheet("color: %s;" % color)
        else:
            self.status_label.setStyleSheet("")
        self._fill_table(self.model.headers, self.model.rows)

    def _fill_table(self, headers, rows):
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(r_idx, c_idx, item)
        self.table.resizeColumnsToContents()

    def load_payload(self):
        return self.service.load_profile(self.profile_edit.text().strip())


class CalcPage(_Page):
    """核算页（FR-08.2）：完整编排结果 + 溯源表 + 报告导出（FR-06）。"""

    def __init__(self, service, parent=None):
        super().__init__(CalcPageModel(service), service, parent)

    def _build(self):
        self.add_profile_picker()
        self.diff_box = QCheckBox("附带双标尺差异（另一版通则，同年同行业）", self)
        self._form.addRow("", self.diff_box)
        self.add_run_button("核算")

        # 报告导出（FR-06）：与 CLI `report` 同一引擎入口，界面不另算一遍
        self.export_button = QPushButton("导出报告…", self)
        self.export_button.clicked.connect(self._on_export)
        self.export_button.setEnabled(False)
        self._controls.insertWidget(1, self.export_button)

    def run_action(self):
        diff = None
        if self.diff_box.isChecked():
            standards = [key for key, _label in self.service.standards()]
            payload = self.load_payload()
            current = (payload.get("coordinate") or {}).get("standard")
            diff = next((s for s in standards if s != current), None)
        self.model.run(self.load_payload(), diff_standard=diff)

    def _on_export(self):
        """导出报告到用户选定目录（复用 service.export → report.export_all）。"""
        directory = QFileDialog.getExistingDirectory(self, "选择报告输出目录")
        if not directory:
            return
        try:
            written = self.service.export(self.load_payload(), directory,
                                          formats=("md", "csv", "xlsx"))
        except Exception as exc:                    # noqa: BLE001 - 界面层兜底
            self.output.setVisible(True)
            self.output.setPlainText("导出失败：%s" % exc)
            return
        files = [path for paths in written.values() for path in paths]
        self.output.setVisible(True)
        self.output.setPlainText("报告已导出 %d 个文件到 %s：\n%s"
                                 % (len(files), directory,
                                    "\n".join(os.path.basename(p) for p in files)))

    def refresh(self):
        super().refresh()
        self.export_button.setEnabled(self.model.status == STATUS_OK)
        if self.model.status != STATUS_OK:
            return
        rows = self.model.provenance_rows()
        if rows:
            self.output.setVisible(True)
            self.output.setPlainText(
                "数据溯源表（%d 行）\n" % len(rows)
                + "\n".join(" | ".join(r) for r in rows))


class CheckPage(_Page):
    """校核页（FR-08.2）：四类检查的分级问题清单。"""

    def __init__(self, service, parent=None):
        super().__init__(CheckPageModel(service), service, parent)

    def _build(self):
        self.add_profile_picker()
        self.baseline_edit = QLineEdit(self)
        self._form.addRow("上一年度档案（可选）", self.baseline_edit)
        self.add_run_button("校核")

    def run_action(self):
        baseline = None
        path = self.baseline_edit.text().strip()
        if path:
            baseline = self.service.load_profile(path)
        self.model.run(self.load_payload(), baseline=baseline)


class QuotaPage(_Page):
    """配额页（FR-08.2）：方法学 / 参数 / 结果 / 免责声明。"""

    def __init__(self, service, parent=None):
        super().__init__(QuotaPageModel(service), service, parent)

    def _build(self):
        self.add_profile_picker()
        self.benchmark_edit = QLineEdit(self)
        self.benchmark_edit.setPlaceholderText("规则包不承载时须显式填写（外部输入）")
        self._form.addRow("行业平衡值 / 基准值", self.benchmark_edit)
        self.factor_edit = QLineEdit(self)
        self.factor_edit.setPlaceholderText("调峰修正系数 / 强度系数 α（可空）")
        self._form.addRow("修正系数", self.factor_edit)
        self.output_edit = QLineEdit(self)
        self.output_edit.setPlaceholderText("产量 / 发电量（可空，取档案）")
        self._form.addRow("产量", self.output_edit)
        self.add_run_button("试算")

    def run_action(self):
        params = {
            "benchmark_value": self.benchmark_edit.text().strip() or None,
            "correction_factor": self.factor_edit.text().strip() or None,
            "output": self.output_edit.text().strip() or None,
        }
        self.model.run(self.load_payload(), params=params)

    def refresh(self):
        super().refresh()
        disclaimer = self.model.disclaimer()
        if disclaimer:
            self.output.setVisible(True)
            self.output.setPlainText("免责声明：%s" % disclaimer)


class BenchPage(_Page):
    """基准页（FR-08.2）：三类套件一条命令跑全 + 指标判定。"""

    def __init__(self, service, parent=None):
        super().__init__(BenchPageModel(service), service, parent)

    def _build(self):
        self.suite_box = QComboBox(self)
        self.suite_box.addItem("全部三类套件", None)
        for name in ("rules", "factor", "cases"):
            self.suite_box.addItem(name, name)
        self._form.addRow("套件", self.suite_box)
        self.add_run_button("运行基准")

    def run_action(self):
        self.model.run(suites=[self.suite_box.currentData()] if self.suite_box.currentData()
                       else None)


class MainWindow(QWidget):
    """多页签主窗口（核算 / 校核 / 配额 / 基准）。"""

    def __init__(self, data_dir=None, parent=None):
        super().__init__(parent)
        from .service import WorkbenchService

        self.service = WorkbenchService(data_dir)
        self.setWindowTitle("企业温室气体排放核算与报告工作台 v%s" % self.service.version())
        self.resize(1080, 680)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.calc_page = CalcPage(self.service, self)
        self.check_page = CheckPage(self.service, self)
        self.quota_page = QuotaPage(self.service, self)
        self.bench_page = BenchPage(self.service, self)
        self.tabs.addTab(self.calc_page, "核算")
        self.tabs.addTab(self.check_page, "校核")
        self.tabs.addTab(self.quota_page, "配额")
        self.tabs.addTab(self.bench_page, "基准")
        layout.addWidget(self.tabs)

        self.data_label = QLabel("数据目录：%s" % self.service.data_dir, self)
        layout.addWidget(self.data_label)

    def pages(self):
        return [self.calc_page, self.check_page, self.quota_page, self.bench_page]


def build_window(data_dir=None):
    """构造主窗口（供 main 与 offscreen 测试共用）。"""
    return MainWindow(data_dir=data_dir)


__all__ = ["MainWindow", "build_window", "CalcPage", "CheckPage", "QuotaPage", "BenchPage"]