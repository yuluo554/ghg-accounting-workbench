"""可核证报告导出（FR-06，M5 落地）。

三个落盘产物（plan/04 §6.2）：

  * :func:`render_markdown` —— 人读，章节骨架见 plan/04 §6.1（§0 报告头 … §8 数据溯源表）；
  * :func:`write_csv`       —— 机读，一张表一个 CSV（UTF-8 with BOM，便于 Excel 双击打开）；
  * :func:`write_xlsx`      —— 机读，**最小 writer**（零第三方依赖）。

三条硬约束：

1. **可复现三要素**（FR-06.3）：报告头固定输出「规则包坐标 + 工具版本 + 生成时间」；
   生成时间由 ``pipeline.compute_full`` 注入（报告正文是唯一允许时间戳出现处）。
2. **无外链**（FR-06.4）：机读产物（CSV/XLSX）**不写 URL** —— 断网可开、可归档。
   官方出处以「文号 + 名称 + 版本」文本承载（足以定位文件），URL 只出现在人读 Markdown 里。
3. **字节确定性**（NFR-04）：一律 ``write_bytes`` + LF（无 CR）；XLSX 用 ``ZIP_STORED``
   + 固定 ``create_system``/``date_time``，同一输入两次导出**逐字节一致**。

**本模块零判定逻辑**：不做任何纳入判定、阈值判断或方法学选择——只把
``pipeline`` / ``quality`` / ``quota`` 已算好的结构渲染成文件。表格模型
（:func:`_tables`）是 CSV 与 XLSX 的**单一真相源**，避免两条导出路径漂移。
"""

import zipfile

from . import __version__
from .calc import (
    UNIT_EMISSION,
    VAR_ACTIVITY,
    VAR_FACTOR,
    VAR_OXIDATION,
)
from .errors import InputError

SCHEMA_REPORT = "ghg-report/v1"

# 支持的导出格式（CLI `--format` 与 :func:`export_all` 共用；单一真相源）
FORMATS = ("md", "csv", "xlsx")

# 报告标题（人读 Markdown 首行；与 pipeline.render_report_text 保持一致）
TITLE = "# 企业温室气体排放核算报告（内部参考）"

# 章节标题（plan/04 §6.1 骨架；XLSX/CSV 表名亦取自此，保证人读/机读同名）
SEC_HEAD = "0 报告头"
SEC_BOUNDARY = "1 核算边界"
SEC_LINES = "2 逐排放源明细表"
SEC_FACTORS = "3 因子来源表"
SEC_PROCESS = "4 核算过程"
SEC_QUALITY = "5 数据质量校核结果"
SEC_QUOTA = "6 配额试算"
SEC_CLAUSES = "7 依据清单"
SEC_PROVENANCE = "8 数据溯源表"

# 未启用章节的显式说明（不得静默留空，否则读者会以为"检查过且没问题"）
NOTE_CHECK_DISABLED = "本次导出未启用数据质量校核（使用 --with-check 启用）。"
NOTE_QUOTA_DISABLED = "本次导出未启用配额试算（使用 --with-quota 启用）。"
NOTE_CLAUSES_ABSENT = "未加载条款库（data/knowledge/clauses.json），本节不可用。"
NOTE_NO_ISSUES = "（无命中问题）"
NOTE_NO_DIFF = "（未请求双标尺差异对比）"

# 公式变量 → 中文标签（报告 §4 公式代入可读化；键取自 calc 的单一真相源）
_VAR_LABELS = {
    VAR_ACTIVITY: "活动数据",
    VAR_FACTOR: "排放因子",
    VAR_OXIDATION: "氧化率",
}

# 运算符 → 可读符号
_OP_SYMBOLS = {"mul": " × ", "add": " + ", "sub": " − ", "div": " ÷ "}

# 问题级别 → 中文（报告 §5）
_LEVEL_LABELS = {"error": "错误", "warning": "警告", "info": "提示"}

# 边界纳入标记
_MARK_INCLUDED = "纳入"
_MARK_EXCLUDED = "排除"


# --------------------------------------------------------------------------
# 表格模型（CSV 与 XLSX 的单一真相源）
# --------------------------------------------------------------------------

def _clause_text(clause):
    """条款引用 → 可读文本（编号 + 条号）。"""
    clause = clause or {}
    code = clause.get("code") or "-"
    article = clause.get("article") or "-"
    return "%s %s" % (code, article)


