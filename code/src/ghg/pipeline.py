"""完整核算编排（CLI 与 GUI 共用的单点，M2 落地；报告文件导出属 M5）。

编排顺序（硬性，plan/04 §三）：
  1. 门控 ``effective_ruleset(coord, scope="calc")``（可能抛 ``RulesetNotEffective`` → 退出码 1）；
  2. 边界识别 :func:`ghg.boundary.identify_boundary`（应核算源缺输入 → 退出码 2）；
  3. 逐源：因子选择（按类别分派 + 优先级）→ 单位换算 → 表达式树求值；
  4. 汇总（行序按 ``source_id`` 排序，位级确定性）；
  5. 组装报告：报告头 + 边界清单 + 逐源明细 + 因子来源表 + 数据溯源表（+ 可选双标尺差异）。

**溯源完整性是硬约束**（plan/04 §6.3）：溯源表行数必须等于「明细表行数 + 因子来源表行数」，
且每行 ``rule_entry_id`` 必须能在该坐标包内解析到具体条目；不满足即抛
:class:`ProvenanceError`（退出码 2）——不得导出"半溯源"报告。
"""

from datetime import datetime

from . import __version__
from .boundary import diff_boundary, identify_boundary
from .calc import UNIT_EMISSION, compute
from .errors import ProvenanceError
from .rules import SCOPE_CALC

SCHEMA_FULL_REPORT = "ghg-fullreport/v1"

# 因子来源层级 → 规则包内治理该层级的条目路径（供溯源表 rule_entry_id 解析）
_FACTOR_ENTRY_DEFAULT = "factors.industry_default_values.default_factor"
_FACTOR_ENTRY_BY_CATEGORY = "factors.industry_default_values.by_category"
_FACTOR_ENTRY_PRIORITY = "factors.priority_clause"

# 溯源表两段的定位前缀（报告数字位置）
_POS_DETAIL = "明细表"
_POS_FACTOR = "因子来源表"


def resolve_rule_entry(pack, entry_id):
    """把溯源表的 ``rule_entry_id`` 解析为规则包内的具体条目。

    支持两种形态：
      * ``boundary.sources.<source_id>``（列表按 ``id`` 定位）；
      * 通用点分路径（如 ``factors.industry_default_values.default_factor``）。

    解析失败即抛 :class:`ProvenanceError` —— 溯源表不得出现悬空引用。
    """
    parts = entry_id.split(".")
    node = pack
    idx = 0
    while idx < len(parts):
        part = parts[idx]
        if isinstance(node, dict):
            if part not in node:
                raise ProvenanceError("溯源条目路径不存在：%s（缺 %s）" % (entry_id, part))
            node = node[part]
        elif isinstance(node, list):
            matched = [item for item in node
                       if isinstance(item, dict) and item.get("id") == part]
            if not matched:
                raise ProvenanceError(
                    "溯源条目在列表中不存在：%s（列表内无 id=%s）" % (entry_id, part))
            node = matched[0]
        else:
            raise ProvenanceError("溯源条目路径无法继续：%s（在 %s 处中断）" % (entry_id, part))
        idx += 1
    return node


def _factor_entry_path(source_label, category):
    """因子来源层级 → 规则包内治理条目的路径。"""
    if source_label == "industry_default":
        return _FACTOR_ENTRY_DEFAULT
    if source_label.startswith("industry_default:"):
        return "%s.%s" % (_FACTOR_ENTRY_BY_CATEGORY, source_label.split(":", 1)[1])
    # 实测 / 官方因子库：治理条目是"因子获取优先级"条款（FR-02.4）
    return _FACTOR_ENTRY_PRIORITY


