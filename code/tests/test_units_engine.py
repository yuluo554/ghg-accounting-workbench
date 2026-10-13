"""单位换算与表达式求值测试。"""

from decimal import Decimal

import pytest

from ghg.decimals import as_decimal, quantize, to_text
from ghg.engine import collect_refs, evaluate, validate
from ghg.errors import CalcError, RulesetValidationError, UnitError


# ---------- decimals ----------

def test_as_decimal_rejects_float():
    with pytest.raises(TypeError):
        as_decimal(1.5)


def test_as_decimal_accepts_str_and_int():
    assert as_decimal("1.500") == Decimal("1.500")
    assert as_decimal(3) == Decimal(3)


def test_as_decimal_rejects_bool():
    with pytest.raises(TypeError):
        as_decimal(True)


def test_quantize_half_up():
    assert quantize(Decimal("1.0005"), 3) == Decimal("1.001")
    assert quantize("2.5678", 2) == Decimal("2.57")


def test_to_text_strips_trailing_zeros():
    assert to_text(Decimal("1000.000")) == "1000"
    assert to_text(Decimal("1.5")) == "1.5"


# ---------- units ----------

def test_convert_mass(unit_table):
    assert unit_table.convert("1", "t", "kg") == Decimal("1000")


def test_convert_energy(unit_table):
    assert unit_table.convert("1", "TJ", "GJ") == Decimal("1000")


def test_convert_roundtrip_all_units(unit_table):
    for unit in unit_table.unit_list():
        dim = unit_table.dimension_of(unit)
        base = unit_table.dimensions()[dim]["base"]
        if unit == base:
            continue
        forward = unit_table.convert("1", base, unit)
        back = unit_table.convert(forward, unit, base)
        assert back == Decimal(1), "单位 %s 往返不一致" % unit


def test_convert_cross_dimension_rejected(unit_table):
    with pytest.raises(UnitError):
        unit_table.convert("1", "t", "MWh")


def test_unknown_unit_rejected(unit_table):
    with pytest.raises(UnitError):
        unit_table.dimension_of("furlong")


def test_units_are_unique_across_dimensions(unit_table):
    dims = unit_table.dimensions()
    seen = {}
    for dim, spec in dims.items():
        for unit in spec["units"]:
            assert unit not in seen, "单位 %s 在 %s 与 %s 重复" % (unit, seen.get(unit), dim)
            seen[unit] = dim


def test_base_unit_factor_is_one(unit_table):
    for dim, spec in unit_table.dimensions().items():
        assert Decimal(str(spec["units"][spec["base"]])) == Decimal(1)


# ---------- engine ----------

def test_evaluate_var_and_const():
    expr = {"op": "mul", "args": [{"op": "var", "ref": "a"},
                                  {"op": "const", "ref": "b"}]}
    scope = {"a": Decimal(2), "b": Decimal("1.5")}
    assert evaluate(expr, scope) == Decimal(3)


def test_evaluate_div_by_zero_raises():
    expr = {"op": "div", "args": [{"op": "var", "ref": "a"},
                                  {"op": "const", "ref": "b"}]}
    with pytest.raises(CalcError):
        evaluate(expr, {"a": 1, "b": 0})


def test_evaluate_sub_and_add():
    scope = {"a": 10, "b": 4}
    assert evaluate({"op": "sub", "args": [{"op": "var", "ref": "a"},
                                           {"op": "var", "ref": "b"}]}, scope) == 6
    assert evaluate({"op": "add", "args": [{"op": "var", "ref": "a"},
                                           {"op": "var", "ref": "b"}]}, scope) == 14


def test_missing_ref_raises():
    with pytest.raises(CalcError):
        evaluate({"op": "var", "ref": "nope"}, {})


def test_null_ref_raises():
    with pytest.raises(CalcError):
        evaluate({"op": "var", "ref": "a"}, {"a": None})


def test_float_ref_rejected():
    with pytest.raises(TypeError):
        evaluate({"op": "var", "ref": "a"}, {"a": 1.5})


def test_validate_rejects_inline_const_value():
    """零字面量在表达式层同样成立：const 必须 ref，不得内联 value。"""
    with pytest.raises(RulesetValidationError):
        validate({"op": "const", "value": 3})


def test_validate_rejects_unknown_op():
    with pytest.raises(RulesetValidationError):
        validate({"op": "pow", "args": []})


def test_validate_rejects_binary_arity():
    with pytest.raises(RulesetValidationError):
        validate({"op": "div", "args": [{"op": "var", "ref": "a"}]})


def test_validate_rejects_extra_fields():
    with pytest.raises(RulesetValidationError):
        validate({"op": "var", "ref": "a", "bogus": 1})


def test_collect_refs():
    expr = {"op": "mul", "args": [{"op": "var", "ref": "a"},
                                  {"op": "const", "ref": "c"},
                                  {"op": "var", "ref": "a"}]}
    assert collect_refs(expr) == ["a", "c"]


def test_ruleset_formula_validates(rules_index):
    """生成器产出的公式树必须通过校验（fail fast 纪律）。"""
    for coord in rules_index.coordinates():
        pack = rules_index.pack(coord)
        expr = pack["engine"]["formula"]["expr"]
        validate(expr)
        refs = collect_refs(expr)
        assert "activity_data" in refs
        assert "emission_factor" in refs
        assert "oxidation_rate" in refs