def _ref_text(ref):
    """出处引用 → 文本（只用 ``source``/``version``，**不含 URL**，见 FR-06.4）。"""
    if not isinstance(ref, dict):
        return ""
    parts = [ref.get("source") or ""]
    if ref.get("version"):
        parts.append("（%s）" % ref["version"])
    return "".join(parts)


def _formula_text(expr):
    """表达式树 → 可读公式文本（``var`` 换成中文标签，``const`` 保留系数 id）。"""
    if not isinstance(expr, dict):
        return ""
    op = expr.get("op")
    if op == "var":
        return _VAR_LABELS.get(expr.get("ref"), expr.get("ref"))
    if op == "const":
        return expr.get("ref")
    symbol = _OP_SYMBOLS.get(op)
    args = expr.get("args") or []
    if symbol is None:
        return op or ""
    return "(" + symbol.join(_formula_text(arg) for arg in args) + ")"


def _unit_chain_text(line):
    """单位换算链 → 单行文本（无换算步则说明"无换算"）。"""
    steps = line.get("unit_chain") or []
    if not steps:
        return "无换算（活动数据与因子已在基本单位口径）"
    return "；".join(
        "%s %s→%s（×%s）" % (step.get("target"), step.get("from_unit"),
                            step.get("to_unit"), step.get("scale"))
        for step in steps
    )


def _process_text(report, line):
    """单源公式代入文本（§4 核算过程）。"""
    formula = _formula_text((report or {}).get("formula")) or "排放量"
    return "%s = %s %s" % (formula, line.get("emission"), UNIT_EMISSION)


def _boundary_rows(report):
    rows = []
    for src in (report.get("boundary") or {}).get("sources", []) or []:
        rows.append([
            src.get("id"),
            src.get("name"),
            src.get("category"),
            "是" if src.get("required") else "否",
            _MARK_INCLUDED if src.get("included") else _MARK_EXCLUDED,
            src.get("reason"),
            _clause_text(src.get("clause")),
        ])
    return rows


def _line_rows(report):
    rows = []
    for line in (report.get("calc") or {}).get("lines", []) or []:
        activity = line.get("activity") or {}
        base = line.get("activity_base") or {}
        factor = line.get("factor") or {}
        factor_base = line.get("factor_base") or {}
        rows.append([
            line.get("source_id"),
            line.get("source_name"),
            activity.get("value"),
            activity.get("unit"),
            base.get("value"),
            base.get("unit"),
            factor.get("value"),
            factor.get("unit"),
            factor.get("source"),
            line.get("oxidation_rate"),
            line.get("emission"),
            _clause_text(line.get("clause")),
        ])
    total = (report.get("calc") or {}).get("total")
    if total is not None:
        rows.append(["合计", "", "", "", "", "", "", "", "", "", total, ""])
    return rows


def _factor_rows(report):
    rows = []
    for row in report.get("factor_table", []) or []:
        rows.append([
            row.get("factor_id"),
            row.get("value"),
            row.get("unit"),
            row.get("source"),
            _ref_text(row.get("ref")),
            row.get("status"),
            "、".join(row.get("sources") or []),
        ])
    return rows


def _process_rows(report):
    rows = []
    for line in (report.get("calc") or {}).get("lines", []) or []:
        rows.append([
            line.get("source_id"),
            _process_text(report, line),
            _unit_chain_text(line),
            _clause_text(line.get("clause")),
        ])
    return rows


def _quality_rows(quality):
    rows = []
    for issue in (quality or {}).get("issues", []) or []:
        rows.append([
            _LEVEL_LABELS.get(issue.get("level"), issue.get("level")),
            issue.get("rule_id"),
            issue.get("source_id") or "全厂",
            issue.get("message"),
            _clause_text(issue.get("clause")),
            issue.get("advice"),
        ])
    return rows


