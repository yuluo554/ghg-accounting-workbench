# HANDOFF-M6 —— 续接快照（M0/M1/M2/M3/M4/M5 已完成，下一棒 = M6 脱敏发布 + 收尾固化）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M6.md" 继续完成任务`
> **本快照状态**：✅ 有效（M5 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 + M1 + M2 + M3 + M4 + M5 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06`；05 已回写 M1–**M5** DoD；06 已加 D1-1~7 / D2-1~7 / D3-1~5 / D4-1~5 / **D5-1~8** |
| 核心包 `code/src/ghg/` | ✅ | errors/decimals/jsonio/paths/coordinates/rules/units/engine/calc/boundary/pipeline/quality/quota/bench/**report**/cli **十六个模块** |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；`tools/gen_rulesets.py`（v0.3.0）；重生成位级一致 |
| 门控分作用域 + 第三态 `input_required` | ✅ | `RulesIndex.effective_ruleset(coord, scope)`：`calc`/`quota`/`check` |
| 边界识别 + 双标尺差异（M2） | ✅ | `code/src/ghg/boundary.py` |
| 显式单位换算链（M2） | ✅ | `calc.UnitChain`；分隔符单一真相源 `units.PER_SEPARATOR` |
| 完整编排单点（M2） | ✅ | `code/src/ghg/pipeline.py`（M5 补 `formula` 表达式树） |
| 溯源完整性硬约束（M2） | ✅ | `pipeline._assert_provenance_complete` |
| 四类数据质量校核（M3） | ✅ | `code/src/ghg/quality.py` |
| 配额试算方法学分支（M3） | ✅ | `code/src/ghg/quota.py`（4 分支） |
| 免责声明强制（M3） | ✅ | `QuotaResult.disclaimer_required` 恒 True |
| 内置离线基准（M4） | ✅ | `code/src/ghg/bench.py`；`ghg bench` 三类全绿 |
| **报告导出三产物（M5）** | ✅ | `code/src/ghg/report.py`：`render_markdown` / `write_csv` / `write_xlsx` + `export_all` |
| **报告 §0–§8 九张表** | ✅ | 报告头 / 边界 / 明细 / 因子表 / 核算过程 / 校核 / 配额 / 依据清单 / 溯源表；CSV/XLSX 与人读同名 |
| **无外链 + XLSX 字节确定** | ✅ | 机读产物无 URL；自研最小 writer（`ZIP_STORED` + 固定元数据），两次导出逐字节一致 |
| **CLI `report` 子命令** | ✅ | `--format md,csv,xlsx` / `--with-check` / `--with-quota` / `--diff-standard` |
| **GUI 四页签（M5）** | ✅ | `code/gui/ghg_gui/`：核算 / 校核 / 配额 / 基准；**只消费引擎 API** |
| **GUI offscreen 测试常驻** | ✅ | `QT_QPA_PLATFORM=offscreen`（conftest 默认）；四页签逐个跑通填表 |
| **GUI 导入门禁** | ✅ | AST 静态检查：页面/模型不得 import `ghg.calc`/`quality`/`quota`/`bench`（唯一入口 `service.py`） |
| **PyInstaller onedir 双 exe（M5）** | ✅ | `tools/ghg_cli.spec` / `ghg_gui.spec` + `entry_cli.py` / `entry_gui.py`；实测 CLI 13 MB、GUI 101 MB |
| **`exe --selftest` 通过（数据目录在 dist 内）** | ✅ | 自检项「冻结态数据目录在 exe 目录内」；实测隔离目录 rc 0 |
| **打包白名单断言（M5）** | ✅ | `tools/ghg_packaging.py`（单一真相源）+ `test_m5_packaging.py` 19 项（含探活） |
| **演示素材入 `docs/demo/`** | ✅ | 四页签 PNG（离屏渲染）+ `demo-cli.txt`（含 rc 0/1/2 谱）；`tools/gen_demo.py` 可复跑 |
| **技术报告 md（M5）** | ✅ | `docs/技术报告.md`（含留白清单） |
| 测试套件 | ✅ | `code/tests/` **18 个文件，288 passed**（py3.8 与 py3.12 双跑） |
| 零政策字面量门禁 | ✅ | 扫描范围**含 GUI**（D5-3）；token 集 **13 个** → 退出码 0 |
| CI workflow | ✅ | 三矩阵 + `fetch-depth: 0` + bench + **report 导出冒烟**；本地守门测试通过（GitHub 首跑仍待 M6） |
| README / data 台账 | ✅ | README 已转 M5 状态；目录结构 / 快速开始 / 测试数已更新 |

**M5 关键数字**：报告 **9 张表**；双 exe **CLI 13 MB / GUI 101 MB**；
测试 204 → **288**（+84：报告 21 / GUI 23 / 打包 19 / 演示 9 / CLI 报告与自检 12）；
基准运行时长 **≈ 0.034 秒**（NFR-11 上限 2 秒）；门禁 token 集 **13**。

**未做（M5 刻意不做）**：脱敏发布、Release、`gh repo create`/push（M6，对外动作）。

## 二、M6 待办（脱敏发布 + 收尾固化）

按 `plan/05` §二 M6 与 `plan/06` §四「发布前必办」：

1. **提交元数据脱敏**（O-6）：当前 `git log --format="%ae %ce"` 可见**真实个人邮箱**；
   发布前 `git filter-branch --env-filter` 全历史改写为 GitHub noreply，
   改后清 `refs/original` + reflog + `gc`，用**固定字面值** grep 验证 **ae 与 ce 两个字段**。
   无远端时改写成本最低 —— M0–M5 期间产生的提交务必一次性处理。
2. **未提交的工作树改动**：M0–M5 的 `code/`、`data/`、`tools/`、`docs/` 改动**尚未提交**
   （判据是位级一致守门测试，不是 `git status`）；发布前须形成**有序提交**（数据产物与代码同批），
   提交信息注明里程碑。
3. **脱敏审计脚本固化**：把脱敏四步做成入仓可复跑脚本 + 守门测试。
4. **构建产物扫描**：`dist/` 与 exe 内不得含个人邮箱 / 真实企业数据 / 绝对路径泄露；
   发布附件用 **ASCII 名 + sha256 留档**。
5. **干净环境验证**：新 clone + 全新 venv，逐条照 README 跑通（含 GUI offscreen 与打包）。
6. **建立远端 + 发布**：`gh repo create ... --source . --remote origin`（**不带 `--push`**）
   → 切 SSH → push（**对外动作，先向用户确认**）→ tag + Release（附双 exe）。
7. **CI 首跑**：首次 push 即首跑；按需诊断环境差异型失败（编码/EOL/系统库）。
   **注意**：CI 现已含 `tools/bench.py` 与 report 导出冒烟，三矩阵都要确认通过
   （Ubuntu 上 GUI 测试需 PySide6，CI 已改为安装 `.[dev,gui]`；若无显示相关库缺失需诊断）。
8. **官方因子库补摘**（O-7）：复核 data.ncsc.org.cn 是否可直连（或改用浏览器会话）；
   能摘则补 `data/factors/` 并重跑相关测试。
9. **`plan/RELEASE-M6.md` 留档** + README 状态行转正。

**M6 DoD**：见 `plan/05` §二 M6；README 状态行转正；Release 附件 ASCII 名 + sha256 留档；
发布后 GitHub 全新 clone 复核；`plan/RELEASE-M6.md` 留档。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

P1–P26 见 `plan/HANDOFF-M5.md` §三（未变）。**M5 新增**：

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| **P27** | **零政策字面量门禁扫描范围含 GUI**：`code/src/ghg/**` + `code/gui/ghg_gui/**` | `tools/check_zero_literals.py` `DEFAULT_TARGETS`（06 D5-3） | 门禁命中面、GUI 源码纪律 |
| **P28** | **GUI 引擎调用收口于 `ghg_gui/service.py`**：页面/视图模型不得直接 import `ghg.calc`/`quality`/`quota`/`bench` | `test_m5_gui.py` AST 门禁（06 D5-4） | "界面/CLI 同源"审计 |
| **P29** | **打包数据白名单**：`DATA_WHITELIST`（含用途）+ `DATA_EXCLUDE`（`knowledge/raw`）；未登记目录 → 打包自检失败 | `tools/ghg_packaging.py`（06 D5-5） | dist 体积、冻结态数据定位、打包守门 |
| **P30** | **报告章节"未启用"显式写出**（不留空） | `report.NOTE_CHECK_DISABLED` / `NOTE_QUOTA_DISABLED`（06 D5-8） | 报告渲染、核证可读性 |
| **P31** | **XLSX 字节确定性**：`ZIP_STORED` + 固定 `create_system`/`date_time`；禁引 openpyxl | `report.render_xlsx_bytes`（06 D5-1） | 报告字节守门、无第三方依赖纪律 |
| **P32** | **冻结态自检断言数据目录在 exe 目录内**；非冻结态该项不适用（不报 FAIL） | `cli._frozen_data_check`（06 D5-6） | 打包验收、源码运行不误判 |

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`）；脚本一律 `py -X utf8`。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`，单轮崩溃直接重试。
   **M5 实测**：py3.12 跑全量时 pytest 在格式化 traceback 阶段 access violation 崩溃
   （根因是**陈旧 pycache**）；清 `__pycache__` 后 288 passed。**遇崩溃先清缓存再重试**。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **`Path.write_text(newline=)` 是 3.10+**：3.8 上报错，统一用 `write_bytes`。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通；临时文件用工作区相对路径或 `tmp_path` 夹具。
   **M5 实测**：`os.path.relpath` 跨盘符（C: → D:）抛 `ValueError`，展示路径须 try/except 回落绝对路径。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。
   **GUI 测试**：conftest 已默认 `QT_QPA_PLATFORM=offscreen`，无需手动设。
7. **`git status` 的 M 状态含 M0–M5 未提交改动**：判据是位级一致守门测试，不是 `git status`。
8. **配额 CLI 的数值参数一律按字符串解析**（`as_decimal`），避免 float 进计算路径。
9. **`py -X utf8 -m ghg.cli` 需 `PYTHONPATH=code/src`**；**GUI 需再补 `code/gui`**。
10. **官方 PDF/HTML 快照为 UTF-8**：`decode('utf-8')`（勿用 gbk）。
11. **CI YAML 的 `name:` 值里别写半角 `: `**（全角冒号可以）；否则 `test_workflows.py` 报 ScannerError。
12. **PyInstaller spec 里没有 `__file__`**：用 PyInstaller 注入的 `SPECPATH`；
    且**别把辅助模块命名为 `packaging.py`**——会与 PyInstaller 自带的 `packaging` 包冲突
    （M5 实测：`AttributeError: module 'packaging' has no attribute 'repo_root'`）；
    改名 `ghg_packaging.py` 后正常。
13. **PyInstaller `datas` 的目录源语义**：目录源是把**内容**拷进目标目录，文件源才是拷成
    `目标/文件名`。目标路径要按源类型分别算，否则整棵树被拍平、`data/rules/manifest.json`
    定位标记丢失、冻结态 exe 找不到数据（M5 实测踩过）。
14. **offscreen Qt 找不到系统字体目录**：中文渲染成豆腐块；需
    `QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")`（或 Deng.ttf）。
15. **子进程 stdout 在 Windows 是文本模式**：会把 `\n` 翻成 `\r\n`；
    写文本产物前须 `.replace("\r\n", "\n")`（否则 CR 守门测试挂）。

## 五、DoD 逐项 checklist（M5）

- [x] M5-1 报告导出三产物（`render_markdown` / `write_csv` / `write_xlsx`）
- [x] M5-2 报告含 M3 章节（§5 校核 / §6 配额），未启用时显式写明
- [x] M5-3 可复现三要素（坐标 + 工具版本 + 生成时间）
- [x] M5-4 无外链（CSV/XLSX 单元格与关系项）
- [x] M5-5 XLSX 字节确定性（`ZIP_STORED` + 固定元数据）
- [x] M5-6 溯源完整性硬约束（行数对账 + `rule_entry_id` 可解析）
- [x] M5-7 CLI `report` 子命令（含 `--with-check` / `--with-quota` / `--diff-standard`）
- [x] M5-8 GUI 四页签，只消费引擎 API、零判定逻辑
- [x] M5-9 GUI 导入门禁（AST 静态检查）
- [x] M5-10 界面结论 == 引擎结论（同输入同输出）
- [x] M5-11 GUI offscreen 测试常驻（四页签逐个跑通填表）
- [x] M5-12 PyInstaller onedir 双 exe（CLI 13 MB / GUI 101 MB）
- [x] M5-13 `exe --selftest` 通过且数据目录在 dist 内（隔离目录实测 rc 0）
- [x] M5-14 打包白名单断言（含未登记目录探活）
- [x] M5-15 核对留档不进包（`knowledge/raw` 显式排除）
- [x] M5-16 冻结态定位标记不变量（`data/rules/manifest.json` 可达）
- [x] M5-17 演示素材入 `docs/demo/`（截图 + 命令行记录，可复跑）
- [x] M5-18 技术报告 md（`docs/技术报告.md`）
- [x] M5-19 门禁扫描范围扩到 GUI（D5-3）
- [x] M5-20 回归不破：288 passed（双解释器）；门禁 0 命中；基准三类达标

**偏差说明（如实留档）**：
- **`data/knowledge/raw/` 不进发布包**：官方原文快照（约 11 MB）是**核对留档**，
  非运行时依赖（报告 §7 只用 `clauses.json` 索引）。需复核数值出处者请用仓库全量数据。
- **GUI 页签 4 个**：`coords` / `units` / `convert` 属查表型命令（CLI 强项），不设独立页签。
- **演示素材为 PNG 而非 GIF**：GIF 需额外依赖且要录制窗口交互，与"素材可脚本复跑"冲突；
  改为四页签离屏截图 + 命令行文本记录（后者含 rc 0/1/2 全谱）。
- **配额页缺省需显式填外部输入**：平衡值/修正系数属 `input_required`，未填即失败态（与 CLI 一致）。
- 官方因子库（第二版）站点（data.ncsc.org.cn）直连仍恒返回 **HTTP 412（WAF）**，仍无摘录条目；
  2 个坐标（新旧通则 × 2026 发电）核算路径仍被门控拦截，核算路径 **38/40**。

## 六、关键命令速查

```bash
# 全量测试（288 项；GUI 测试自动 offscreen）
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照；扫引擎 + GUI，token 集 13 个）
py -X utf8 tools/check_zero_literals.py --selftest

# 内置基准（三类全跑；退出码 0 达标 / 1 未达标 / 2 用法错误）
py -X utf8 tools/bench.py
PYTHONPATH=code/src py -X utf8 -m ghg.cli --json bench   # 机器可读

# 四生成器链式重生成（应位级一致，用守门测试判定而非 git status）
py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_factors.py && \
py -X utf8 tools/gen_knowledge.py && py -X utf8 tools/gen_synthetic.py

# CLI 实测（退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check            # → rc 1（核算路径仍有 2 坐标被拦）
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json   # → rc 0
PYTHONPATH=code/src py -X utf8 -m ghg.cli bench                                              # → rc 0
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest                                           # → rc 0
PYTHONPATH=code/src py -X utf8 -m ghg.cli --selftest                                         # → rc 0（打包入口）

# 报告导出（三产物；§5/§6 按需）
PYTHONPATH=code/src py -X utf8 -m ghg.cli report --input data/truth/profiles/steel-2024.json \
  --out-dir . --with-check --with-quota --benchmark-value 2 --output 166150                   # → rc 0

# GUI（offscreen）
QT_QPA_PLATFORM=offscreen PYTHONPATH="code/src;code/gui" py -X utf8 -m ghg_gui.main --selftest  # → rc 0

# 打包（双 exe）+ 验收
py -X utf8 -m PyInstaller tools/ghg_cli.spec --noconfirm
py -X utf8 -m PyInstaller tools/ghg_gui.spec --noconfirm
./dist/ghg-cli/ghg-cli.exe --selftest        # → rc 0（断言数据目录在 dist 内）
./dist/ghg-gui/ghg-gui.exe --selftest        # → rc 0

# 演示素材重生成
QT_QPA_PLATFORM=offscreen py -X utf8 tools/gen_demo.py   # → docs/demo/
```

## 七、下一棒建议动作顺序（M6）

1. 先跑一遍"关键命令速查"，确认基线仍绿（防"接手时已经不绿"）。
2. 读 `plan/05` §二 M6、`plan/06` §四「发布前必办」与 O-6/O-7。
3. **先做脱敏与提交**（无远端时成本最低）：写脱敏脚本 → 形成有序提交 → 全历史邮箱改写 → 验证两个字段。
4. 构建产物扫描（dist/exe 内不得含邮箱、真实企业数据、绝对路径泄露）。
5. 干净环境验证（新 clone + 全新 venv 逐条照 README）。
6. **向用户确认后**建立远端、push、tag + Release（附双 exe，ASCII 名 + sha256）。
7. 首跑 CI 并诊断三矩阵差异；`plan/RELEASE-M6.md` 留档；README 状态行转正。

## 八、发布前必办（清单汇总）

| 项 | 状态 | 动作 |
|---|---|---|
| **提交元数据邮箱** | ⚠️ 真实个人邮箱（`git log --format="%ae %ce"` 可见） | M6 发布前全历史改写为 GitHub noreply（06 O-6）；清 refs/original + reflog + gc；固定字面值 grep 验证 **ae 与 ce** |
| **未提交的工作树改动** | ⚠️ M0–M5 的 `code/`、`data/`、`tools/`、`docs/` 改动尚未提交 | 发布前形成有序提交（数据产物与代码同批） |
| 远端仓库 | 尚未建立（`git remote -v` 为空） | `gh repo create ... --source . --remote origin`（**不带 --push**）→ 切 SSH → push（对外动作，先向用户确认） |
| 脱敏审计脚本 | 尚未固化 | M6 前把脱敏四步做成入仓可复跑脚本 + 守门测试 |
| CI 首跑 | 未跑（无远端） | 首次 push 即首跑；确认三矩阵 bench + report 冒烟 + GUI 测试均通过 |
| **构建产物白名单** | ✅ M5 已落（`tools/ghg_packaging.py`） | M6 只需在此基础上做"发布附件扫描" |
| **官方因子库补摘** | WAF 阻断未摘录（06 O-7） | M6 前复核站点是否可直连；能摘则补 `data/factors/` 并重跑相关测试 |