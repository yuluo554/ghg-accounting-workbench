"""命令行入口（plan/03 §六 CLI 契约）。

退出码语义（锁定，不得漂移）：
  0 = 成功 / 门控通过 / 基准达标
  1 = 门控拦截（规则包含未核对条目）或基准未达标
  2 = 输入不可用 / 参数错误

本模块**零判定逻辑**：只做参数解析、调用引擎 API、渲染输出与退出码映射。
"""

import argparse
import json
import os
import sys

from . import __version__, jsonio
from .bench import SUITES, render_bench_text, run_bench
from .calc import compute
from .coordinates import Coordinate, parse_coordinate
from .decimals import to_text
from .errors import EXIT_GATE, EXIT_INPUT, EXIT_OK, GhgError, InputError, exit_code_for
from .paths import find_data_dir
from .pipeline import compute_full, render_report_text
from .quality import LEVEL_ERROR, render_quality_text, run_checks
from .quota import compute_quota, quota_inputs_from_profile, render_quota_text
from .report import (
    FORMATS,
    export_all,
    load_clause_index,
)
from .rules import (
    SCOPE_CALC,
    SCOPE_CHECK,
    SCOPE_QUOTA,
    RulesIndex,
    parse_payload_coordinate,
    SCHEMA_RULESET,
)
from .units import UnitTable

CLI_NAME = "ghg"