def _quota_rows(quota):
    """配额试算 → 键值行（方法学 / 参数 / 结果 / 免责声明）。"""
    if not quota:
        return []
    rows = [
        ["坐标", quota.get("coordinate")],
        ["方法学", quota.get("method")],
        ["方法学依据", _clause_text(quota.get("method_clause"))],
        ["核算排放量(%s)" % UNIT_EMISSION, quota.get("actual")],
        ["试算配额量(%s)" % UNIT_EMISSION, quota.get("allocated")],
        ["履约缺口(%s)" % UNIT_EMISSION, quota.get("gap")],
        ["缺口占排放量比", quota.get("gap_ratio")],
    ]
    for key in sorted(quota.get("parameters") or {}):
        value = quota["parameters"][key]
        if isinstance(value, dict):
            rows.append(["参数 %s" % key,
                         "%s（来源：%s）" % (value.get("value"), value.get("source"))])
        else:
            rows.append(["参数 %s" % key, value])
    for note in quota.get("notes") or []:
        rows.append(["说明", note])
    if quota.get("disclaimer_required"):
        rows.append(["免责声明", quota.get("disclaimer") or "（缺失——不得对外输出）"])
    return rows


def _clause_rows(clause_index):
    rows = []
    for source in (clause_index or {}).get("sources", []) or []:
        rows.append([
            source.get("doc_no") or source.get("id"),
            source.get("title"),
            source.get("kind"),
            source.get("published"),
            source.get("effective") or "-",
            source.get("status_text"),
        ])
    return rows


def _provenance_rows(report):
    rows = []
    for row in report.get("provenance", []) or []:
        rows.append([
            row.get("position"),
            row.get("value"),
            row.get("activity_source"),
            row.get("factor_source"),
            _clause_text(row.get("clause")),
            row.get("rule_entry_id"),
        ])
    return rows


def _tables(report, quality=None, quota=None, clause_index=None):
    """全部导出表（CSV / XLSX 共用）。

    返回 ``[{name, headers, rows}]``；``name`` 即章节名，人读与机读同名。
    """
    head = report.get("report_head") or {}
    facility = report.get("facility") or {}
    return [
        {
            "name": SEC_HEAD,
            "headers": ["项目", "内容"],
            "rows": [
                ["报告主体", facility.get("name") or "（未命名）"],
                ["统一社会信用代码", facility.get("credit_code") or "-"],
                ["档案说明", facility.get("note") or "-"],
                ["规则包坐标", head.get("coordinate")],
                ["通则编号", head.get("standard_code")],
                ["行业", head.get("industry_label")],
                ["工具版本", head.get("tool_version") or __version__],
                ["生成时间", head.get("generated_at")],
                ["免责声明", head.get("disclaimer")],
            ],
        },
        {
            "name": SEC_BOUNDARY,
            "headers": ["源 id", "源名称", "类别", "应核算", "纳入判定", "纳入依据", "依据条款"],
            "rows": _boundary_rows(report),
        },
        {
            "name": SEC_LINES,
            "headers": ["源 id", "源名称", "活动数据", "单位", "活动数据(基本单位)", "基本单位",
                        "排放因子", "因子单位", "因子来源", "氧化率", "排放量(tCO2e)", "依据条款"],
            "rows": _line_rows(report),
        },
        {
            "name": SEC_FACTORS,
            "headers": ["因子 id", "数值", "单位", "来源层级", "出处", "status", "用于排放源"],
            "rows": _factor_rows(report),
        },
        {
            "name": SEC_PROCESS,
            "headers": ["源 id", "公式代入", "单位换算链", "依据条款"],
            "rows": _process_rows(report),
        },
        {
            "name": SEC_QUALITY,
            "headers": ["级别", "规则 id", "对象", "问题描述", "依据条款", "建议"],
            "rows": _quality_rows(quality),
        },
        {
            "name": SEC_QUOTA,
            "headers": ["项目", "内容"],
            "rows": _quota_rows(quota),
        },
        {
            "name": SEC_CLAUSES,
            "headers": ["编号", "名称", "类型", "发布", "实施", "状态"],
            "rows": _clause_rows(clause_index),
        },
        {
            "name": SEC_PROVENANCE,
            "headers": ["报告数字位置", "值", "活动数据来源", "因子来源", "规则条款", "规则包条目 id"],
            "rows": _provenance_rows(report),
        },
    ]


# --------------------------------------------------------------------------
# 人读 Markdown（plan/04 §6.1）
# --------------------------------------------------------------------------

def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return out


def _table_by_name(tables, name):
    for table in tables:
        if table["name"] == name:
            return table
    return {"name": name, "headers": [], "rows": []}


