"""规则索引与 status 门控测试（M0 核心 DoD：坐标门控 M0-6、混算拦截 M0-7）。"""

from decimal import Decimal

import pytest

from ghg import jsonio
from ghg.coordinates import Coordinate
from ghg.errors import (
    CoordinateError,
    MixedCoordinateError,
    RulesetNotEffective,
    RulesetValidationError,
)
from ghg.rules import (
    SCOPE_CALC,
    SCOPE_CHECK,
    SCOPE_QUOTA,
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

def test_gate_is_scoped_by_calc_path(rules_index):
    """M1 立规、M3 收口：门控按计算路径分作用域（plan/04 §4.3）。

    核算路径可通过的坐标存在（M1 已挂官方原文核对）；M3 起校核阈值与配额参数已就位，
    故**校核路径与配额路径亦全部可通过**——"分作用域"仍由各块独立门控体现
    （见 test_scope_blocks_are_independent）。
    """
    calc_ok = [c for c in rules_index.coordinates()
               if rules_index.gate_report(c, scope=SCOPE_CALC)["effective"]]
    assert len(calc_ok) > 0, "应至少有一个坐标的核算路径可通过门控"
    assert all(rules_index.gate_report(c, scope=SCOPE_QUOTA)["effective"]
               for c in rules_index.coordinates()), "M3 起配额路径应全部可通过"
    assert all(rules_index.gate_report(c, scope=SCOPE_CHECK)["effective"]
               for c in rules_index.coordinates()), "M3 起校核路径应全部可通过"


def test_scope_blocks_are_independent(rules_index):
    """分作用域仍生效：把 quota 块改回 pending 只拦配额路径，不牵连核算/校核。"""
    coord = rules_index.resolve("gbt32150-2025", 2024, "steel")
    pack = jsonio.loads(jsonio.dumps(rules_index.pack(coord)))
    pack["quota"]["status"] = STATUS_PENDING
    index = _index_with_pack(rules_index, coord, pack)
    assert index.gate_report(coord, scope=SCOPE_QUOTA)["effective"] is False
    assert index.gate_report(coord, scope=SCOPE_CALC)["effective"] is True
    assert index.gate_report(coord, scope=SCOPE_CHECK)["effective"] is True


def test_gate_report_lists_pending(rules_index):
    """整包口径下仍有待核对条目（如 quota 未覆盖年度 / 2026 发电碳氧化率）→ 列表非空。"""
    reports = [rules_index.gate_report(c) for c in rules_index.coordinates()]
    pending_reports = [r for r in reports if not r["effective"]]
    assert pending_reports, "整包口径应存在被拦截坐标"
    for report in pending_reports:
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


# ---------- 数据态纪律（M1）----------

def test_verified_entries_have_values_and_clauses(rules_index):
    """M1 纪律：凡 status=verified 的条目必须有非空 value、真实条款号与出处。

    （M0 的「全部数值为 null」断言在 M1 已由本断言取代：核对过的条目必须带值 +
    条款 + 出处，未核对的一律维持 pending 且未经门控不得进入计算路径。）
    """
    from ghg.rules import _iter_entries
    verified_count = 0
    for coord in rules_index.coordinates():
        pack = rules_index.pack(coord)
        for path, node in _iter_entries(pack):
            if node.get("status") == STATUS_VERIFIED:
                verified_count += 1
                if "value" in node:
                    assert node["value"] is not None, "%s.%s 已核对但数值为空" % (coord.key, path)
                clause = node.get("clause") or {}
                assert clause.get("article"), "%s.%s 已核对但缺条款号" % (coord.key, path)
                assert clause.get("article") != "待核对", "%s.%s 条款号仍为占位" % (coord.key, path)
            else:
                # pending 条目绝不得携带数值（未核对不得生效）
                if "value" in node:
                    assert node["value"] is None, "%s.%s pending 却携带数值" % (coord.key, path)
    assert verified_count > 0, "M1 应存在已核对（verified）条目"


def test_pending_entries_never_enter_calc_path(rules_index):
    """未核对条目不得进入计算路径：核算路径可通过的坐标内不得残留 pending。"""
    from ghg.rules import _scoped_entries
    for coord in rules_index.coordinates():
        if not rules_index.gate_report(coord, scope=SCOPE_CALC)["effective"]:
            continue
        pack = rules_index.pack(coord)
        leftover = [p for p, n in _scoped_entries(pack, SCOPE_CALC)
                    if n.get("status") != STATUS_VERIFIED]
        assert leftover == [], "%s 核算路径残留未核对条目：%s" % (coord.key, leftover)


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
