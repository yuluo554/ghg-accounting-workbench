"""异常体系与 CLI 退出码映射。

退出码契约（plan/03 §六，锁定后不得漂移）：
  0 = 成功 / 门控通过 / 基准达标
  1 = 门控拦截（规则包含未核对条目，计算路径被拒）或基准未达标
  2 = 输入不可用 / 参数错误（坐标不存在、文件缺失、格式非法）
"""

EXIT_OK = 0
EXIT_GATE = 1
EXIT_INPUT = 2


class GhgError(Exception):
    """本工具全部可预期异常的基类。"""

    exit_code = EXIT_INPUT


class InputError(GhgError):
    """输入不可用或参数错误 → 退出码 2。"""

    exit_code = EXIT_INPUT


class CoordinateError(InputError):
    """坐标不存在或无法解析。"""


class MixedCoordinateError(InputError):
    """一次核算里出现两个及以上规则包坐标（跨坐标混算）。"""


class FactorUnavailable(InputError):
    """因子来源三层（实测/官方库/行业缺省）均不可用。"""


class UnitError(InputError):
    """单位未知或量纲不一致。"""


class RulesetValidationError(GhgError):
    """规则包结构或表达式非法。"""

    exit_code = EXIT_INPUT


class DataDirNotFound(GhgError):
    """数据目录定位失败。"""

    exit_code = EXIT_INPUT


class RulesetNotEffective(GhgError):
    """门控拦截：规则包存在未核对（pending）条目，禁止进入计算路径。

    attributes:
        coordinate: 坐标字符串
        entries:    未核对条目 id 列表（排序后，保证可复现）
    """

    exit_code = EXIT_GATE

    def __init__(self, coordinate, entries):
        self.coordinate = coordinate
        self.entries = sorted(entries)
        sample = "、".join(self.entries[:5])
        more = "" if len(self.entries) <= 5 else "（等 %d 项）" % len(self.entries)
        super().__init__(
            "规则包 %s 存在未核对条目，已拒绝进入计算路径：%s%s"
            % (coordinate, sample, more)
        )


class CalcError(GhgError):
    """计算过程非法（除零、引用缺失等）。"""

    exit_code = EXIT_INPUT


def exit_code_for(exc):
    """把异常映射为 CLI 退出码。"""
    if isinstance(exc, GhgError):
        return exc.exit_code
    return EXIT_INPUT