def render_markdown(report, quality=None, quota=None, clause_index=None):
    """渲染完整报告 Markdown（§0–§8，plan/04 §6.1）。

    ``quality`` / ``quota`` 为 ``None`` 时对应章节**显式写明"未启用"**，
    而不是留空——留空会被读者误读成"检查过且无问题"。
    """
    head = report.get("report_head") or {}
    facility = report.get("facility") or {}
    boundary = report.get("boundary") or {}
    calc = report.get("calc") or {}
    tables = _tables(report, quality=quality, quota=quota, clause_index=clause_index)

    lines = [
        TITLE,
        "",
        "## %s（可复现三要素，FR-06.3）" % SEC_HEAD,
        "",
    ]
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_HEAD)))

    lines += ["", "## %s" % SEC_BOUNDARY, "",
              "### 1.1 企业概况",
              "",
              "  报告主体：%s" % (facility.get("name") or "（未命名）"),
              "  统一社会信用代码：%s" % (facility.get("credit_code") or "-"),
              "  档案说明：%s" % (facility.get("note") or "-"),
              "",
              "### 1.2 应核算排放源清单",
              "",
              "  应核算 %d 项，纳入 %d 项。"
              % (boundary.get("required_count", 0), boundary.get("included_count", 0)),
              ""]
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_BOUNDARY)))

    lines += ["", "### 1.3 双标尺差异提示", ""]
    lines += _diff_lines(report.get("boundary_diff"))

    lines += ["", "## %s" % SEC_LINES, ""]
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_LINES)))
    lines += ["", "  排放总量：**%s %s**" % (calc.get("total"), UNIT_EMISSION)]

    lines += ["", "## %s" % SEC_FACTORS, ""]
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_FACTORS)))

    lines += ["", "## %s（逐源公式代入）" % SEC_PROCESS, ""]
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_PROCESS)))

    lines += ["", "## %s" % SEC_QUALITY, ""]
    lines += _quality_lines(quality, tables)

    lines += ["", "## %s" % SEC_QUOTA, ""]
    lines += _quota_lines(quota, tables)

    lines += ["", "## %s" % SEC_CLAUSES, ""]
    if clause_index:
        lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_CLAUSES)))
    else:
        lines.append("  " + NOTE_CLAUSES_ABSENT)

    lines += ["", "## %s（FR-06.2 核心）" % SEC_PROVENANCE, ""]
    counts = report.get("provenance_counts") or {}
    lines.append("  溯源行数 %s = 明细 %s + 因子 %s（plan/04 §6.3 完整性断言）。"
                 % (counts.get("total"), counts.get("detail_rows"), counts.get("factor_rows")))
    lines.append("")
    lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_PROVENANCE)))

    lines += ["", "---", "",
              "  本报告由 %s 生成；全部数值可回指规则包条目 id 与官方依据条款。"
              % ("ghg-accounting-workbench %s" % __version__)]
    return "\n".join(lines)


def _headers_rows(table):
    return table["headers"], table["rows"]


def _diff_lines(diff):
    if not diff:
        return ["  " + NOTE_NO_DIFF]
    adjusted = sorted({row["id"] for row in diff.get("adjusted") or []})
    return [
        "  基准：%s → 目标：%s" % (diff.get("base"), diff.get("target")),
        "",
        "  | 类别 | 排放源 |",
        "  |---|---|",
        "  | 新增 | %s |" % ("、".join(diff.get("added") or []) or "（无）"),
        "  | 取消 | %s |" % ("、".join(diff.get("removed") or []) or "（无）"),
        "  | 口径调整 | %s |" % ("、".join(adjusted) or "（无）"),
        "  | 未变化 | %s |" % ("、".join(diff.get("unchanged") or []) or "（无）"),
    ]


def _quality_lines(quality, tables):
    if quality is None:
        return ["  " + NOTE_CHECK_DISABLED]
    counts = quality.get("counts") or {}
    lines = [
        "  规则总数 %s，已执行 %s 条；问题计数：错误 %s / 警告 %s / 提示 %s（合计 %s）。"
        % (quality.get("rules_total"), len(quality.get("rules_executed") or []),
           counts.get("error", 0), counts.get("warning", 0), counts.get("info", 0),
           quality.get("issue_count")),
        "",
    ]
    rows = _table_by_name(tables, SEC_QUALITY)["rows"]
    if rows:
        lines += _md_table(*_headers_rows(_table_by_name(tables, SEC_QUALITY)))
    else:
        lines.append("  " + NOTE_NO_ISSUES)
    for skip in quality.get("rules_skipped") or []:
        lines.append("  [跳过] %s（%s）：%s"
                     % ("、".join(skip.get("rule_ids") or []), skip.get("type"),
                        skip.get("reason")))
    return lines


