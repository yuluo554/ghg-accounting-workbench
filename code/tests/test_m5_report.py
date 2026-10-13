"""M5 报告导出测试（FR-06）：MD / CSV / XLSX 三产物 + 可核证性 + 字节确定性。

对账纪律：
  * 报告内容与 ``pipeline.compute_full`` / ``quality.run_checks`` / ``quota.compute_quota``
    的输出逐字段一致（渲染层不得自行改数）；
  * **溯源完整性**（plan/04 §6.3）：报告内溯源行数 == 明细 + 因子；
  * **无外链**（FR-06.4）：CSV/XLSX 内不得出现 ``http://`` / ``https://``；
  * **字节确定性**（NFR-04）：同一输入两次导出逐字节一致（XLSX 含 ZIP 元数据固定）。
"""

import os
import zipfile

import pytest

from ghg import jsonio, report as R
from ghg.pipeline import compute_full
from ghg.quality import run_checks
from ghg.quota import compute_quota, quota_inputs_from_profile
from ghg.rules import SCOPE_CHECK, SCOPE_QUOTA, parse_payload_coordinate

FIXED_TIME = "2026-10-13T00:00:00"


@pytest.fixture
def steel(data_dir):
    return jsonio.load(os.path.join(data_dir, "truth", "profiles", "steel-2024.json"))


@pytest.fixture
def bundle(rules_index, unit_table, data_dir, steel):
    """一份完整的报告素材：编排结果 + 校核 + 配额 + 条款库。"""
    coord = parse_payload_coordinate(steel, index=rules_index)
    report = compute_full(steel, coord, rules_index, unit_table, generated_at=FIXED_TIME)
    quality = run_checks(steel, report["calc"], coord,
                         rules_index.effective_ruleset(coord, scope=SCOPE_CHECK),
                         units=unit_table)
    params = dict(quota_inputs_from_profile(steel) or {})
    params["benchmark_value"] = "2"
    quota = compute_quota(rules_index.effective_ruleset(coord, scope=SCOPE_QUOTA),
                          coord, report["calc"]["total_raw"], params=params)
    return {
        "report": report,
        "quality": quality,
        "quota": quota,
        "clauses": R.load_clause_index(data_dir),
    }


# ---------- Markdown ----------

def test_markdown_has_all_sections(bundle):
    """plan/04 §6.1 骨架：§0 报告头 … §8 数据溯源表 全在。"""
    text = R.render_markdown(bundle["report"], quality=bundle["quality"],
                             quota=bundle["quota"], clause_index=bundle["clauses"])
    for section in (R.SEC_HEAD, R.SEC_BOUNDARY, R.SEC_LINES, R.SEC_FACTORS,
                    R.SEC_PROCESS, R.SEC_QUALITY, R.SEC_QUOTA, R.SEC_CLAUSES,
                    R.SEC_PROVENANCE):
        assert "## %s" % section in text, "报告缺少章节：%s" % section


def test_markdown_head_has_reproducible_triplet(bundle):
    """FR-06.3：报告头固定输出「规则包坐标 + 工具版本 + 生成时间」。"""
    text = R.render_markdown(bundle["report"])
    head = bundle["report"]["report_head"]
    assert head["coordinate"] in text
    assert head["tool_version"] in text
    assert FIXED_TIME in text


def test_markdown_disabled_sections_are_explicit_not_blank(bundle):
    """未启用的章节必须显式写明"未启用"，不得留空（留空会被误读为"检查过且没问题"）。"""
    text = R.render_markdown(bundle["report"])
    assert R.NOTE_CHECK_DISABLED in text
    assert R.NOTE_QUOTA_DISABLED in text


def test_markdown_quota_renders_mandatory_disclaimer(bundle):
    """R3 / NFR-10：配额章节必须输出免责声明文本。"""
    text = R.render_markdown(bundle["report"], quota=bundle["quota"])
    assert "免责声明" in text
    assert bundle["quota"]["disclaimer"] in text


def test_markdown_provenance_counts_match(bundle):
    """plan/04 §6.3：溯源行数 == 明细 + 因子（报告内自述与结构一致）。"""
    counts = bundle["report"]["provenance_counts"]
    assert counts["total"] == counts["detail_rows"] + counts["factor_rows"]
    text = R.render_markdown(bundle["report"])
    assert "溯源行数 %s = 明细 %s + 因子 %s" % (counts["total"], counts["detail_rows"],
                                               counts["factor_rows"]) in text


# ---------- CSV ----------

def test_csv_written_for_every_table(bundle, tmp_path):
    paths = R.write_csv(bundle["report"], str(tmp_path), quality=bundle["quality"],
                        quota=bundle["quota"], clause_index=bundle["clauses"])
    assert len(paths) == len(R._tables(bundle["report"]))
    for path in paths:
        assert os.path.isfile(path)


def test_csv_is_utf8_bom_lf_without_cr(bundle, tmp_path):
    """机读产物：UTF-8 with BOM（Excel 双击可读）+ LF（无 CR，NFR-04）。"""
    paths = R.write_csv(bundle["report"], str(tmp_path))
    for path in paths:
        raw = open(path, "rb").read()
        assert raw.startswith(b"\xef\xbb\xbf"), "CSV 缺 BOM：%s" % path
        assert b"\r" not in raw, "CSV 含 CR：%s" % path
        raw.decode("utf-8")                       # 必须可 UTF-8 解码


def test_csv_has_no_external_links(bundle, tmp_path):
    """FR-06.4：机读产物不得含外链（断网可开、可归档）。"""
    paths = R.write_csv(bundle["report"], str(tmp_path), quality=bundle["quality"],
                        quota=bundle["quota"], clause_index=bundle["clauses"])
    for path in paths:
        text = open(path, "rb").read().decode("utf-8")
        assert "http://" not in text and "https://" not in text, "CSV 含外链：%s" % path


