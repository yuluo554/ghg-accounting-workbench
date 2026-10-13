"""确定性 JSON 读写测试（NFR-04）。"""

import os
from decimal import Decimal

import pytest

from ghg import jsonio


def test_dumps_sorts_keys():
    a = jsonio.dumps({"b": 1, "a": 2})
    b = jsonio.dumps({"a": 2, "b": 1})
    assert a == b
    assert a.index('"a"') < a.index('"b"')


def test_dumps_decimal_is_bare_number():
    text = jsonio.dumps({"v": Decimal("0.001")})
    assert '"0.001"' not in text       # 不得写成字符串
    assert "0.001" in text


def test_dumps_ends_with_single_newline():
    text = jsonio.dumps({"a": 1})
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")


def test_loads_float_becomes_decimal():
    obj = jsonio.loads('{"v": 1.5}')
    assert isinstance(obj["v"], Decimal)
    assert obj["v"] == Decimal("1.5")


def test_write_uses_lf_only(tmp_path):
    path = tmp_path / "x.json"
    jsonio.write(str(path), {"a": [1, 2], "b": {"c": "中文"}})
    raw = path.read_bytes()
    assert b"\r" not in raw, "冻结产物不得含 CR（Windows 默认 CRLF 漂移）"
    assert raw.decode("utf-8").startswith("{")


def test_roundtrip_stable(tmp_path):
    payload = {"z": 1, "a": {"n": Decimal("2.50"), "t": "文本"}}
    p1 = tmp_path / "one.json"
    p2 = tmp_path / "two.json"
    jsonio.write(str(p1), payload)
    loaded = jsonio.load(str(p1))
    jsonio.write(str(p2), loaded)
    assert p1.read_bytes() == p2.read_bytes()


def test_unsupported_type_raises():
    with pytest.raises(TypeError):
        jsonio.dumps({"v": object()})