def _quota_lines(quota, tables):
    if quota is None:
        return ["  " + NOTE_QUOTA_DISABLED]
    lines = _md_table(*_headers_rows(_table_by_name(tables, SEC_QUOTA)))
    if not quota.get("disclaimer_required"):       # pragma: no cover - 结构体恒定 True
        lines.append("")
        lines.append("  **警告：免责声明缺失，本产物不得对外输出。**")
    return lines


def write_markdown(report, path, quality=None, quota=None, clause_index=None):
    """把人读报告写入 ``path``（UTF-8、LF、无 CR）。返回写入的路径。"""
    text = render_markdown(report, quality=quality, quota=quota, clause_index=clause_index)
    _write_bytes(path, text)
    return path


# --------------------------------------------------------------------------
# 机读 CSV（UTF-8 with BOM，LF，无外链）
# --------------------------------------------------------------------------

def _csv_cell(value):
    """CSV 单元格转义（含逗号/引号/换行或首尾空格时加引号）。"""
    text = "" if value is None else str(value)
    if any(ch in text for ch in (",", '"', "\n", "\r")) or text != text.strip():
        return '"' + text.replace('"', '""') + '"'
    return text


def render_csv(table):
    """单表 → CSV 文本（LF 行尾，**不含 BOM**；BOM 在落盘时加）。"""
    out = [",".join(_csv_cell(cell) for cell in table["headers"])]
    for row in table["rows"]:
        out.append(",".join(_csv_cell(cell) for cell in row))
    return "\n".join(out) + "\n"


def write_csv(report, out_dir, quality=None, quota=None, clause_index=None):
    """把全部机读表写入 ``out_dir``，返回写入的文件路径列表（按表序）。"""
    import os

    if not os.path.isdir(out_dir):
        raise InputError("CSV 输出目录不存在：%s" % out_dir)
    paths = []
    for table in _tables(report, quality=quality, quota=quota, clause_index=clause_index):
        path = os.path.join(out_dir, _csv_filename(table["name"]))
        _write_bytes(path, render_csv(table), bom=True)
        paths.append(path)
    return paths


def _csv_filename(name):
    """表名 → 文件名（去章节序号，保留中文可读性）。"""
    parts = name.split(" ", 1)
    label = parts[1] if len(parts) == 2 and parts[0].isdigit() else name
    return "%s.csv" % label


# --------------------------------------------------------------------------
# 机读 XLSX（最小 writer，零第三方依赖）
# --------------------------------------------------------------------------

_XLSX_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_PKG_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_CT_SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
_CT_WORKBOOK = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"

_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# 固定 ZIP 元数据（字节确定性，NFR-04）：不写系统时钟、不写宿主系统标识
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_ZIP_CREATE_SYSTEM = 0        # MS-DOS
_ZIP_EXTERNAL_ATTR = 0

_XLSX_MAX_SHEET_NAME = 31


def _xml_escape(text):
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col_letter(index):
    """0 → A，1 → B，…，25 → Z，26 → AA。"""
    letters = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def _sheet_name(name):
    """表名 → XLSX sheet 名（去章节序号；Excel 上限 31 字符且禁 []:*?/\\\\）。"""
    parts = name.split(" ", 1)
    label = parts[1] if len(parts) == 2 and parts[0].isdigit() else name
    for ch in "[]:*?/\\":
        label = label.replace(ch, "-")
    return label[:_XLSX_MAX_SHEET_NAME]


def _sheet_xml(table):
    rows = []
    all_rows = [table["headers"]] + [list(row) for row in table["rows"]]
    for r_idx, row in enumerate(all_rows, 1):
        cells = []
        for c_idx, value in enumerate(row):
            ref = "%s%d" % (_col_letter(c_idx), r_idx)
            if value is None:
                continue                      # 空单元格不写（Excel 默认空）
            text = _xml_escape(value)
            cells.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                         % (ref, text))
        rows.append('<row r="%d">%s</row>' % (r_idx, "".join(cells)))
    return ('%s<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>'
            % (_XML_DECL, _XLSX_NS_MAIN, "".join(rows)))


def _content_types_xml(sheet_count):
    overrides = "".join(
        '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="%s"/>'
        % (idx, _CT_SHEET) for idx in range(1, sheet_count + 1))
    return ('%s<Types xmlns="%s">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="%s"/>'
            '%s</Types>'
            % (_XML_DECL, _PKG_NS_CT, _CT_WORKBOOK, overrides))


