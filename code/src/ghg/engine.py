"""公式树求值与校验（对应 plan/04 §1.3 表达式文法）。

文法（唯一允许的运算集）：

  { "op": "mul",   "args": [expr, ...] }          连乘
  { "op": "add",   "args": [expr, ...] }          连加
  { "op": "sub",   "args": [expr, expr] }         差
  { "op": "div",   "args": [expr, expr] }         商（除数 0 抛 CalcError）
  { "op": "var",   "ref": "<scope 键>" }           变量
  { "op": "const", "ref": "<coefficients id>" }   常量（只允许引用系数，禁内联数值）

零字面量在表达式层同样成立：``{"op": "const", "value": 1.0}`` 属非法，
必须是 ``{"op": "const", "ref": "<id>"}``。
"""

from decimal import Decimal

from .decimals import as_decimal
from .errors import CalcError, RulesetValidationError

OPS = ("mul", "add", "sub", "div", "var", "const")

_BINARY_OPS = ("sub", "div")
_NARY_OPS = ("mul", "add")


def validate(expr, path="$"):
    """校验表达式结构；非法即抛 :class:`RulesetValidationError`。

    加载规则包时调用（fail fast），避免运行到一半才发现表达式写错。
    """
    if not isinstance(expr, dict):
        raise RulesetValidationError("表达式节点必须是对象，位置 %s" % path)
    op = expr.get("op")
    if op not in OPS:
        raise RulesetValidationError("非法运算符 %r，位置 %s" % (op, path))

    extra = set(expr.keys()) - {"op", "args", "ref"}
    if extra:
        raise RulesetValidationError(
            "表达式节点含未知字段 %s，位置 %s" % (sorted(extra), path)
        )

    if op in ("var", "const"):
        ref = expr.get("ref")
        if not isinstance(ref, str) or not ref:
            raise RulesetValidationError("%s 节点缺少 ref，位置 %s" % (op, path))
        if "args" in expr:
            raise RulesetValidationError("%s 节点不得含 args，位置 %s" % (op, path))
        return True

    args = expr.get("args")
    if not isinstance(args, list) or not args:
        raise RulesetValidationError("%s 节点缺少 args，位置 %s" % (op, path))
    if op in _BINARY_OPS and len(args) != 2:
        raise RulesetValidationError("%s 需要恰好 2 个参数，位置 %s" % (op, path))
    if op in _NARY_OPS and len(args) < 1:
        raise RulesetValidationError("%s 至少需要 1 个参数，位置 %s" % (op, path))
    for idx, child in enumerate(args):
        validate(child, "%s.args[%d]" % (path, idx))
    return True


def evaluate(expr, scope):
    """按表达式树求值，返回 :class:`Decimal`。

    scope 提供 ``var`` / ``const`` 的引用值；缺失引用抛 :class:`CalcError`。
    """
    validate(expr)
    op = expr["op"]

    if op == "var":
        return _lookup(expr["ref"], scope, "变量")
    if op == "const":
        return _lookup(expr["ref"], scope, "系数")

    values = [evaluate(child, scope) for child in expr["args"]]
    if op == "mul":
        acc = values[0]
        for value in values[1:]:
            acc = acc * value
        return acc
    if op == "add":
        acc = values[0]
        for value in values[1:]:
            acc = acc + value
        return acc
    if op == "sub":
        return values[0] - values[1]
    if op == "div":
        if values[1] == 0:
            raise CalcError("除数为 0，表达式 %r" % expr)
        return values[0] / values[1]
    raise RulesetValidationError("非法运算符 %r" % op)  # pragma: no cover - validate 已挡


def _lookup(ref, scope, kind):
    if not isinstance(scope, dict) or ref not in scope:
        raise CalcError("表达式引用的%s不存在：%s" % (kind, ref))
    value = scope[ref]
    if value is None:
        raise CalcError("表达式引用的%s值为空（可能是未核对条目）：%s" % (kind, ref))
    return as_decimal(value)


def collect_refs(expr):
    """收集表达式引用的全部 ref（去重排序），用于溯源与规则包校验。"""
    refs = set()

    def visit(node):
        if isinstance(node, dict):
            if node.get("op") in ("var", "const") and isinstance(node.get("ref"), str):
                refs.add(node["ref"])
            for arg in node.get("args", []) or []:
                visit(arg)

    visit(expr)
    return sorted(refs)


def collect_refs_by_op(expr):
    """按 ``op`` 分类收集 ref（去重排序）。

    返回 ``{"var": [...], "const": [...]}``。供规则包自洽扫描区分
    "变量引用"（须落在合法变量集内）与"系数引用"（须能在 ``engine.coefficients`` 解析）——
    两者校验依据不同，不能混作一份清单（见 plan/06 D4-3）。
    """
    out = {"var": set(), "const": set()}

    def visit(node):
        if isinstance(node, dict):
            op = node.get("op")
            if op in out and isinstance(node.get("ref"), str):
                out[op].add(node["ref"])
            for arg in node.get("args", []) or []:
                visit(arg)

    visit(expr)
    return {key: sorted(values) for key, values in out.items()}