def _build_factor_table(lines, pack):
    """因子来源表：按（层级, 数值, 单位）去重，并记录使用该因子的排放源。"""
    rows = {}
    for line in lines:
        label = line["factor"]["source"]
        key = (label, line["factor"]["value"], line["factor"]["unit"])
        row = rows.get(key)
        if row is None:
            entry_path = _factor_entry_path(label, line["category"])
            entry = resolve_rule_entry(pack, entry_path)
            row = {
                "factor_id": ("default_factor" if label == "industry_default"
                              else label),
                "value": line["factor"]["value"],
                "unit": line["factor"]["unit"],
                "source": label,
                "ref": (line["provenance"].get("factor") or {}).get("ref"),
                "clause": entry.get("clause"),
                "status": entry.get("status"),
                "rule_entry_id": entry_path,
                "sources": [],
            }
            rows[key] = row
        row["sources"].append(line["source_id"])
    table = []
    for key in sorted(rows.keys()):
        row = rows[key]
        row["sources"] = sorted(row["sources"])
        table.append(row)
    return table


def _build_provenance(lines, factor_table):
    """数据溯源表（FR-06.2 核心）：明细行 + 因子行，逐数字回指来源。"""
    rows = []
    for line in lines:
        rows.append({
            "position": "%s:%s" % (_POS_DETAIL, line["source_id"]),
            "value": line["emission"],
            "unit": UNIT_EMISSION,
            "activity_source": "企业档案 sources[%s].activity" % line["source_id"],
            "factor_source": line["factor"]["source"],
            "clause": line.get("clause"),
            "rule_entry_id": "boundary.sources.%s" % line["source_id"],
        })
    for row in factor_table:
        rows.append({
            "position": "%s:%s" % (_POS_FACTOR, row["factor_id"]),
            "value": row["value"],
            "unit": row["unit"],
            "activity_source": "（因子，非活动数据）",
            "factor_source": row["source"],
            "clause": row.get("clause"),
            "rule_entry_id": row["rule_entry_id"],
        })
    return rows


def _assert_provenance_complete(provenance, line_count, factor_count, pack):
    expected = line_count + factor_count
    if len(provenance) != expected:
        raise ProvenanceError(
            "溯源表不完整：%d 行，应为 明细 %d + 因子 %d = %d 行"
            % (len(provenance), line_count, factor_count, expected)
        )
    for row in provenance:
        resolve_rule_entry(pack, row["rule_entry_id"])   # 悬空引用即抛错


def _report_head(pack, coord, generated_at):
    report_block = pack.get("report", {}) or {}
    return {
        "coordinate": coord.key,
        "standard_code": report_block.get("standard_code"),
        "industry_label": report_block.get("industry_label"),
        "tool_version": __version__,
        "generated_at": generated_at,
        "disclaimer": report_block.get("disclaimer"),
    }


def compute_full(payload, coord, index, units, diff_standard=None, generated_at=None,
                 include_optional=None):
    """完整编排：门控 → 边界 → 逐源核算 → 因子表 → 溯源表（+ 可选双标尺差异）。

    * ``diff_standard``：给出另一个通则短键即附带双标尺差异（同年同行业）；
    * ``generated_at``：报告头生成时间；缺省用当前本地时间（报告正文是唯一允许
      时间戳出现处，见 plan/04 §6.1）。测试传固定值以保证可复现。
    """
    pack = index.effective_ruleset(coord, scope=SCOPE_CALC)

    if include_optional is not None:
        payload = dict(payload)
        payload["include_optional"] = include_optional

    boundary = identify_boundary(payload, coord, pack,
                                 include_optional=bool(payload.get("include_optional")))
    calc = compute(payload, coord, pack, units)

    factor_table = _build_factor_table(calc["lines"], pack)
    provenance = _build_provenance(calc["lines"], factor_table)
    _assert_provenance_complete(provenance, len(calc["lines"]), len(factor_table), pack)

    boundary_diff = None
    if diff_standard:
        other = index.resolve(diff_standard, coord.year, coord.industry)
        # 基准 = 另一版通则（旧版坐标），目标 = 本次核算坐标
        boundary_diff = diff_boundary(other, coord, index)

    return {
        "schema": SCHEMA_FULL_REPORT,
        "report_head": _report_head(pack, coord,
                                    generated_at or datetime.now().isoformat(timespec="seconds")),
        "facility": payload.get("facility") or {},
        # 公式表达式树（报告 §4「核算过程」逐源代入用；来自规则包，非代码内联）
        "formula": (pack.get("engine", {}) or {}).get("formula", {}).get("expr"),
        "boundary": boundary,
        "boundary_diff": boundary_diff,
        "calc": calc,
        "factor_table": factor_table,
        "provenance": provenance,
        "provenance_counts": {
            "detail_rows": len(calc["lines"]),
            "factor_rows": len(factor_table),
            "total": len(provenance),
        },
        "warnings": [],
    }