def _root_rels_xml():
    return ('%s<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>' % (_XML_DECL, _PKG_NS_REL, _XLSX_NS_REL))


def _workbook_xml(sheet_names):
    sheets = "".join(
        '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_xml_escape(name), idx, idx)
        for idx, name in enumerate(sheet_names, 1))
    return ('%s<workbook xmlns="%s" xmlns:r="%s"><sheets>%s</sheets></workbook>'
            % (_XML_DECL, _XLSX_NS_MAIN, _XLSX_NS_REL, sheets))


def _workbook_rels_xml(sheet_count):
    rels = "".join(
        '<Relationship Id="rId%d" Type="%s/worksheet" Target="worksheets/sheet%d.xml"/>'
        % (idx, _XLSX_NS_REL, idx) for idx in range(1, sheet_count + 1))
    return ('%s<Relationships xmlns="%s">%s</Relationships>'
            % (_XML_DECL, _PKG_NS_REL, rels))


def render_xlsx_bytes(report, quality=None, quota=None, clause_index=None):
    """渲染 XLSX 字节（``ZIP_STORED`` + 固定元数据 → 同一输入逐字节一致）。"""
    import io

    tables = _tables(report, quality=quality, quota=quota, clause_index=clause_index)
    names = [_sheet_name(table["name"]) for table in tables]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in _xlsx_parts(tables, names):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = _ZIP_CREATE_SYSTEM
            info.external_attr = _ZIP_EXTERNAL_ATTR
            archive.writestr(info, data)
    return buffer.getvalue()


def _xlsx_parts(tables, names):
    """XLSX 包内各部件（顺序固定 → 字节确定）。"""
    yield "[Content_Types].xml", _content_types_xml(len(tables))
    yield "_rels/.rels", _root_rels_xml()
    yield "xl/workbook.xml", _workbook_xml(names)
    yield "xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(tables))
    for idx, table in enumerate(tables, 1):
        yield "xl/worksheets/sheet%d.xml" % idx, _sheet_xml(table)


def write_xlsx(report, path, quality=None, quota=None, clause_index=None):
    """把机读 XLSX 写入 ``path``（零第三方依赖、字节确定）。"""
    data = render_xlsx_bytes(report, quality=quality, quota=quota, clause_index=clause_index)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------

def _write_bytes(path, text, bom=False):
    """UTF-8 字节写入（LF、无 CR；CSV 可加 BOM 便于 Excel 识别编码）。"""
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with open(path, "wb") as fh:
        fh.write(data)
    return path


# --------------------------------------------------------------------------
# 便捷入口（CLI / GUI 共用）
# --------------------------------------------------------------------------

def load_clause_index(data_dir):
    """加载条款库（``data/knowledge/clauses.json``）；缺失返回 ``None``。

    报告 §7 依据清单用它；缺失不致命（章节会显式写明不可用），但**不得**编造依据。
    """
    import os

    from .jsonio import load

    path = os.path.join(data_dir, "knowledge", "clauses.json")
    if not os.path.isfile(path):
        return None
    return load(path)


def export_all(report, out_dir, formats=("md",), quality=None, quota=None,
               clause_index=None, basename="report"):
    """按 ``formats`` 导出报告，返回 ``{格式: [路径]}``。

    ``md`` → ``<basename>.md``；``csv`` → 一表一文件；``xlsx`` → ``<basename>.xlsx``。
    """
    import os

    if not os.path.isdir(out_dir):
        raise InputError("输出目录不存在：%s" % out_dir)
    written = {}
    for fmt in formats:
        if fmt not in FORMATS:
            raise InputError("不支持的报告格式：%r（可用：%s）"
                             % (fmt, " / ".join(FORMATS)))
        if fmt == "md":
            written["md"] = [write_markdown(
                report, os.path.join(out_dir, "%s.md" % basename),
                quality=quality, quota=quota, clause_index=clause_index)]
        elif fmt == "csv":
            written["csv"] = write_csv(report, out_dir, quality=quality, quota=quota,
                                       clause_index=clause_index)
        else:                                  # xlsx
            written["xlsx"] = [write_xlsx(
                report, os.path.join(out_dir, "%s.xlsx" % basename),
                quality=quality, quota=quota, clause_index=clause_index)]
    return written