def _ensure_utf8_stdio():
    """按编码探针把 stdout/stderr 切换为 UTF-8。

    只在流编码**不支持**中文时才 reconfigure（中文控制台 cp936 保持不动）；
    否则 CI 的 cp1252 管道会让中文输出崩 UnicodeEncodeError（见 HANDOFF 环境坑）。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        enc = (getattr(stream, "encoding", None) or "").lower()
        if enc.replace("-", "") in ("utf8", "utf8mb4"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


class Context(object):
    """一次 CLI 调用的运行上下文（数据目录 + 索引 + 单位表）。"""

    def __init__(self, data_dir=None, as_json=False, preview=False):
        self.data_dir = find_data_dir(data_dir)
        self.index = RulesIndex.load(self.data_dir)
        self.units = UnitTable.load(self.data_dir)
        self.as_json = as_json
        self.preview = preview

    def emit(self, payload, text):
        if self.as_json:
            sys.stdout.write(jsonio.dumps(payload))
        else:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")


# --------------------------------------------------------------------------
# 子命令实现
# --------------------------------------------------------------------------

def cmd_coords(ctx, args):
    coords = ctx.index.coordinates()
    payload = {
        "standards": ctx.index.standards,
        "years": ctx.index.years,
        "industries": ctx.index.industries,
        "count": len(coords),
        "coordinates": [c.key for c in coords],
    }
    labels_s = ctx.index._manifest.get("labels", {}).get("standards", {})
    labels_i = ctx.index._manifest.get("labels", {}).get("industries", {})
    lines = ["规则包坐标空间（通则版本 × 年度 × 行业）",
             "  通则：%s" % "、".join("%s（%s）" % (k, labels_s.get(k, "")) for k in ctx.index.standards),
             "  年度：%s" % "、".join(str(y) for y in ctx.index.years),
             "  行业：%s" % "、".join("%s（%s）" % (k, labels_i.get(k, "")) for k in ctx.index.industries),
             "  坐标总数：%d" % len(coords)]
    ctx.emit(payload, "\n".join(lines))
    return EXIT_OK


def cmd_rules_show(ctx, args):
    coord = ctx.index.resolve(args.standard, args.year, args.industry)
    pack = ctx.index.pack(coord)
    report = ctx.index.gate_report(coord)
    calc_report = ctx.index.gate_report(coord, scope=SCOPE_CALC)
    if ctx.as_json:
        ctx.emit({"coordinate": coord.key, "gate": report,
                  "gate_calc": calc_report, "pack": pack}, "")
        return EXIT_OK
    def _line(report, label):
        if report["effective"]:
            return "  %s：通过（全部条目已核对）" % label
        return "  %s：拦截（%d 项未核对）" % (label, report["pending_count"])
    lines = ["规则包 %s" % coord.key,
             "  schema：%s" % pack.get("schema"),
             "  排放源条目：%d" % len(pack.get("boundary", {}).get("sources", [])),
             "  校核规则：%d" % len(pack.get("quality", {}).get("rules", [])),
             _line(calc_report, "核算路径门控"),
             _line(report, "整包门控")]
    if report["pending"]:
        for item in report["pending"][:10]:
            lines.append("    - %s（%s）" % (item["entry"], item["status"]))
        if report["pending_count"] > 10:
            lines.append("    … 其余 %d 项见 --json" % (report["pending_count"] - 10))
    text = "\n".join(lines)
    if args.preview:
        ctx.emit({"coordinate": coord.key, "gate": report, "gate_calc": calc_report}, text)
        return EXIT_OK
    # rules show 以**核算路径**门控为退出码判据（quota/quality 的 pending 不阻断核算预览）
    ctx.emit({"coordinate": coord.key, "gate": report, "gate_calc": calc_report}, text)
    return EXIT_OK if calc_report["effective"] else EXIT_GATE


def cmd_rules_check(ctx, args):
    """门控体检：默认检查全部坐标，或指定单个坐标。

    按作用域逐路径报告（范围见 plan/04 §4.3）：核算 / 配额 / 校核各查各的块。
    退出码以**核算路径**为准（三行业配额平衡值等不影响核算可用性）。
    """
    if args.standard and args.year and args.industry:
        targets = [ctx.index.resolve(args.standard, args.year, args.industry)]
    else:
        targets = ctx.index.coordinates()
    reports = []
    for coord in targets:
        calc = ctx.index.gate_report(coord, scope=SCOPE_CALC)
        quota = ctx.index.gate_report(coord, scope=SCOPE_QUOTA)
        check = ctx.index.gate_report(coord, scope=SCOPE_CHECK)
        reports.append({"coordinate": coord.key, "calc": calc,
                        "quota": quota, "check": check})
    calc_effective = [r for r in reports if r["calc"]["effective"]]
    payload = {
        "total": len(reports),
        "calc_effective": len(calc_effective),
        "calc_blocked": len(reports) - len(calc_effective),
        "reports": reports,
    }
    text = "\n".join([
        "规则包门控体检（分作用域）",
        "  坐标总数：%d" % len(reports),
        "  核算路径可通过：%d" % len(calc_effective),
        "  核算路径被拦截：%d" % (len(reports) - len(calc_effective)),
        "  配额路径可通过：%d" % len([r for r in reports if r["quota"]["effective"]]),
        "  校核路径可通过：%d" % len([r for r in reports if r["check"]["effective"]]),
    ])
    ctx.emit(payload, text)
    return EXIT_OK if not (len(reports) - len(calc_effective)) else EXIT_GATE


def cmd_calc(ctx, args):
    """核算入口（M2 完整编排）：门控 → 边界识别 → 逐源计算 → 因子表 → 溯源表。

    分层：门控与输入校验在此；编排由 :func:`ghg.pipeline.compute_full` 单点承担
    （CLI 与 GUI 共用，见 plan/04 §三）。
    """
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    report = compute_full(
        payload, coord, ctx.index, ctx.units,
        diff_standard=getattr(args, "diff_standard", None),
    )
    if getattr(args, "report", None):
        text = render_report_text(report)
        with open(args.report, "wb") as fh:
            fh.write(text.encode("utf-8"))
        report = dict(report)
        report["report_file"] = args.report
    if ctx.as_json:
        ctx.emit(report, "")
    else:
        ctx.emit(report, render_report_text(report))
    return EXIT_OK


def cmd_check(ctx, args):
    """数据质量校核入口（M3）：门控（校核路径）→ 四类检查 → 分级问题清单。

    退出码：校核路径门控拦截（quality 未生效）→ 1；问题清单含 error → 2；
    仅 warning/info 或无问题 → 0（对应 plan/03 §六 退出码语义）。
    """
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    pack = ctx.index.effective_ruleset(coord, scope=SCOPE_CHECK)
    calc = compute(payload, coord, ctx.index.effective_ruleset(coord, scope=SCOPE_CALC),
                   ctx.units)
    baseline = _baseline_calc(ctx, payload, coord, getattr(args, "baseline", None))
    report = run_checks(payload, calc, coord, pack, units=ctx.units, baseline=baseline)
    if ctx.as_json:
        ctx.emit(report, "")
    else:
        ctx.emit(report, render_quality_text(report))
    errors = report["counts"].get(LEVEL_ERROR, 0)
    return EXIT_INPUT if errors else EXIT_OK


def _baseline_calc(ctx, payload, coord, baseline_path):
    """载入上一年度同坐标核算结果（``yoy_jump`` 用）；未提供返回 None。"""
    if not baseline_path:
        return None
    other = jsonio.load(baseline_path)
    other_coord = parse_payload_coordinate(other, index=ctx.index)
    if other_coord.industry != coord.industry or other_coord.standard != coord.standard:
        raise InputError(
            "同比基线坐标不一致：%s vs %s（须同年同行业、仅年度不同）"
            % (other_coord.key, coord.key)
        )
    if other_coord.year == coord.year:
        raise InputError("同比基线年度与本次核算年度相同：%s" % other_coord.key)
    pack = ctx.index.effective_ruleset(other_coord, scope=SCOPE_CALC)
    return compute(other, other_coord, pack, ctx.units)


def cmd_quota(ctx, args):
    """配额试算入口（M3）：门控（配额路径）→ 方法学分支试算 → 免责声明强制。

    试算输入优先取命令行参数，其次取档案 ``quota_inputs``（``output`` 亦可取档案顶层字段）。
    """
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    pack = ctx.index.effective_ruleset(coord, scope=SCOPE_QUOTA)
    calc = compute(payload, coord, ctx.index.effective_ruleset(coord, scope=SCOPE_CALC),
                   ctx.units)
    params = quota_inputs_from_profile(payload)
    for key in ("benchmark_value", "correction_factor", "output", "historical_intensity"):
        value = getattr(args, key, None)
        if value is not None:
            params[key] = value
    report = compute_quota(pack, coord, calc["total_raw"], params=params)
    if ctx.as_json:
        ctx.emit(report, "")
    else:
        ctx.emit(report, render_quota_text(report))
    return EXIT_OK


def _quality_and_quota(ctx, payload, coord, calc, args):
    """按需执行校核与配额试算（报告 §5 / §6 用）；未启用返回 ``None``。

    校核/配额各自的**门控与输入错误在此暴露**（不吞异常）：校核路径 pending → 退出码 1，
    配额外部输入缺失 → 退出码 2。这正是"报告里写得出这一章"的前提。
    """
    quality = None
    quota = None
    if getattr(args, "with_check", False):
        pack = ctx.index.effective_ruleset(coord, scope=SCOPE_CHECK)
        baseline = _baseline_calc(ctx, payload, coord, getattr(args, "baseline", None))
        quality = run_checks(payload, calc, coord, pack, units=ctx.units, baseline=baseline)
    if getattr(args, "with_quota", False):
        pack = ctx.index.effective_ruleset(coord, scope=SCOPE_QUOTA)
        params = quota_inputs_from_profile(payload)
        for key in ("benchmark_value", "correction_factor", "output", "historical_intensity"):
            value = getattr(args, key, None)
            if value is not None:
                params[key] = value
        quota = compute_quota(pack, coord, calc["total_raw"], params=params)
    return quality, quota


def cmd_report(ctx, args):
    """可核证报告导出（FR-06，M5）：Markdown + CSV + XLSX 三产物一次落盘。

    复用 ``pipeline.compute_full`` 编排单点；``--with-check`` / ``--with-quota``
    追加报告 §5 校核章节与 §6 配额章节（各自走对应作用域门控）。
    导出后**复核溯源完整性**（plan/04 §6.3：不得导出"半溯源"报告）。
    """
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    report = compute_full(
        payload, coord, ctx.index, ctx.units,
        diff_standard=getattr(args, "diff_standard", None),
    )
    quality, quota = _quality_and_quota(ctx, payload, coord, report["calc"], args)
    clause_index = None if getattr(args, "no_clauses", False) else load_clause_index(ctx.data_dir)

    formats = _parse_formats(getattr(args, "format", None))
    out_dir = args.out_dir or "."
    if not os.path.isdir(out_dir):
        raise InputError("输出目录不存在：%s" % out_dir)
    written = export_all(report, out_dir, formats=formats, quality=quality, quota=quota,
                         clause_index=clause_index, basename=getattr(args, "basename", "report"))

    payload_out = {
        "coordinate": coord.key,
        "output_dir": os.path.abspath(out_dir),
        "formats": list(formats),
        "files": written,
        "provenance_counts": report["provenance_counts"],
    }
    if ctx.as_json:
        ctx.emit(payload_out, "")
        return EXIT_OK
    lines = ["可核证报告已导出（坐标 %s）" % coord.key,
             "  输出目录：%s" % os.path.abspath(out_dir)]
    for fmt in formats:
        for path in written.get(fmt, []):
            lines.append("  [%s] %s" % (fmt, os.path.basename(path)))
    counts = report["provenance_counts"]
    lines.append("  溯源完整性：%s 行 = 明细 %s + 因子 %s"
                 % (counts["total"], counts["detail_rows"], counts["factor_rows"]))
    if quality is not None:
        lines.append("  校核章节：问题 %s 条（错误 %s）"
                     % (quality["issue_count"], quality["counts"].get(LEVEL_ERROR, 0)))
    else:
        lines.append("  校核章节：未启用（--with-check 可追加）")
    if quota is not None:
        lines.append("  配额章节：方法学 %s，试算配额量 %s %s"
                     % (quota["method"], quota["allocated"], quota["unit"]))
    else:
        lines.append("  配额章节：未启用（--with-quota 可追加）")
    ctx.emit(payload_out, "\n".join(lines))
    return EXIT_OK


def _parse_formats(value):
    """解析 ``--format``（可重复）；缺省 md+csv+xlsx 三产物。"""
    if not value:
        return list(FORMATS)
    formats = []
    for item in value:
        for part in str(item).replace("，", ",").split(","):
            part = part.strip().lower()
            if not part:
                continue
            if part not in FORMATS:
                raise InputError("不支持的报告格式：%r（可用：%s）"
                                 % (part, " / ".join(FORMATS)))
            if part not in formats:
                formats.append(part)
    return formats or list(FORMATS)


def cmd_convert(ctx, args):
    value = args.value
    result = ctx.units.convert(value, args.from_unit, args.to_unit)
    payload = {
        "value": value,
        "from": args.from_unit,
        "to": args.to_unit,
        "result": str(result),
    }
    ctx.emit(payload, "%s %s = %s %s" % (value, args.from_unit,
                                         to_text(result), args.to_unit))
    return EXIT_OK


def cmd_units(ctx, args):
    dims = ctx.units.dimensions()
    lines = ["单位换算表（%s）" % "data/rules/units.json"]
    payload = {}
    for dim in sorted(dims.keys()):
        spec = dims[dim]
        lines.append("  %s：基准 %s；单位 %s"
                     % (dim, spec["base"], "、".join(sorted(spec["units"].keys()))))
        payload[dim] = {"base": spec["base"], "units": sorted(spec["units"].keys())}
    ctx.emit(payload, "\n".join(lines))
    return EXIT_OK


def cmd_bench(ctx, args):
    """内置离线基准入口（M4）：三类基准一条命令跑全。

    退出码（plan/03 §六）：0 = 三类基准达标；1 = 有指标未达标；2 = 用法/配置错误
    （suite 名非法、manifest 缺门槛配置）。基准层零 API 依赖、只读冻结产物。
    """
    suites = list(args.suite) if getattr(args, "suite", None) else None
    report = run_bench(data_dir=ctx.data_dir, suites=suites,
                       index=ctx.index, units=ctx.units)
    if ctx.as_json:
        ctx.emit(report, "")
    else:
        ctx.emit(report, render_bench_text(report))
    return EXIT_OK if report["ok"] else EXIT_GATE


def cmd_selftest(ctx, args):
    """内建自检：数据定位 + 坐标空间 + 门控 + 单位换算往返 + 报告导出。

    冻结态验收（exe --selftest）复用本命令；断言数据目录在预期位置（打包内）。
    """
    checks = []

    coords = ctx.index.coordinates()
    checks.append(("坐标空间完整", len(coords) > 0,
                   "%d 格" % len(coords)))

    # 门控必须生效：存在被拦截坐标（整包口径），同时报告核算路径可通过数
    reports = [ctx.index.gate_report(c) for c in coords]
    blocked = [r for r in reports if not r["effective"]]
    checks.append(("门控可拦截未核对条目", len(blocked) > 0 or len(coords) == 0,
                   "整包拦截 %d / 共 %d" % (len(blocked), len(coords))))
    calc_ok = [c for c in coords if ctx.index.gate_report(c, scope=SCOPE_CALC)["effective"]]
    checks.append(("核算路径存在可出数坐标", len(calc_ok) > 0 or len(coords) == 0,
                   "核算路径可通过 %d / 共 %d" % (len(calc_ok), len(coords))))

    # 单位换算往返
    roundtrip_ok = True
    detail = ""
    for unit in ctx.units.unit_list():
        dim = ctx.units.dimension_of(unit)
        base = ctx.units.dimensions()[dim]["base"]
        try:
            back = ctx.units.convert(ctx.units.convert("1", base, unit), unit, base)
            if back != ctx.units._factor[base]:
                roundtrip_ok = False
                detail = unit
        except GhgError:
            roundtrip_ok = False
            detail = unit
    checks.append(("单位换算往返一致", roundtrip_ok, detail or "全部单位通过"))

    # 报告导出可用（三产物 + 溯源完整性断言；不落盘，只在内存渲染）
    checks.append(_report_export_check(ctx, coords))

    # 冻结态：数据目录必须落在 exe 目录内（打包白名单与数据随包分发的前提）
    frozen = _frozen_data_check(ctx)
    if frozen is not None:
        checks.append(frozen)

    ok = all(item[1] for item in checks)
    payload = {
        "data_dir": ctx.data_dir,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "ok": ok,
        "checks": [{"name": n, "ok": v, "detail": d} for n, v, d in checks],
    }
    if ctx.as_json:
        ctx.emit(payload, "")
    else:
        lines = ["自检：工具版本 %s" % __version__, "  数据目录：%s" % ctx.data_dir]
        for name, passed, detail in checks:
            lines.append("  [%s] %s（%s）" % ("OK" if passed else "FAIL", name, detail))
        lines.append("结论：%s" % ("全部通过" if ok else "存在失败项"))
        ctx.emit(payload, "\n".join(lines))
    return EXIT_OK if ok else EXIT_GATE


def _report_export_check(ctx, coords):
    """自检项：在第一个核算路径可通过的坐标上跑通报告渲染（含溯源断言）。"""
    from .report import render_markdown, render_xlsx_bytes

    target = None
    for coord in coords:
        if ctx.index.gate_report(coord, scope=SCOPE_CALC)["effective"]:
            target = coord
            break
    if target is None:
        return ("报告导出可用", True, "无核算路径可通过坐标（跳过）")
    payload = _selftest_profile(ctx, target)
    try:
        report = compute_full(payload, target, ctx.index, ctx.units,
                              generated_at="selftest")
        markdown = render_markdown(report)
        render_xlsx_bytes(report)
    except GhgError as exc:
        return ("报告导出可用", False, "%s: %s" % (target.key, exc))
    counts = report["provenance_counts"]
    complete = counts["total"] == counts["detail_rows"] + counts["factor_rows"]
    return ("报告导出可用（MD/XLSX + 溯源完整）", complete and bool(markdown),
            "%s：溯源 %s 行" % (target.key, counts["total"]))


def _selftest_profile(ctx, coord):
    """用规则包声明的应核算排放源合成一份最小档案（自检不依赖 data/truth/）。"""
    pack = ctx.index.effective_ruleset(coord, scope=SCOPE_CALC)
    sources = []
    for src in pack.get("boundary", {}).get("sources", []) or []:
        if not src.get("required"):
            continue
        unit = _activity_unit_of(pack, src.get("category"))
        sources.append({"source_id": src["id"],
                        "activity": {"value": "1", "unit": unit}})
    return {
        "coordinate": {"standard": coord.standard, "year": coord.year,
                       "industry": coord.industry},
        "facility": {"name": "自检（合成）", "synthetic": True},
        "sources": sources,
    }


def _activity_unit_of(pack, category):
    """取该类别行业缺省因子的分母单位作为活动数据单位（缺省回落到吨）。"""
    defaults = (pack.get("factors", {}) or {}).get("industry_default_values", {}) or {}
    entry = (defaults.get("by_category") or {}).get(category) or defaults.get("default_factor")
    unit = (entry or {}).get("unit") or ""
    _numerator, denominator = unit.partition("_per_")[0], unit.partition("_per_")[2]
    return denominator or "t"


def _frozen_data_check(ctx):
    """冻结态断言：数据目录必须落在 exe 目录内（打包白名单与随包分发的前提）。

    非冻结态（源码运行）返回 ``None``（该项不适用），避免把源码运行误判为失败。
    """
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    data_dir = os.path.abspath(ctx.data_dir)
    try:
        inside = os.path.commonpath([exe_dir, data_dir]) == exe_dir
    except ValueError:                        # 不同盘符 → 必然不在
        inside = False
    return ("冻结态数据目录在 exe 目录内", inside,
            "exe=%s data=%s" % (exe_dir, data_dir))


def cmd_version(ctx, args):
    payload = {"version": __version__, "schema": SCHEMA_RULESET}
    ctx.emit(payload, "%s %s" % (CLI_NAME, __version__))
    return EXIT_OK


# --------------------------------------------------------------------------
# 参数解析
# --------------------------------------------------------------------------

def _add_coord_args(parser, required=False):
    parser.add_argument("--standard", required=required, help="通则短键（见 ghg coords）")
    parser.add_argument("--year", type=int, required=required, help="核算年度")
    parser.add_argument("--industry", required=required, help="行业短键（见 ghg coords）")


def build_parser():
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description="企业温室气体排放核算与报告工作台（本地核算，零上传）",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("--data-dir", default=None, help="数据目录（默认自动定位）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--selftest", dest="selftest", action="store_true",
                        help="内建自检（打包产物验收；等价 selftest 子命令，见 FR-08.3）")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("coords", help="列出规则包坐标空间")
    p.set_defaults(func=cmd_coords)

    p = sub.add_parser("rules", help="规则包查看与门控体检")
    rsub = p.add_subparsers(dest="rules_command")
    ps = rsub.add_parser("show", help="查看单个坐标的规则包与门控状态")
    _add_coord_args(ps, required=True)
    ps.add_argument("--preview", action="store_true", help="只读预览（允许显示未核对条目）")
    ps.set_defaults(func=cmd_rules_show)
    pc = rsub.add_parser("check", help="门控体检（全部坐标或单个坐标）")
    _add_coord_args(pc, required=False)
    pc.set_defaults(func=cmd_rules_check)

    p = sub.add_parser("calc", help="核算（边界识别 + 逐源计算 + 溯源表）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.add_argument("--diff-standard", default=None,
                   help="附带双标尺差异（另一版通则短键，同年同行业）")
    p.add_argument("--report", default=None,
                   help="同时把 Markdown 报告写入指定路径（FR-06.1）")
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("check", help="数据质量校核（四类检查 + 分级问题清单）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.add_argument("--baseline", default=None,
                   help="上一年度同坐标企业档案 JSON（用于跨年度突变检查）")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("quota", help="行业配额试算（方法学分支 + 免责声明）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.add_argument("--method", default=None, help="覆盖方法学（默认取规则包 quota.method）")
    p.add_argument("--benchmark-value", dest="benchmark_value", default=None,
                   help="行业平衡值 / 发电基准值（规则包不承载时须显式提供）")
    p.add_argument("--correction-factor", dest="correction_factor", default=None,
                   help="调峰修正系数 / 强度系数 α（显式给定则跳过推导）")
    p.add_argument("--output", default=None, help="产量 / 发电量（基准法、强度系数法需要）")
    p.add_argument("--historical-intensity", dest="historical_intensity", default=None,
                   help="历史强度（历史强度法需要）")
    p.set_defaults(func=cmd_quota)

    p = sub.add_parser("report", help="可核证报告导出（Markdown + CSV + XLSX，FR-06）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.add_argument("--out-dir", dest="out_dir", default=None,
                   help="输出目录（缺省当前目录）")
    p.add_argument("--format", action="append", default=None,
                   help="导出格式，可重复或逗号分隔（可用：%s；缺省三产物全出）"
                        % " / ".join(FORMATS))
    p.add_argument("--basename", default="report", help="Markdown/XLSX 文件名主干")
    p.add_argument("--diff-standard", default=None,
                   help="报告 §1.3 双标尺差异（另一版通则短键，同年同行业）")
    p.add_argument("--with-check", dest="with_check", action="store_true",
                   help="追加报告 §5 数据质量校核章节（走校核路径门控）")
    p.add_argument("--with-quota", dest="with_quota", action="store_true",
                   help="追加报告 §6 配额试算章节（走配额路径门控）")
    p.add_argument("--baseline", default=None,
                   help="上一年度同坐标企业档案 JSON（--with-check 的跨年度突变检查用）")
    p.add_argument("--benchmark-value", dest="benchmark_value", default=None,
                   help="行业平衡值 / 发电基准值（--with-quota；规则包不承载时须显式给出）")
    p.add_argument("--correction-factor", dest="correction_factor", default=None,
                   help="调峰修正系数 / 强度系数 α（--with-quota）")
    p.add_argument("--output", default=None, help="产量 / 发电量（--with-quota）")
    p.add_argument("--historical-intensity", dest="historical_intensity", default=None,
                   help="历史强度（--with-quota）")
    p.add_argument("--no-clauses", dest="no_clauses", action="store_true",
                   help="不加载条款库（报告 §7 依据清单显式标注不可用）")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("convert", help="单位换算")
    p.add_argument("--value", required=True, help="数值（字符串，避免浮点）")
    p.add_argument("--from", dest="from_unit", required=True, help="源单位")
    p.add_argument("--to", dest="to_unit", required=True, help="目标单位")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("units", help="列出单位换算表")
    p.set_defaults(func=cmd_units)

    p = sub.add_parser("selftest", help="内建自检")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("bench", help="内置离线基准（规则自洽 / 因子与单位 / 边界用例）")
    p.add_argument("--suite", action="append", default=None,
                   help="只跑指定套件（可重复；可用：%s；缺省三类全跑）"
                        % "、".join(SUITES))
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("version", help="打印工具版本")
    p.set_defaults(func=cmd_version)

    return parser


def main(argv=None):
    _ensure_utf8_stdio()
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])

    # 打包产物验收入口：`exe --selftest`（无子命令，见 FR-08.3）
    selftest_only = False
    if "--selftest" in argv:
        argv = [a for a in argv if a != "--selftest"]
        selftest_only = not argv or argv[0].startswith("-")

    if not argv and not selftest_only:
        parser.print_help()
        return EXIT_INPUT

    # `rules` 子命令必须带 show/check 二级命令
    if argv and argv[0] == "rules" and (len(argv) == 1 or argv[1].startswith("-")):
        sys.stderr.write("错误：rules 需要二级命令 show 或 check\n")
        return EXIT_INPUT

    # 顶层开关（--data-dir / --json）先于子命令；纯 --selftest 时补上 selftest 子命令
    if selftest_only:
        argv = argv + ["selftest"]

    args = parser.parse_args(argv)

    if not getattr(args, "command", None) or not hasattr(args, "func"):
        parser.print_help()
        return EXIT_INPUT

    try:
        ctx = Context(data_dir=args.data_dir, as_json=args.json,
                      preview=getattr(args, "preview", False))
        return args.func(ctx, args)
    except GhgError as exc:
        sys.stderr.write("错误：%s\n" % exc)
        return exit_code_for(exc)
    except FileNotFoundError as exc:
        sys.stderr.write("错误：文件不存在 %s\n" % exc)
        return EXIT_INPUT
    except ValueError as exc:
        sys.stderr.write("错误：输入非法 %s\n" % exc)
        return EXIT_INPUT


if __name__ == "__main__":
    sys.exit(main())