def test_csv_escapes_delimiters_and_quotes():
    """CSV 转义：含逗号/引号/换行必须加引号（否则列会错位）。"""
    table = {"name": "t", "headers": ["a", "b"],
             "rows": [["x,y", 'say "hi"'], ["p\nq", None]]}
    text = R.render_csv(table)
    assert '"x,y"' in text
    assert '"say ""hi"""' in text
    assert '"p\nq"' in text


# ---------- XLSX ----------

def test_xlsx_is_valid_zip_with_expected_parts(bundle, tmp_path):
    path = str(tmp_path / "r.xlsx")
    R.write_xlsx(bundle["report"], path, quality=bundle["quality"], quota=bundle["quota"],
                 clause_index=bundle["clauses"])
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert "[Content_Types].xml" in names
        assert "_rels/.rels" in names
        assert "xl/workbook.xml" in names
        sheets = [n for n in names if n.startswith("xl/worksheets/")]
        assert len(sheets) == len(R._tables(bundle["report"]))


def test_xlsx_is_byte_deterministic(bundle):
    """NFR-04：ZIP 元数据固定 → 同一输入两次导出逐字节一致。"""
    first = R.render_xlsx_bytes(bundle["report"], quality=bundle["quality"],
                                quota=bundle["quota"], clause_index=bundle["clauses"])
    second = R.render_xlsx_bytes(bundle["report"], quality=bundle["quality"],
                                 quota=bundle["quota"], clause_index=bundle["clauses"])
    assert first == second


def test_xlsx_has_no_external_links(bundle):
    """FR-06.4：XLSX **单元格数据**不得含外链（断网可开、可归档）。

    OOXML 的命名空间 URI（``http://schemas.openxmlformats.org/...``）是格式结构标识，
    不是外链；本测试只查工作表里的可见文本与关系项是否指向外部资源。
    """
    import io
    import re
    data = R.render_xlsx_bytes(bundle["report"], quality=bundle["quality"],
                               quota=bundle["quota"], clause_index=bundle["clauses"])
    cell_text = re.compile(r"<t[^>]*>(.*?)</t>", re.S)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            text = archive.read(name).decode("utf-8", "replace")
            for cell in cell_text.findall(text):
                assert "http://" not in cell and "https://" not in cell, \
                    "XLSX 单元格含外链：%s" % name
            # 关系项不得声明为外部目标（External hyperlink 才是真外链）
            assert 'TargetMode="External"' not in text, "XLSX 含外部关系：%s" % name


def test_xlsx_zip_metadata_is_fixed(bundle):
    """ZIP 条目的时间/宿主系统必须固定（否则跨机器字节漂移）。"""
    import io
    data = R.render_xlsx_bytes(bundle["report"])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            assert info.date_time == R._ZIP_DATE_TIME
            assert info.create_system == R._ZIP_CREATE_SYSTEM


def test_xlsx_sheet_names_strip_section_numbers(bundle):
    names = [R._sheet_name(t["name"]) for t in R._tables(bundle["report"])]
    assert "报告头" in names
    assert all(not n[0].isdigit() for n in names)
    assert all(len(n) <= R._XLSX_MAX_SHEET_NAME for n in names)


# ---------- export_all 编排 ----------

def test_export_all_writes_three_formats(bundle, tmp_path):
    written = R.export_all(bundle["report"], str(tmp_path), formats=("md", "csv", "xlsx"),
                           quality=bundle["quality"], quota=bundle["quota"],
                           clause_index=bundle["clauses"], basename="rep")
    assert written["md"] and written["csv"] and written["xlsx"]
    assert os.path.basename(written["md"][0]) == "rep.md"
    assert os.path.basename(written["xlsx"][0]) == "rep.xlsx"
    md = open(written["md"][0], "rb").read()
    assert b"\r" not in md


def test_export_all_rejects_unknown_format(bundle, tmp_path):
    from ghg.errors import InputError
    with pytest.raises(InputError):
        R.export_all(bundle["report"], str(tmp_path), formats=("pdf",))


def test_export_all_rejects_missing_dir(bundle, tmp_path):
    from ghg.errors import InputError
    with pytest.raises(InputError):
        R.export_all(bundle["report"], str(tmp_path / "nope"), formats=("md",))


def test_load_clause_index_absent_returns_none(tmp_path):
    assert R.load_clause_index(str(tmp_path)) is None


# ---------- 溯源可核证（FR-06.2 核心）----------

def test_provenance_rule_entry_ids_resolve(bundle, rules_index):
    """每条溯源行的 ``rule_entry_id`` 必须能在该坐标包内解析（不得悬空）。"""
    from ghg.pipeline import resolve_rule_entry
    coord = parse_payload_coordinate(bundle["report"]["facility"] and
                                     {"coordinate": {"standard": "gbt32150-2025", "year": 2024,
                                                     "industry": "steel"}},
                                     index=rules_index)
    pack = rules_index.pack(coord)
    for row in bundle["report"]["provenance"]:
        resolve_rule_entry(pack, row["rule_entry_id"])


def test_formula_trace_present_in_report(bundle):
    """§4 核算过程：公式代入文本来自规则包表达式树（非代码内联）。"""
    rows = R._process_rows(bundle["report"])
    assert rows and all(row[1] for row in rows)
    assert bundle["report"]["formula"], "编排结果未携带公式表达式树"


def test_clause_index_renders_source_list(bundle):
    rows = R._clause_rows(bundle["clauses"])
    assert rows, "条款库依据清单不得为空"
    assert all(row[0] and row[1] for row in rows)