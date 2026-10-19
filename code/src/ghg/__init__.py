"""企业温室气体排放核算与报告工作台 —— 核心层。

设计铁律（见 plan/03、plan/06）：
  * 零第三方依赖、零网络、零 LLM（全部结论由确定性规则产生）；
  * 数值全链路 :class:`decimal.Decimal`；
  * 代码内不得出现任何规则包政策数值或坐标字面量（由 tools/check_zero_literals.py 门禁）。
"""

__version__ = "0.1.1"

__all__ = ["__version__"]
