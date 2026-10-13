"""核算边界识别与双标尺差异（FR-01，M2 落地）。

两份能力：
  1. :func:`identify_boundary` —— 对**单一坐标**输出应核算排放源清单，
     每条判定"是否纳入"并给出条款依据文本；企业档案缺应核算源的活动数据时，
     记入 ``missing_inputs``（由编排层转为退出码 2，FR-01.4）。
  2. :func:`diff_boundary` —— 双标尺差异（FR-01.3）：以旧版坐标为基准，按 ``id``
     集合做差，产出 ``added`` / ``removed`` / ``adjusted``。

设计判断（为什么差异用规则包内的 ``delta_vs_2015`` 标记，而非跨包字段比较）：
  两版通则下的排放源清单在**条目 id 与结构字段**（``name`` / ``category`` / ``required``）
  上可能逐字相同——差异往往体现在"同一源在两版下的口径/条款依据"而非条目本身
  （例：2025 版把「燃料燃烧排放」更名为「化石燃料燃烧排放」，属术语口径变更）。
  因此差异判定以新版包内的 ``delta_vs_2015`` 声明为准（由 ``tools/gen_rulesets.py``
  逐条挂官方原文核对），再以两包同 id 的 ``category`` / ``required`` 变化作为
  **可程序化复核的交叉校验**——两者不一致即抛错（第二份真相检测）。

差异结果**现算现出，不落盘**（plan/04 §1.2：避免第二份真相）。
"""

from .errors import BoundaryError, CoordinateError

DELTA_SAME = "same"
DELTA_ADDED = "added"
DELTA_REMOVED = "removed"
DELTA_ADJUSTED = "adjusted"
DELTA_VALUES = (DELTA_SAME, DELTA_ADDED, DELTA_REMOVED, DELTA_ADJUSTED)

# 双标尺差异的比对字段（口径变化面）
_COMPARED_FIELDS = ("name", "category", "required")

# 档案活动数据数值字段名（缺失即视为该源未提供输入）
ACTIVITY_VALUE_KEY = "value"


def _sources_of(pack):
    return list(pack.get("boundary", {}).get("sources", []) or [])


def _catalog(pack):
    out = {}
    for src in _sources_of(pack):
        sid = src.get("id")
        if not sid:
            raise BoundaryError("规则包排放源条目缺少 id")
        if sid in out:
            raise BoundaryError("规则包排放源 id 重复：%s" % sid)
        out[sid] = src
    return out


def _provided(payload):
    """档案提供的排放源活动数据（source_id → 条目）。"""
    out = {}
    for item in payload.get("sources", []) or []:
        sid = item.get("source_id")
        if not sid:
            raise BoundaryError("档案中存在缺少 source_id 的排放源条目")
        if sid in out:
            raise BoundaryError("档案中排放源重复：%s" % sid)
        out[sid] = item
    return out


def _has_activity(item):
    activity = (item or {}).get("activity") or {}
    return activity.get(ACTIVITY_VALUE_KEY) is not None


def _clause_text(clause):
    if not clause:
        return ""
    code = clause.get("code")
    article = clause.get("article")
    parts = [p for p in (code, article) if p]
    return " ".join(parts)


def _source_report(coord, src, provided, include_optional):
    """单条排放源纳入判定。"""
    sid = src["id"]
    item = provided.get(sid)
    has_input = _has_activity(item)
    required = src.get("required") is True
    included = has_input and (required or include_optional)

    if included and required:
        reason = "应核算排放源，档案已提供活动数据"
    elif included:
        reason = "选填排放源，档案已提供活动数据（按 include_optional 纳入）"
    elif required:
        reason = "应核算排放源，但档案未提供活动数据（缺失输入）"
    else:
        reason = "非应核算排放源，档案未提供活动数据（排除）"
    clause_text = _clause_text(src.get("clause"))
    if clause_text:
        reason = "%s；依据 %s" % (reason, clause_text)

    return {
        "id": sid,
        "name": src.get("name"),
        "category": src.get("category"),
        "required": required,
        "clause": src.get("clause"),
        "included": included,
        "reason": reason,
    }


