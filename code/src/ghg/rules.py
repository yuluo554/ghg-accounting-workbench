"""规则索引与 status 门控（本项目的架构核心）。

三件事：
  1. **单点索引** —— 坐标空间（通则版本 × 年度 × 行业）由 ``data/rules/manifest.json``
     唯一枚举；代码不得内联标准短键/年度/行业名。
  2. **门控单点** —— :meth:`RulesIndex.effective_ruleset` 是**唯一**允许进入计算路径的入口，
     任一携带 ``status`` 的条目非 ``verified``（或数值字段为 null）即抛
     :class:`RulesetNotEffective`。:meth:`RulesIndex.pack` 仅供只读预览。
  3. **混算拦截** —— :func:`detect_mixed_coordinates` 在输入里找出全部坐标，
     多于一个即抛 :class:`MixedCoordinateError`。
"""

import hashlib
import os
from decimal import Decimal

from . import jsonio
from .coordinates import Coordinate, parse_coordinate
from .errors import (
    CoordinateError,
    MixedCoordinateError,
    RulesetNotEffective,
    RulesetValidationError,
)

MANIFEST_NAME = "manifest.json"
SCHEMA_RULESET = "ghg-ruleset/v1"
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

# 携带这些键且值为 null 的条目视为"未核对"（null = 待核对占位，非零值）
NULLABLE_POLICY_KEYS = ("value",)


def _load_json(path):
    """读取 JSON，float → Decimal（禁 float 进入计算路径）。"""
    return jsonio.load(path)


def _iter_entries(node, path=""):
    """递归遍历，产出所有携带 ``status`` 字段的条目 (path, node)。"""
    if isinstance(node, dict):
        if "status" in node:
            yield path, node
        for key in sorted(node.keys()):
            child = node[key]
            if isinstance(child, (dict, list)):
                yield from _iter_entries(child, "%s.%s" % (path, key) if path else key)
    elif isinstance(node, list):
        for idx, child in enumerate(node):
            if isinstance(child, (dict, list)):
                yield from _iter_entries(child, "%s[%d]" % (path, idx))


def _entry_label(path, node):
    return node.get("id") or path or "<anonymous>"


def _entry_is_effective(node):
    if node.get("status") != STATUS_VERIFIED:
        return False
    for key in NULLABLE_POLICY_KEYS:
        if key in node and node[key] is None:
            return False
    return True


