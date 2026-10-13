# HANDOFF-M5 —— 续接快照（M0/M1/M2/M3/M4 已完成，下一棒 = M5 桌面交付 + 报告导出）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M5.md" 继续完成任务`
> （路径用相对形式 `plan/HANDOFF-M5.md`，启动命令由用户侧拼绝对路径。）
> **本快照状态**：✅ 有效（M4 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 + M1 + M2 + M3 + M4 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06`；05 已回写 M1/M2/M3/**M4** DoD，06 已加 D1-1~7 / D2-1~7 / D3-1~5 / **D4-1~5** |
| 核心包 `code/src/ghg/` | ✅ | errors/decimals/jsonio/paths/coordinates/rules/units/engine/calc/boundary/pipeline/quality/quota/**bench**/cli **十五个模块** |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；`tools/gen_rulesets.py`（**v0.3.0**，新增 `BENCH_TARGETS`）；重生成位级一致 |
| 门控分作用域 + 第三态 `input_required` | ✅ | `RulesIndex.effective_ruleset(coord, scope)`：`calc`/`quota`/`check`；`_entry_is_effective` 放行 `input_required`（06 D1-1 / D3-2） |
| 规则数值逐条挂官方原文核对 | ✅ | 全 verified 或显式 pending/input_required；`data/README.md` §二 |
| 官方因子库台账 | ✅ | `data/factors/manifest.json`；**站点 WAF 阻断（412）如实留空**（06 D1-4 / O-7） |
| 边界识别 + 双标尺差异（M2） | ✅ | `code/src/ghg/boundary.py` |
| 显式单位换算链（M2） | ✅ | `calc.UnitChain`；复合单位分隔符单一真相源在 `units.PER_SEPARATOR`（06 D3-3） |
| 因子按类别分派 + 优先级（M2） | ✅ | `calc._select_factor` |
| 完整编排单点（M2） | ✅ | `code/src/ghg/pipeline.py` |
| 溯源完整性硬约束（M2） | ✅ | `pipeline._assert_provenance_complete` |
| 四类数据质量校核（M3） | ✅ | `code/src/ghg/quality.py` |
| 配额试算方法学分支（M3） | ✅ | `code/src/ghg/quota.py`：benchmark / intensity_coefficient / historical_intensity / none |
| 免责声明强制（M3） | ✅ | `QuotaResult.disclaimer_required` 恒 True |
| **内置离线基准（M4）** | ✅ | `code/src/ghg/bench.py`：`run_bench` / `suite_rules` / `suite_factor` / `suite_cases` |
| **三类基准一条命令跑全（M4）** | ✅ | CLI `ghg bench` + `tools/bench.py`（薄封装）；退出码 0/1/2 |
| **门槛是数据不是代码（M4）** | ✅ | `manifest.bench.targets` + `RulesIndex.bench_targets()`（06 D4-1） |
| **基准可证伪（M4）** | ✅ | `test_m4_bench.py` 6 个探活用例（注入缺陷 → 必须报未达标，06 D4-2） |
| 合成企业档案 + 真值库 | ✅ | `data/truth/`（**8 核算档案 + 12 用例 + `controls` 对照集声明**）；`tools/gen_synthetic.py` |
| 真值双路对账（核算 + 校核 + 配额） | ✅ | `test_m2_engine.py` / `test_m3_quality_quota.py` / `bench.suite_cases` |
| 条款库 + 官方原文快照 | ✅ | `data/knowledge/clauses.json`（11 依据 / 21 快照）+ `raw/` |
| `calc` / `check` / `quota` 端到端 | ✅ | 核算 38/40、校核 40/40、配额 40/40 坐标退出码 0 |
| **`bench` 三类基准全绿（M4 DoD）** | ✅ | 规则 480/480、因子 116/116、用例 29/29；命中 12/12、误报 0/8；**≈0.036 秒** |
| 测试套件 | ✅ | `code/tests/` **14 个文件，204 passed**（py3.8 与 py3.12 双跑） |
| 零政策字面量门禁 | ✅ | token 集 **13 个** → 退出码 0 |
| CI workflow | ✅ | 三矩阵 + `fetch-depth: 0` + **新增 `python tools/bench.py` 步骤**；本地守门测试通过（GitHub 首跑仍待 M6） |
| README / data 台账 | ✅ | README 已转 M4 状态（基准表实测值已填）；`data/README.md` §一/§三 已更新 |

**M4 关键数字**：规则自洽率 **100%（480/480）**、因子与单位一致率 **100%（116/116）**、
异常用例命中率 **100%（12/12）**、误报率 **0%（8 个干净对照档案零命中）**、
单次全量运行 **≈ 0.036 秒**（NFR-11 上限 2 秒，门槛随 manifest 下发）。
测试 179 → **202**；生成器版本 0.2.0 → **0.3.0**（manifest 新增 `bench.targets`）。

**未做（M4 刻意不做）**：GUI/打包/XLSX·CSV 报告导出（M5）、发布（M6）。
校核与配额的报告章节（报告 §5/§6）并入 M5 的报告导出。

## 二、M5 待办（桌面交付 + 报告导出）

按 `plan/05-数据计划与里程碑.md` §二 M5 与 `plan/02` FR-06/FR-08：

1. **报告导出（FR-06）**：`report.render_markdown` / `write_csv` / `write_xlsx` 三个落盘产物；
   内容含 M2 的报告头/边界/明细/因子表/溯源表 + **M3 的校核章节（§5）与配额章节（§6）**；
   Markdown 已有 `pipeline.render_report_text` 可复用（M2 只产内存文本，M5 落盘）。
2. **GUI（FR-08，P1）**：PySide6 多页签（核算 / 校核 / 配额 / 基准），**只消费引擎 API，零判定逻辑**；
   复用 `pipeline.compute_full` / `quality.run_checks` / `quota.compute_quota` / `bench.run_bench`。
3. **打包**：PyInstaller onedir 双 exe（CLI + GUI）；数据目录解析走 `paths.find_data_dir` 冻结分支；
   `exe --selftest` 必须通过（断言数据目录落在 dist 内）。
4. **GUI offscreen 测试常驻**（`QT_QPA_PLATFORM=offscreen`），不得依赖真实显示器。
5. **演示物**：`docs/demo/` 放截图/GIF。

**M5 DoD**：见 `plan/05` §二 M5；GUI offscreen 测试常驻、`exe --selftest` 通过、打包白名单断言、演示物入 `docs/demo/`。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| P1 | 条目 id 命名（`source.id` 全局稳定，不随年度改名） | `tools/gen_rulesets.py` | 双标尺 diff、真值库、报告溯源表 |
| P2 | `status` 门控语义：`pending` 绝不进**其自身路径**（含 `value: null` 的 verified 条目）；**`input_required` 放行** | `rules._entry_is_effective` + `SCOPE_BLOCKS` | CLI 退出码、全部基准 |
| P3 | CLI 退出码 0/1/2 语义（校核含 error→2；配额外部输入缺失→2；**基准未达标→1、用法错误→2**） | `errors.py` + `plan/03 §六` | CLI 测试、批处理用户 |
| P4 | 冻结产物字节口径：无 CR、无时间戳、键排序固定、`write_bytes` | `jsonio.write` + `gen_*.py` | 冻结守门测试、manifest sha256 |
| P5 | 表达式文法白名单（`mul/add/sub/div/var/const`；const 必须 ref） | `engine.py` | 引擎求值器、规则包校验、基准自洽扫描 |
| P6 | 零政策字面量门禁：**只扫引擎/前端源码**（`code/src/ghg/**`）；token 从规则包数值字段采集（**现 13 个**） | `tools/check_zero_literals.py` + `plan/06 §二` | 门禁测试 |
| P7 | 免责声明文本（法律文本，入代码豁免门禁） | `gen_rulesets.py` `DISCLAIMER` | 报告模板、02 R3、`quota` 渲染 |
| P8 | 坐标空间与短键（`gbt32150-2015/2025`、2022–2026、四行业） | `data/rules/manifest.json`（单一真相源） | 坐标测试、CLI、文档计数 |
| P9 | 门控按计算路径分作用域 | `rules.SCOPE_BLOCKS` / `effective_ruleset(scope)` | CLI 退出码判据、基准作用域划分检查 |
| P10 | 行业缺省因子 = 官方缺省值按标准公式合成 | `gen_rulesets._factors_block` | 零字面量 token 集、算例真值 |
| P11 | 四生成器链式依赖：rules → factors → knowledge → synthetic | `tools/gen_*.py` | 位级一致测试 |
| P12 | 双标尺差异以 `delta_vs_2015` 声明为准 + 结构交叉校验 | `boundary.diff_boundary` | 差异输出、基准双标尺检查 |
| P13 | 单位换算链三段式 | `calc.UnitChain` | 明细行字段 |
| P14 | 档案自报因子来源须落在 `factors.priority` 白名单内 | `calc._select_factor` | 因子选择、退出码 2、基准优先级检查 |
| P15 | 溯源表行数 == 明细 + 因子，`rule_entry_id` 必须可解析 | `pipeline._assert_provenance_complete` | 报告导出、溯源断言 |
| P16 | CLI `calc` 走 `pipeline.compute_full` 编排单点 | `cli.cmd_calc` | CLI 输出结构 |
| P17 | 校核阈值属工程判据（非政策数值）：`quality.thresholds` 四项 `verified`，`clause.code=null` | `gen_rulesets.QUALITY_THRESHOLDS`（06 D3-1） | 校核路径门控、零字面量 token 集 |
| P18 | 配额参数三态：`verified` / `input_required` / `pending` | `gen_rulesets._quota_block`（06 D3-2） | 配额路径门控、`QuotaUnavailable` |
| P19 | 校核分级可降级：规则的 level 是硬违规级别；可换算/可解释时降一级 | `quality._check_unit_consistency`（06 D3-4） | `check` 退出码判据、基准分级降级检查 |
| P20 | 配额结果双口径：量化呈现字段 + `*_raw` 全精度对账字段 | `quota.compute_quota`（06 D3-5） | 配额测试对账、基准配额用例对账 |
| P21 | 复合单位分隔符单一真相源：`units.PER_SEPARATOR` / `units.split_compound_unit` | `units.py`（06 D3-3） | 校核单位一致性 + calc 因子换算 + 基准因子单位拆分 |
| **P22** | **基准验收门槛是数据不是代码**：`manifest.bench.targets`；缺失即 `BenchConfigError`（退出码 2），不回落到代码默认值 | `rules.bench_targets` + `gen_rulesets.BENCH_TARGETS`（06 D4-1） | `ghg bench` 全部判定 |
| **P23** | **基准必须可证伪**：每套件配"注入缺陷 → 必须报未达标"探活 | `test_m4_bench.py`（06 D4-2） | 基准可信度 |
| **P24** | **公式变量集与系数集分列校验**：`var` 须落在 `calc.FORMULA_VARS`；`const` 须解析到 `engine.coefficients` | `engine.collect_refs_by_op` + `calc.FORMULA_VARS`（06 D4-3） | 基准规则自洽扫描 |
| **P25** | **误报对照集由真值库显式声明**：`expected.json` 的 `controls` 块；基准层不内联档案名 | `gen_synthetic.py` + `bench._control_checks`（06 D4-4） | 误报率指标 |
| **P26** | **`--suite` 部分运行不判定未测指标** | `bench._verdicts` 按 `metrics` 存在性过滤（06 D4-5） | `ghg bench --suite X` 用法 |

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`）；脚本一律 `py -X utf8`。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`，单轮崩溃直接重试。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **Path.write_text(newline=) 是 3.10+**：3.8 上报错，统一用 `write_bytes`。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通；临时文件用工作区相对路径或 `tmp_path` 夹具。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。
7. **`git status` 的 M 状态含 M0–M4 未提交改动**：本仓库 `code/`、`data/`、`tools/` 改动**尚未提交**。
   判据是 `test_synthetic_regeneration_is_bitwise_identical`（临时目录重生成 + sha256 逐份比对），
   不是 `git status`。
8. **配额 CLI 的数值参数一律按字符串解析**（`as_decimal`），避免 float 进计算路径。
9. **`py -X utf8 -m ghg.cli` 需 `PYTHONPATH=code/src`**（或先 `pip install -e code`）。
10. **官方 PDF/HTML 快照为 UTF-8**：`data/knowledge/raw/*.txt` 直接 `open(...,'rb').read().decode('utf-8')`
    （勿用 gbk，会崩）；pdfplumber/pdftotext 可用。
11. **CI YAML 的 `name:` 值里别写 `: `**（中文全角冒号可以，半角 `: ` 会被 YAML 当映射键 → `test_workflows.py` 直接报 `ScannerError`）。
    本次实测踩过一次，被守门测试拦住（这正是该测试存在的意义）。

## 五、DoD 逐项 checklist（M4）

- [x] M4-1 规则自洽基准（40 包 × 12 项 = 480/480）+ 双标尺差异声明与结构交叉一致
- [x] M4-2 因子一致性基准（116/116：单位往返 / 基准因子恒 1 / 跨量纲拒绝 / 因子单位拆分 / 跨年不漂移 / 跨通则一致 / 优先级白名单 / 孤儿类别）
- [x] M4-3 边界与异常用例基准（29/29；用例命中 12/12；误报 0/8）
- [x] M4-4 一条命令跑全 + 退出码 0/1/2（`ghg bench` / `tools/bench.py`）
- [x] M4-5 指标进 README 基准表（自洽率 / 一致率 / 命中率 / 误报率 / 运行时长，实测值已填）
- [x] M4-6 门槛取自 `manifest.bench.targets`，缺失即退出码 2
- [x] M4-7 基准可证伪（6 个探活用例）
- [x] M4-8 只读 + 确定性（data/ 逐份 sha256 不变；两次运行结果一致）
- [x] M4-9 运行时长符合 NFR-11（≈0.036 秒 < 2 秒）
- [x] M4-10 回归不破：204 passed（py3.8 + py3.12）；门禁 0 命中；四生成器位级一致

**偏差说明（如实留档）**：
- 官方因子库（第二版）站点（data.ncsc.org.cn）直连恒返回 **HTTP 412（WAF）**，仍无摘录条目。
- 2 个坐标（新旧通则 × 2026 发电）核算路径仍被门控拦截（碳氧化率待因子库），核算路径 **38/40**。
  **基准的"规则自洽率 100%"指 40 包结构自洽**（表达式/引用/状态/作用域），与"核算路径 38/40 可通过"
  不矛盾：后者是数据未核对，前者是规则包自身无矛盾；基准同时把"门控能正确拦截未核对条目"纳入检查，不掩盖该留白。
- 单位表"基准单位换算因子必须为 1"由 `UnitTable.__init__` 在加载时强制（更强保证），
  基准层同类检查在正常数据上恒真——保留它作为"表内自洽"的显式记录，而非唯一防线。
- 三行业配额"平衡值"与发电"调峰修正系数"标 **`input_required`**（第三态），非 `pending`。
- 校核阈值是**工程筛查判据**（非官方数值），规则包内 `clause.code = null` 并注明。
- 配额试算覆盖方案覆盖年度（发电 2025/2026、三行业 2026）；其余年度发电基准值标 `input_required`。
- 校核与配额的报告章节（报告 §5/§6）与 XLSX/CSV 机读产物属 M5；M4 只落基准 + 指标。

## 六、关键命令速查

```bash
# 全量测试（204 项）
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照；token 集 13 个）
py -X utf8 tools/check_zero_literals.py --selftest

# 内置基准（三类全跑；退出码 0 达标 / 1 未达标 / 2 用法错误）
py -X utf8 tools/bench.py
py -X utf8 tools/bench.py --suite rules          # 只跑指定套件（可重复）
PYTHONPATH=code/src py -X utf8 -m ghg.cli --json bench   # 机器可读

# 四生成器链式重生成（应位级一致，用守门测试判定而非 git status）
py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_factors.py && \
py -X utf8 tools/gen_knowledge.py && py -X utf8 tools/gen_synthetic.py

# CLI 实测（退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check            # → rc 1（核算路径仍有 2 坐标被拦）
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json   # → rc 0
PYTHONPATH=code/src py -X utf8 -m ghg.cli check --input data/truth/profiles/steel-2024-bad-unit.json  # → rc 2（Q-UNIT-01 error）
PYTHONPATH=code/src py -X utf8 -m ghg.cli quota --input data/truth/profiles/power-2025.json \
  --correction-factor 0.97                                                                   # → rc 0（基准法）
PYTHONPATH=code/src py -X utf8 -m ghg.cli quota --input data/truth/profiles/steel-2024.json  # → rc 2（缺外部输入）
PYTHONPATH=code/src py -X utf8 -m ghg.cli bench                                              # → rc 0（三类达标）
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest                                           # → rc 0
```

## 七、下一棒建议动作顺序

1. 先跑一遍"关键命令速查"，确认基线仍绿（防"接手时已经不绿"）。
2. 读 `plan/02` FR-06/FR-08、`plan/05` §二 M5、`plan/04` §七 接口表（`report` 行标 ⬜ M5）。
3. 落地 `code/src/ghg/report.py`：`render_markdown` / `write_csv` / `write_xlsx`
   （复用 `pipeline.render_report_text` 的报告头/边界/明细/因子表/溯源表，补 §5 校核 / §6 配额章节）；
   加 CLI `calc --report` 的 CSV/XLSX 分支或新 `ghg report` 子命令。
4. 落 `code/gui/`（PySide6）多页签，**只调引擎 API**；offscreen 测试常驻。
5. 落 PyInstaller 规格（onedir 双 exe）+ `exe --selftest` 断言数据目录在 dist 内。
6. 跑测试 → 跑门禁 → 跑基准 → 重生成四产物（守门测试判位级一致）→ 回写 `plan/05` M5 DoD 表 → 落 HANDOFF-M6。

## 八、发布前必办（记在 M6，别忘了）

| 项 | 状态 | 动作 |
|---|---|---|
| **提交元数据邮箱** | ⚠️ 当前为真实个人邮箱（`git log --format="%ae %ce"` 可见） | M6 发布前 `git filter-branch --env-filter` 全历史改写为 GitHub noreply（plan/06 O-6）；改后清 refs/original + reflog + gc，固定字面值 grep 验证 **ae 与 ce 两个字段** |
| **未提交的工作树改动** | ⚠️ M0–M4 的 `code/`、`data/`、`tools/` 改动尚未提交（见 §四 坑 7） | 发布前须形成有序提交（数据产物与代码同批）；提交信息注明里程碑 |
| 远端仓库 | 尚未建立（`git remote -v` 为空） | M6 用 `gh repo create ... --source . --remote origin`（**不带 --push**）→ 切 SSH → push（对外动作，先向用户确认） |
| 脱敏审计脚本 | 尚未固化 | M6 前把脱敏四步做成入仓可复跑脚本 + 守门测试 |
| CI 首跑 | 未跑（无远端） | M6 首次 push 即首跑；按需诊断环境差异型失败（编码/EOL/系统库）。**注意**：CI 现已含 `tools/bench.py` 步骤，首跑要确认三矩阵上基准均达标（阈值 2 秒很宽，但 CI 机器更慢，必要时复核） |
| **官方因子库补摘** | WAF 阻断未摘录（06 O-7） | M6 前复核站点是否可直连（或改用浏览器会话）；能摘则补 `data/factors/` 并重跑相关测试 |