def identify_boundary(payload, coord, pack, include_optional=False):
    """识别该坐标下的应核算排放源清单。

    返回::

        {
          "coordinate": {...}, "coordinate_key": str,
          "sources": [{id, name, category, required, clause, included, reason}, ...],
          "included": [id...], "excluded": [id...], "missing_inputs": [id...],
          "required_count": int, "included_count": int,
        }

    * ``included`` 仅当该源被要求（``required`` 或 ``include_optional``）且档案提供了活动数据；
    * ``missing_inputs`` 非空表示"应核算却缺输入"，由调用方转退出码 2（FR-01.4）。
    """
    catalog = _catalog(pack)
    provided = _provided(payload)

    unknown = sorted(set(provided) - set(catalog))
    if unknown:
        raise BoundaryError(
            "档案含规则包未定义的排放源 id：%s（坐标 %s）"
            % ("、".join(unknown), coord.key)
        )

    sources = []
    for sid in sorted(catalog):
        sources.append(_source_report(coord, catalog[sid], provided, include_optional))

    included = [s["id"] for s in sources if s["included"]]
    missing = [s["id"] for s in sources if s["required"] and not s["included"]]
    excluded = [s["id"] for s in sources if not s["included"] and not s["required"]]

    return {
        "coordinate": coord.as_dict(),
        "coordinate_key": coord.key,
        "sources": sources,
        "included": included,
        "excluded": excluded,
        "missing_inputs": missing,
        "required_count": len([s for s in sources if s["required"]]),
        "included_count": len(included),
        "schema": "ghg-boundaryreport/v1",
    }


def _structural_changes(old_src, new_src):
    changes = []
    for field in _COMPARED_FIELDS:
        before = old_src.get(field)
        after = new_src.get(field)
        if before != after:
            changes.append({"field": field, "from": before, "to": after})
    return changes


def diff_boundary(coord_old, coord_new, index):
    """双标尺差异（以旧版为基准，FR-01.3）。

    返回 ``{base, target, added, removed, adjusted, unchanged}``：
      * ``added``    = 新版有、旧版无；
      * ``removed``  = 旧版有、新版无；
      * ``adjusted`` = 两版皆有且口径变化（``[{id, field, from, to, flag, declared_delta}]``）。

    差异判定：以新版包内 ``delta_vs_2015`` 声明为准（官方核对结论），并以两包同 id 的
    结构字段变化交叉校验；声明与结构不一致即抛 :class:`BoundaryError`。
    """
    if coord_old.standard == coord_new.standard:
        raise CoordinateError(
            "双标尺差异需要两个不同通则坐标，收到同一通则：%s" % coord_old.standard
        )
    old = _catalog(index.pack(coord_old))
    new = _catalog(index.pack(coord_new))

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))

    adjusted = []
    unchanged = []
    for sid in sorted(set(old) & set(new)):
        old_src = old[sid]
        new_src = new[sid]
        declared = new_src.get("delta_vs_2015")
        if declared not in DELTA_VALUES:
            raise BoundaryError(
                "排放源 %s 的 delta_vs_2015 取值非法：%r" % (sid, declared)
            )
        changes = _structural_changes(old_src, new_src)
        if declared == DELTA_ADJUSTED:
            if not changes:
                # 结构字段未变属常见情形（口径变更写在条款依据里）——用条款文本兜底为
                # 一条"clause"变更，保证 adjusted 行始终携带可比对字段。
                changes = [{
                    "field": "clause",
                    "from": _clause_text(old_src.get("clause")),
                    "to": _clause_text(new_src.get("clause")),
                }]
            for change in changes:
                row = dict(change)
                row["id"] = sid
                row["declared_delta"] = declared
                adjusted.append(row)
        else:
            if changes:
                raise BoundaryError(
                    "排放源 %s 声明 delta_vs_2015=%s，但结构字段实际变化 %s（口径不一致）"
                    % (sid, declared, [c["field"] for c in changes])
                )
            unchanged.append(sid)

    return {
        "base": coord_old.key,
        "target": coord_new.key,
        "added": added,
        "removed": removed,
        "adjusted": adjusted,
        "unchanged": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "adjusted_count": len({row["id"] for row in adjusted}),
        "unchanged_count": len(unchanged),
        "schema": "ghg-boundarydiff/v1",
    }


def diff_summary_text(diff):
    """人类可读的差异摘要（CLI 用）。"""
    lines = [
        "双标尺排放源差异（基准 %s → 目标 %s）" % (diff["base"], diff["target"]),
        "  新增：%s" % ("、".join(diff["added"]) if diff["added"] else "（无）"),
        "  取消：%s" % ("、".join(diff["removed"]) if diff["removed"] else "（无）"),
        "  口径调整：%s" % ("、".join(sorted({r["id"] for r in diff["adjusted"]}))
                            if diff["adjusted"] else "（无）"),
        "  未变：%s" % ("、".join(diff["unchanged"]) if diff["unchanged"] else "（无）"),
    ]
    return "\n".join(lines)