class RulesIndex(object):
    """坐标空间索引 + 规则包读取 + 门控。"""

    def __init__(self, data_dir, manifest, base_dir):
        self.data_dir = data_dir
        self.base_dir = base_dir
        self._manifest = manifest
        self._by_key = {}
        for item in manifest.get("coordinates", []):
            coord = Coordinate(item["standard"], item["year"], item["industry"])
            if coord.key in self._by_key:
                raise RulesetValidationError("manifest 坐标重复：%s" % coord.key)
            self._by_key[coord.key] = item
        self._cache = {}

    # ---------- 构造 ----------

    @classmethod
    def load(cls, data_dir):
        base = os.path.join(data_dir, "rules")
        manifest_path = os.path.join(base, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            raise RulesetValidationError("缺少规则索引：%s" % manifest_path)
        manifest = _load_json(manifest_path)
        if manifest.get("schema") != "ghg-manifest/v1":
            raise RulesetValidationError(
                "manifest schema 不受支持：%r" % manifest.get("schema")
            )
        return cls(data_dir, manifest, base)

    # ---------- 坐标空间 ----------

    @property
    def standards(self):
        return list(self._manifest.get("standards", []))

    @property
    def years(self):
        return list(self._manifest.get("years", []))

    @property
    def industries(self):
        return list(self._manifest.get("industries", []))

    def coordinates(self):
        """按 manifest 声明次序返回全部坐标。"""
        return [Coordinate(i["standard"], i["year"], i["industry"])
                for i in self._manifest.get("coordinates", [])]

    def has(self, coord):
        return coord.key in self._by_key

    def require(self, coord):
        if not self.has(coord):
            raise CoordinateError(
                "坐标不存在于规则空间：%s（可用坐标见 `ghg coords`）" % coord.key
            )
        return coord

    def resolve(self, standard, year, industry):
        """三字段 → 坐标（含合法性校验）。"""
        return self.require(Coordinate(standard, year, industry))

    # ---------- 规则包读取 ----------

    def _entry(self, coord):
        self.require(coord)
        if coord.key not in self._cache:
            item = self._by_key[coord.key]
            path = os.path.join(self.base_dir, item["file"])
            if not os.path.isfile(path):
                raise RulesetValidationError("规则包文件缺失：%s" % path)
            self._cache[coord.key] = (item, _load_json(path))
        return self._cache[coord.key]

    def pack(self, coord):
        """原始规则包（含 pending 条目）——**仅供只读预览，不得用于计算**。"""
        return self._entry(coord)[1]

    def pack_sha256(self, coord):
        return self._entry(coord)[0].get("sha256")

    def effective_ruleset(self, coord):
        """门控入口：返回通过校验的规则包，否则抛 :class:`RulesetNotEffective`。

        这是**唯一**允许把规则数值交给计算路径的方法。
        """
        pack = self.pack(coord)
        if pack.get("schema") != SCHEMA_RULESET:
            raise RulesetValidationError(
                "规则包 %s schema 不受支持：%r" % (coord.key, pack.get("schema"))
            )
        declared = pack.get("coordinate") or {}
        if Coordinate(declared.get("standard"), declared.get("year"),
                      declared.get("industry")) != coord:
            raise RulesetValidationError(
                "规则包 %s 内声明的坐标与索引不一致：%r" % (coord.key, declared)
            )
        blocked = [_entry_label(p, n) for p, n in _iter_entries(pack)
                   if not _entry_is_effective(n)]
        if blocked:
            raise RulesetNotEffective(coord.key, blocked)
        return pack

    def gate_report(self, coord):
        """门控体检（不抛异常）：返回待核对条目清单。"""
        pack = self.pack(coord)
        pending = []
        for path, node in _iter_entries(pack):
            if not _entry_is_effective(node):
                pending.append({
                    "entry": _entry_label(path, node),
                    "path": path,
                    "status": node.get("status"),
                })
        return {
            "coordinate": coord.key,
            "effective": not pending,
            "pending_count": len(pending),
            "pending": pending,
        }

    # ---------- 零字面量门禁的数据源 ----------

    def collect_numeric_tokens(self):
        """采集全部规则包中的**政策数值** token，供零政策字面量门禁使用。

        只采集数值类字段（``value``/``coefficient``/``threshold``/``limit``）——
        标准编号与条款号是**公开标识符/元数据**而非政策数值，属豁免（plan/06 §二 豁免 4）。
        返回排序去重后的字符串集合。
        """
        tokens = set()
        for coord in self.coordinates():
            pack = self.pack(coord)
            for _path, node in _iter_entries(pack):
                for key in ("value", "coefficient", "threshold", "limit"):
                    val = node.get(key)
                    if isinstance(val, bool):
                        continue
                    if isinstance(val, (int, Decimal)):
                        tokens.add(str(val))
        return sorted(tokens)


def detect_mixed_coordinates(payload):
    """在输入载荷里找出全部坐标；多于一个即抛 :class:`MixedCoordinateError`。

    识别两类形态：
      * dict 同时含 standard/year/industry 三键；
      * 形如 ``<standard>/<year>/<industry>`` 的字符串。
    """
    found = {}

    def visit(node):
        if isinstance(node, dict):
            if all(k in node for k in ("standard", "year", "industry")):
                try:
                    coord = Coordinate(node["standard"], node["year"], node["industry"])
                except CoordinateError:
                    coord = None
                if coord is not None:
                    found.setdefault(coord.key, node)
            for key in sorted(node.keys()):
                visit(node[key])
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, str):
            parts = node.split("/")
            if len(parts) == 3 and all(parts):
                try:
                    coord = Coordinate(parts[0], parts[1], parts[2])
                except CoordinateError:
                    return
                if coord.standard and _looks_like_standard(coord.standard):
                    found.setdefault(coord.key, node)

    visit(payload)

    if len(found) > 1:
        raise MixedCoordinateError(
            "输入包含多个规则包坐标（跨坐标混算被拒）：%s"
            % "、".join(sorted(found.keys()))
        )
    return [found[key] for key in sorted(found.keys())]


def _looks_like_standard(text):
    """启发式：标准短键含连字符与数字段（如 xxx-YYYY），避免把任意 a/b/c 当坐标。"""
    if "-" not in text:
        return False
    return any(ch.isdigit() for ch in text) and text.islower()


def manifest_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def parse_payload_coordinate(payload, index=None):
    """从输入载荷取唯一坐标（无坐标 → 抛 CoordinateError）。"""
    coords = detect_mixed_coordinates(payload)
    if not coords:
        raise CoordinateError("输入未声明规则包坐标（需要 standard/year/industry）")
    raw = coords[0]
    if isinstance(raw, str):
        return parse_coordinate(raw, index=index)
    return parse_coordinate(raw, index=index)
