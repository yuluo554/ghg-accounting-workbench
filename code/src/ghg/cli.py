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
from .coordinates import Coordinate, parse_coordinate
from .decimals import to_text
from .errors import EXIT_GATE, EXIT_INPUT, EXIT_OK, GhgError, exit_code_for
from .paths import find_data_dir
from .rules import RulesIndex, parse_payload_coordinate, SCHEMA_RULESET
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
    if ctx.as_json:
        ctx.emit({"coordinate": coord.key, "gate": report, "pack": pack}, "")
        return EXIT_OK
    gate_line = ("门控：通过（全部条目已核对）" if report["effective"]
                 else "门控：拦截（%d 项未核对）" % report["pending_count"])
    lines = ["规则包 %s" % coord.key,
             "  schema：%s" % pack.get("schema"),
             "  排放源条目：%d" % len(pack.get("boundary", {}).get("sources", [])),
             "  校核规则：%d" % len(pack.get("quality", {}).get("rules", [])),
             "  %s" % gate_line]
    if report["pending"]:
        for item in report["pending"][:10]:
            lines.append("    - %s（%s）" % (item["entry"], item["status"]))
        if report["pending_count"] > 10:
            lines.append("    … 其余 %d 项见 --json" % (report["pending_count"] - 10))
    text = "\n".join(lines)
    if args.preview:
        ctx.emit({"coordinate": coord.key, "gate": report}, text)
        return EXIT_OK
    ctx.emit({"coordinate": coord.key, "gate": report}, text)
    return EXIT_OK if report["effective"] else EXIT_GATE


def cmd_rules_check(ctx, args):
    """门控体检：默认检查全部坐标，或指定单个坐标。"""
    if args.standard and args.year and args.industry:
        targets = [ctx.index.resolve(args.standard, args.year, args.industry)]
    else:
        targets = ctx.index.coordinates()
    reports = [ctx.index.gate_report(coord) for coord in targets]
    effective = [r for r in reports if r["effective"]]
    blocked = [r for r in reports if not r["effective"]]
    payload = {
        "total": len(reports),
        "effective": len(effective),
        "blocked": len(blocked),
        "reports": reports,
    }
    text = "\n".join([
        "规则包门控体检",
        "  坐标总数：%d" % len(reports),
        "  可通过（全部已核对）：%d" % len(effective),
        "  被拦截（存在未核对条目）：%d" % len(blocked),
    ])
    ctx.emit(payload, text)
    return EXIT_OK if not blocked else EXIT_GATE


def cmd_calc(ctx, args):
    """核算入口：M0 只做门控与输入校验（计算引擎 M2 落地）。"""
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    # 门控：pending 规则包不得进入计算路径
    ctx.index.effective_ruleset(coord)
    # 走到这里说明规则包已全部核对；M0 数据初态不会到达
    ctx.emit({"coordinate": coord.key, "status": "ready"},
             "规则包 %s 已通过门控（计算引擎于 M2 落地）" % coord.key)
    return EXIT_OK


def cmd_check(ctx, args):
    """数据质量校核入口：M0 只做门控（校核层 M3 落地）。"""
    payload = jsonio.load(args.input)
    coord = parse_payload_coordinate(payload, index=ctx.index)
    rules = ctx.index.effective_ruleset(coord).get("quality", {})
    ctx.emit({"coordinate": coord.key, "rules": len(rules.get("rules", []))},
             "规则包 %s 已通过门控（校核层于 M3 落地）" % coord.key)
    return EXIT_OK


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


def cmd_selftest(ctx, args):
    """内建自检：数据定位 + 坐标空间 + 门控 + 单位换算往返。

    冻结态验收（exe --selftest）复用本命令；断言数据目录在预期位置。
    """
    checks = []

    coords = ctx.index.coordinates()
    checks.append(("坐标空间完整", len(coords) > 0,
                   "%d 格" % len(coords)))

    # 门控必须生效：数据初态下存在被拦截坐标
    reports = [ctx.index.gate_report(c) for c in coords]
    blocked = [r for r in reports if not r["effective"]]
    checks.append(("门控可拦截未核对条目", len(blocked) > 0 or len(coords) == 0,
                   "拦截 %d / 共 %d" % (len(blocked), len(coords))))

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

    ok = all(item[1] for item in checks)
    payload = {
        "data_dir": ctx.data_dir,
        "version": __version__,
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

    p = sub.add_parser("calc", help="核算（M0：门控 + 输入校验）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("check", help="数据质量校核（M0：门控）")
    p.add_argument("--input", required=True, help="企业档案 JSON")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("convert", help="单位换算")
    p.add_argument("--value", required=True, help="数值（字符串，避免浮点）")
    p.add_argument("--from", dest="from_unit", required=True, help="源单位")
    p.add_argument("--to", dest="to_unit", required=True, help="目标单位")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("units", help="列出单位换算表")
    p.set_defaults(func=cmd_units)

    p = sub.add_parser("selftest", help="内建自检")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("version", help="打印工具版本")
    p.set_defaults(func=cmd_version)

    return parser


def main(argv=None):
    _ensure_utf8_stdio()
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])

    if not argv:
        parser.print_help()
        return EXIT_INPUT

    # `rules` 子命令必须带 show/check 二级命令
    if argv[0] == "rules" and (len(argv) == 1 or argv[1].startswith("-")):
        sys.stderr.write("错误：rules 需要二级命令 show 或 check\n")
        return EXIT_INPUT

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
