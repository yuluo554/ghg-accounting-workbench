"""桌面形态（PySide6）—— **只消费引擎 API，零判定逻辑**（FR-08.2）。

设计铁律（与 CLI 同源，见 plan/03 §九）：

  * 本包**不实现任何核算/校核/配额/基准判定**：纳入判定、阈值比较、方法学选择、
    门槛判定一律发生在 ``ghg`` 核心层；GUI 只做「取输入 → 调引擎 → 渲染输出」。
  * 唯一的引擎调用点集中在 :mod:`ghg_gui.service`；页面模块不得直接 import
    ``ghg.calc`` / ``ghg.quality`` / ``ghg.quota`` / ``ghg.bench``
    （由 ``test_m5_gui.py`` 的导入门禁锁定）。
  * 全部页面可 **offscreen** 运行（``QT_QPA_PLATFORM=offscreen``），测试不依赖真实显示器。
"""

__version__ = "0.1.1"

__all__ = ["__version__"]