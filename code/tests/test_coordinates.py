"""坐标模型测试。"""

import pytest

from ghg.coordinates import Coordinate, parse_coordinate
from ghg.errors import CoordinateError


def test_key_and_equality():
    a = Coordinate("gbt32150-2025", 2024, "steel")
    b = Coordinate("gbt32150-2025", "2024", "steel")
    assert a == b
    assert a.key == "gbt32150-2025/2024/steel"
    assert hash(a) == hash(b)


def test_year_coerced_to_int():
    assert Coordinate("x", "2024", "y").year == 2024


def test_invalid_year_raises():
    with pytest.raises(CoordinateError):
        Coordinate("x", "abcd", "y")


def test_empty_field_raises():
    with pytest.raises(CoordinateError):
        Coordinate("", 2024, "steel")


def test_parse_from_dict():
    coord = parse_coordinate({"standard": "s", "year": 2024, "industry": "i"})
    assert coord.key == "s/2024/i"


def test_parse_from_string():
    coord = parse_coordinate("s/2024/i")
    assert (coord.standard, coord.year, coord.industry) == ("s", 2024, "i")


def test_parse_missing_field_raises():
    with pytest.raises(CoordinateError):
        parse_coordinate({"standard": "s", "year": 2024})


def test_parse_bad_string_raises():
    with pytest.raises(CoordinateError):
        parse_coordinate("s/2024")


def test_parse_with_index_rejects_unknown(rules_index):
    with pytest.raises(CoordinateError):
        parse_coordinate("gbt32150-2025/1999/steel", index=rules_index)
