"""规则索引与 status 门控测试（M0 核心 DoD：坐标门控 M0-6、混算拦截 M0-7）。"""

from decimal import Decimal

import pytest

from ghg.coordinates import Coordinate
from ghg.errors import (
    CoordinateError,
    MixedCoordinateError,
    RulesetNotEffective,
    RulesetValidationError,
)
from ghg.rules import (
    STATUS_PENDING,
    STATUS_VERIFIED,
    RulesIndex,
    detect_mixed_coordinates,
    parse_payload_coordinate,
)


# ---------- 坐标空间 ----------

def test_coordinate_space_is_cartesian(rules_index):
    expected = len(rules_index.standards) * len(rules_index.years) * len(rules_index.industries)
    assert len(rules_index.coordinates()) == expected
    assert expected == 40


def test_resolve_known_and_unknown(rules_index):
    ok = rules_index.resolve(rules_index.standards[0], rules_index.years[0],
                             rules_index.industries[0])
    assert ok.key.startswith(rules_index.standards[0])
    with pytest.raises(CoordinateError):
        rules_index.resolve("no-such-standard", 2024, "steel")


def test_pack_declares_matching_coordinate(rules_index):
    for coord in rules_index.coordinates():
        pack = rules_index.pack(coord)
        declared = pack["coordinate"]
        assert Coordinate(declared["standard"], declared["year"],
                          declared["industry"]) == coord


# ---------- 门控（M0 核心行为）----------

def test_every_coordinate_is_blocked_in_m0(rules_index):
    """M0 数据初态：全部条目 pending，故每个坐标都被门控拦截。"""
    for coord in rules_index.coordinates():
        with pytest.raises(RulesetNotEffective):
            rules_index.effective_ruleset(coord)


def test_gate_report_lists_pending(rules_index):
    coord = rules_index.coordinates()[0]
    report = rules_index.gate_report(coord)
    assert report["effective"] is False
    assert report["pending_count"] > 0
    assert all(item["status"] == STATUS_PENDING for item in report["pending"])


def test_ruleset_not_effective_exit_code():
    from ghg.errors import EXIT_GATE
    exc = RulesetNotEffective("s/2024/i", ["a", "b"])
    assert exc.exit_code == EXIT_GATE
    assert exc.entries == ["a", "b"]        # 排序后
    assert "s/2024/i" in str(exc)


def test_gate_passes_when_all_verified(rules_index):
    """构造一个全部条目已核对（value 非空 + verified）的最小规则包 → 门控放行。"""
    coord = rules_index.coordinates()[0]
    pack = _minimal_pack(coord)
    index = _index_with_pack(rules_index, coord, pack)
    result = index.effective_ruleset(coord)
    assert result["engine"]["coefficients"]["oxidation_rate"]["value"] == Decimal(1)


def test_gate_blocks_null_value_even_when_verified(rules_index):
    """status=verified 但数值为 null 仍视为未核对（数值未核对不得生效）。"""
    coord = rules_index.coordinates()[0]
    pack = _minimal_pack(coord)
    pack["engine"]["coefficients"]["oxidation_rate"]["value"] = None
    index = _index_with_pack(rules_index, coord, pack)
    with pytest.raises(RulesetNotEffective):
        index.effective_ruleset(coord)


def test_gate_blocks_pending_entry(rules_index):
    """把一条改回 pending → 门控拦截，且拦截信息含该条目 id。"""
    coord = rules_index.coordinates()[0]
    pack = _minimal_pack(coord)
    pack["engine"]["coefficients"]["oxidation_rate"]["status"] = STATUS_PENDING
    index = _index_with_pack(rules_index, coord, pack)
    with pytest.raises(RulesetNotEffective) as exc_info:
        index.effective_ruleset(coord)
    assert "oxidation_rate" in str(exc_info.value)


def test_unknown_schema_rejected(rules_index):
    coord = rules_index.coordinates()[0]
    pack = _minimal_pack(coord)
    pack["schema"] = "nope/v9"
    index = _index_with_pack(rules_index, coord, pack)
    with pytest.raises(RulesetValidationError):
        index.effective_ruleset(coord)


def test_coordinate_mismatch_rejected(rules_index):
    coord = rules_index.coordinates()[0]
    pack = _minimal_pack(coord)
    pack["coordinate"]["year"] = coord.year + 1
    index = _index_with_pack(rules_index, coord, pack)
    with pytest.raises(RulesetValidationError):
        index.effective_ruleset(coord)


# ---------- 混算拦截（M0 核心行为）----------

def test_detect_single_coordinate_by_dict():
    payload = {"coordinate": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"}}
    found = detect_mixed_coordinates(payload)
    assert len(found) == 1


def test_detect_mixed_coordinates_raises():
    payload = {
        "a": {"standard": "gbt32150-2025", "year": 2024, "industry": "steel"},
        "b": {"standard": "gbt32150-2015", "year": 2022, "industry": "steel"},
    }
    with pytest.raises(MixedCoordinateError):
        detect_mixed_coordinates(payload)


def test_detect_mixed_via_nested_string():
    payload = {"a": "gbt32150-2025/2024/steel", "b": "gbt32150-2015/2022/steel"}
    with pytest.raises(MixedCoordinateError):
        detect_mixed_coordinates(payload)


def test_parse_payload_requires_coordinate():
    with pytest.raises(CoordinateError):
        parse_payload_coordinate({"facility": {}})


def test_parse_payload_with_index(rules_index):
    payload = {"coordinate": {"standard": rules_index.standards[0],
                              "year": rules_index.years[0],
                              "industry": rules_index.industries[0]}}
    coord = parse_payload_coordinate(payload, index=rules_index)
    assert coord.standard == rules_index.standards[0]


# ---------- 数据初态纪律 ----------

def test_all_policy_values_are_null_in_m0(rules_index):
    """M0 纪律：全部数值字段为 null（未核对不得生效）。"""
    from ghg.rules import _iter_entries
    for coord in rules_index.coordinates():
        pack = rules_index.pack(coord)
        for path, node in _iter_entries(pack):
            if "value" in node:
                assert node["value"] is None, "%s.%s 数值非空" % (coord.key, path)
            assert node["status"] == STATUS_PENDING


def test_units_file_is_verified_definitional(rules_index):
    """单位换算表是定义性关系，可标 verified（与政策数值纪律不冲突）。"""
    pack = rules_index.pack(rules_index.coordinates()[0])
    assert "disclaimer" in pack["report"]


# ---------- 辅助 ----------

def _minimal_pack(coord, verified=True):
    """构造一个与 schema 相符、条目已核对的最小规则包（用于门控正/负路径）。"""
    status = STATUS_VERIFIED if verified else STATUS_PENDING
    return {
        "schema": "ghg-ruleset/v1",
        "coordinate": {"standard": coord.standard, "year": coord.year,
                       "industry": coord.industry},
        "engine": {
            "coefficients": {
                "oxidation_rate": {"value": Decimal(1), "unit": "1", "status": status},
            },
        },
    }


def _index_with_pack(rules_index, coord, pack):
    """用给定包内容替换索引中某坐标的包（只在内存中，不写盘）。"""
    index = RulesIndex(rules_index.data_dir, rules_index._manifest, rules_index.base_dir)
    index._cache[coord.key] = (rules_index._by_key[coord.key], pack)
    return index