# --------------------------------------------------------------------------
# 人类可读渲染（CLI 用；文件导出属 M5）
# --------------------------------------------------------------------------

def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return out


def render_report_text(report):
    """渲染完整报告文本（报告头 + 边界 + 明细 + 因子表 + 溯源表）。"""
    head = report["report_head"]
    calc = report["calc"]
    boundary = report["boundary"]
    facility = report.get("facility") or {}
    lines = [
        "# 企业温室气体排放核算报告（内部参考）",
        "",
        "## 0 报告头",
        "  报告主体：%s" % (facility.get("name") or "（未命名）"),
        "  规则包坐标：%s" % head["coordinate"],
        "  通则编号：%s" % (head.get("standard_code") or "-"),
        "  行业：%s" % (head.get("industry_label") or "-"),
        "  工具版本：%s" % head["tool_version"],
        "  生成时间：%s" % head["generated_at"],
        "  免责声明：%s" % (head.get("disclaimer") or "-"),
        "",
        "## 1 核算边界",
        "  应核算排放源 %d 项，纳入 %d 项"
        % (boundary["required_count"], boundary["included_count"]),
    ]
    for src in boundary["sources"]:
        mark = "纳入" if src["included"] else "排除"
        lines.append("    [%s] %s（%s）— %s" % (mark, src["id"], src["name"], src["reason"]))

    if report.get("boundary_diff"):
        diff = report["boundary_diff"]
        lines += [
            "",
            "### 1.3 双标尺差异（基准 %s）" % diff["base"],
            "  新增：%s" % ("、".join(diff["added"]) or "（无）"),
            "  取消：%s" % ("、".join(diff["removed"]) or "（无）"),
            "  口径调整：%s" % ("、".join(sorted({r["id"] for r in diff["adjusted"]})) or "（无）"),
        ]

    lines += ["", "## 2 逐排放源明细表"]
    lines += _table(
        ["源 id", "源名称", "活动数据", "单位", "排放因子", "因子来源", "氧化率", "排放量(tCO2e)", "依据条款"],
        [[l["source_id"], l["source_name"], l["activity"]["value"], l["activity"]["unit"],
          l["factor"]["value"], l["factor"]["source"], l["oxidation_rate"], l["emission"],
          "%s %s" % ((l.get("clause") or {}).get("code") or "-",
                     (l.get("clause") or {}).get("article") or "-")]
         for l in calc["lines"]] + [["合计", "", "", "", "", "", "", calc["total"], ""]])

    lines += ["", "## 3 因子来源表"]
    lines += _table(
        ["因子 id", "数值", "单位", "来源层级", "出处", "status", "用于排放源"],
        [[r["factor_id"], r["value"], r["unit"], r["source"],
          (r.get("ref") or {}).get("source") if isinstance(r.get("ref"), dict) else None,
          r.get("status"), "、".join(r["sources"])]
         for r in report["factor_table"]])

    lines += ["", "## 8 数据溯源表"]
    lines += _table(
        ["报告数字位置", "值", "活动数据来源", "因子来源", "规则条款", "规则包条目 id"],
        [[r["position"], r["value"], r["activity_source"], r["factor_source"],
          "%s %s" % ((r.get("clause") or {}).get("code") or "-",
                     (r.get("clause") or {}).get("article") or "-"),
          r["rule_entry_id"]] for r in report["provenance"]])

    lines += ["", "  排放总量：%s %s" % (calc["total"], UNIT_EMISSION)]
    return "\n".join(lines)