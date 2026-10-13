# HANDOFF-M3 —— 续接快照（M0/M1/M2 已完成，下一棒 = M3 校核层与配额试算）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M3.md" 继续完成任务`
> （路径用相对形式 `plan/HANDOFF-M3.md`，启动命令由用户侧拼绝对路径。）
> **本快照状态**：✅ 有效（M2 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 + M1 + M2 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06`；05 已回写 M1/M2 DoD，06 已加 D1-1~7 与 **D2-1~7** |
| 核心包 `code/src/ghg/` | ✅ | errors/decimals/jsonio/paths/coordinates/rules/units/engine/calc/**boundary**/**pipeline**/cli 十二个模块 |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；`tools/gen_rulesets.py`（v0.2.0）；重生成位级一致 |
| 门控分作用域 | ✅ | `RulesIndex.effective_ruleset(coord, scope)`：`calc`/`quota`/`check`（06 D1-1） |
| 规则数值逐条挂官方原文核对 | ✅ | 全 verified 或显式 pending；`data/README.md` §二 |
| 官方因子库台账 | ✅ | `data/factors/manifest.json`；**站点 WAF 阻断（412）如实留空**（06 D1-4 / O-7） |
| **边界识别 + 双标尺差异（M2）** | ✅ | `code/src/ghg/boundary.py`；`identify_boundary` / `diff_boundary`（06 D2-1） |
| **显式单位换算链（M2）** | ✅ | `calc.UnitChain`（活动→基本单位、因子→每基本单位、排放→tCO2e，链式留痕）（06 D2-2） |
| **因子按类别分派 + 优先级（M2）** | ✅ | `calc._select_factor`：实测 > 官方库 > 行业缺省；三层皆无 → 退出码 2（06 D2-3/D2-4） |
| **完整编排单点（M2）** | ✅ | `code/src/ghg/pipeline.py`：`compute_full` / `render_report_text`（06 D2-6） |
| **溯源完整性硬约束（M2）** | ✅ | `pipeline._assert_provenance_complete` + `resolve_rule_entry`（悬空即退出码 2）（06 D2-5） |
| 合成企业档案 + 真值库 | ✅ | `data/truth/`（**8 档案 + 4 边界用例**）；`tools/gen_synthetic.py` |
| 真值双路对账 | ✅ | `test_m2_engine.py::test_pipeline_matches_truth_for_every_profile`（逐源+汇总，含单位换算/因子优先级算例） |
| 条款库 + 官方原文快照 | ✅ | `data/knowledge/clauses.json`（11 依据 / 21 快照）+ `raw/` |
| **`calc` 完整报告端到端（M2 DoD）** | ✅ | `ghg calc` 输出报告头/边界/明细/因子表/溯源表；`--report` 落 Markdown；核算路径 38/40 坐标退出码 0 |
| 测试套件 | ✅ | `code/tests/` 12 个文件，**145 passed**（1.3 秒） |
| 零政策字面量门禁 | ✅ | token 集 **7 个** → 退出码 0 |
| CI workflow | ✅ | 三矩阵 + `fetch-depth: 0`；本地守门测试通过（**GitHub 首跑仍待 M6**） |
| README / data 台账 | ✅ | README 已转 M2 状态；`data/README.md` 已更新（§三 算例扩充 / §五 未决项） |

**M2 关键数字**：核算路径 **38/40 坐标可通过**（与 M1 相同；2 个被拦 = `gbt32150-{2015,2025}/2026/power`）；
**8 份合成算例 + 真值库 100% 对账**（逐源 + 汇总）；四条失败路径退出码锁定（混算 2 / 缺因子 2 / 坏格式 2 / 门控 1）；
双标尺差异四行业 2024 实测：`adjusted` 3~4 项、`unchanged` 1 项（`process_emission`）。
配额路径全 pending；校核路径全 pending（阈值属 M3）。

**未做（M2 刻意不做）**：校核层与配额试算（M3）、基准（M4）、GUI/打包/XLSX·CSV 报告导出（M5）、发布（M6）。

## 二、M3 待办（校核层与配额试算）

按 `plan/05-数据计划与里程碑.md` §二 M3：

1. **四类数据质量检查（FR-04）**：`quality.run_checks(profile, calc, coord)` → `QualityReport`；
   按 `quality.rules[].type` 分派：`unit_consistency` / `magnitude_outlier` / `yoy_jump` / `intensity_plausibility`。
   - 阈值**全部在规则包 `quality.thresholds`**（现全 `pending`，M3 定值后转 `verified`）；
   - 校核层**只读**：不得修改 `CalcResult` 任何字段（FR-04.4，测试断言输入对象未被变更）；
   - `pending` 的校核规则**不执行**；`check` 在 `quality` 全 pending 时返回退出码 1 并说明原因。
2. **分级问题清单（FR-04.3）**：`level ∈ error/warning/info`，每条挂规则依据 id；
   CLI `check` 输出问题清单 + 计数。
3. **配额试算（FR-05）**：`quota.compute_quota(...)` → `QuotaResult`；
   - 方法学切换即切换公式分支（`benchmark` / `intensity_coefficient` / `historical_intensity` / `none`）；
   - 三行业"平衡值"（`benchmark_value`）仅平台可查 → 保持 pending，试算层须显式处理（不得静默取 0）；
   - **免责声明强制**（R3）：渲染层必须输出固定声明文本常量（`report.disclaimer`）。
4. **接口契约**见 `plan/04` §四（校核）与 §五（配额）。

**M3 DoD**：见 `plan/05` §二 M3；故意错配因子/单位/量级异常档案 → 校核命中且分级正确；
方法学切换 → 公式分支切换；校核命中率/误报率进基准（M4 收口）。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| P1 | 条目 id 命名（`source.id` 全局稳定，不随年度改名） | `tools/gen_rulesets.py` | 双标尺 diff、真值库、报告溯源表 |
| P2 | `status` 门控语义：`pending` 绝不进**其自身路径**（含 `value: null` 的 verified 条目） | `rules._entry_is_effective` + `SCOPE_BLOCKS` | CLI 退出码、全部基准 |
| P3 | CLI 退出码 0/1/2 语义 | `errors.py` + `plan/03 §六` | CLI 测试、批处理用户 |
| P4 | 冻结产物字节口径：无 CR、无时间戳、键排序固定、`write_bytes` | `jsonio.write` + `gen_*.py` | 冻结守门测试、manifest sha256 |
| P5 | 表达式文法白名单（`mul/add/sub/div/var/const`；const 必须 ref，禁内联数值） | `engine.py` | 引擎求值器、规则包校验 |
| P6 | 零政策字面量门禁：**只扫引擎/前端源码**（`code/src/ghg/**`）；生成器不扫（D0-13）；token 从规则包数值字段采集（7 个） | `tools/check_zero_literals.py` + `plan/06 §二` | 门禁测试 |
| P7 | 免责声明文本（法律文本，入代码豁免门禁） | `gen_rulesets.py` `DISCLAIMER` | 报告模板、02 R3 |
| P8 | 坐标空间与短键（`gbt32150-2015/2025`、2022–2026、四行业） | `data/rules/manifest.json`（**单一真相源**） | 坐标测试、CLI、文档计数 |
| P9 | 门控按计算路径分作用域 | `rules.SCOPE_BLOCKS` / `effective_ruleset(scope)` | CLI 退出码判据、各路径放行 |
| P10 | 行业缺省因子 = 官方缺省值按标准公式合成（发热量 × 含碳量 × 44/12） | `gen_rulesets._factors_block` + `DEFAULT_FACTOR_INPUTS` | 零字面量 token 集、算例真值 |
| P11 | 四生成器链式依赖：rules → factors → knowledge → synthetic | `tools/gen_*.py` | 位级一致测试、算例扩充 |
| **P12** | **双标尺差异以 `delta_vs_2015` 声明为准 + 结构交叉校验**（声明 `same` 却有结构变化 → 抛错） | `boundary.diff_boundary`（06 D2-1） | 差异输出、plan/04 §二 契约 |
| **P13** | **单位换算链三段式**（活动→基本单位、因子→每基本单位、排放→tCO2e），每步入 `unit_chain` | `calc.UnitChain`（06 D2-2） | 明细行字段、`UnitTable.scale/base_of` |
| **P14** | **档案自报因子来源须落在 `factors.priority` 白名单内**；自报缺省须与规则包缺省值逐位相等 | `calc._select_factor`（06 D2-4） | 因子选择、退出码 2 |
| **P15** | **溯源表行数 == 明细 + 因子，且 `rule_entry_id` 必须可解析**（悬空即退出码 2） | `pipeline._assert_provenance_complete`（06 D2-5） | 报告导出、溯源断言 |
| **P16** | **CLI `calc` 走 `pipeline.compute_full` 编排单点**（`calc.run_calc` 仅薄封装） | `cli.cmd_calc`（06 D2-6） | CLI 输出结构、`test_cli.py` 断言 |

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`）；脚本一律 `py -X utf8`。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`，单轮崩溃直接重试。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **Path.write_text(newline=) 是 3.10+**：3.8 上报错，统一用 `write_bytes`（本仓库已如此）。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通；临时文件用工作区相对路径或 `tmp_path` 夹具。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。
7. **`git status` 的 M 状态含 M1 未提交改动**：本仓库 M0/M1/M2 的 `code/`、`data/` 改动**尚未提交**
   （`code/src/ghg/calc.py`、`boundary.py`、`pipeline.py`、`data/truth/`、`data/factors/`、`data/knowledge/`
   在工作树中显示为 `M`/`??`）。改产物后勿把"git status 有变化"误判为字节漂移 ——
   判据是 `test_synthetic_regeneration_is_bitwise_identical`（临时目录重生成 + sha256 逐份比对）。
8. **pdfplumber / pdftotext 可用**：官方 PDF 取数用 `pdftotext -layout -enc UTF-8` 或 `pdfplumber`。

## 五、DoD 逐项 checklist（M2）

- [x] M2-1 边界识别 `identify_boundary`（纳入判定 + 条款依据 + 缺失输入）
- [x] M2-2 双标尺差异 `diff_boundary`（added/removed/adjusted，`delta_vs_2015` + 结构交叉校验）
- [x] M2-3 完整编排 `pipeline.compute_full`（报告头 + 边界 + 明细 + 因子表 + 溯源表）
- [x] M2-4 单位换算显式化（FR-02.3，`UnitChain` + kg→t 算例）
- [x] M2-5 因子按类别分派 + 优先级（三层皆无 → 退出码 2）
- [x] M2-6 算例回归 100%（8 档案逐源 + 汇总对账）
- [x] M2-7 溯源表完整性硬约束（行数对账 + `rule_entry_id` 可解析）
- [x] M2-8 失败路径退出码：混算(2) / 缺因子(2) / 坏格式(2) / 门控(1)
- [x] M2-9 `ghg calc` 完整报告 + `--report` + `--diff-standard`
- [x] M2-10 四生成器链式重跑位级一致

**偏差说明（如实留档）**：
- 官方因子库（第二版）站点（data.ncsc.org.cn）直连恒返回 **HTTP 412（WAF）**，仍无摘录条目；
  故 `official_db` 层在引擎侧仅由档案显式因子承担，算例以**合成占位值**覆盖该层（机制验证，非真实数值）。
- 2 个坐标（新旧通则 × 2026 发电）核算路径仍被门控拦截，与 M1 一致（诚实留白，非缺陷）。
- 报告导出的 XLSX/CSV 机读产物属 M5；本里程碑只落 Markdown 报告文本。
- 双标尺差异的 `adjusted` 判定依赖规则包内 `delta_vs_2015` 声明（该字段 M1 已逐条核对）；
  若将来新增排放源条目须同步维护该字段，否则 `diff_boundary` 会因"声明与结构不一致"抛错（这是**刻意的护栏**）。

## 六、关键命令速查

```bash
# 全量测试
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照；token 集 7 个）
py -X utf8 tools/check_zero_literals.py --selftest

# 四生成器链式重生成（应位级一致，用守门测试判定而非 git status）
py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_factors.py && \
py -X utf8 tools/gen_knowledge.py && py -X utf8 tools/gen_synthetic.py

# CLI 实测（退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check          # → rc 1（仍有坐标被拦）
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json  # → rc 0 完整报告
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json \
  --diff-standard gbt32150-2015 --report report.md            # → rc 0，含双标尺差异 + 落盘
PYTHONPATH=code/src py -X utf8 -m ghg.cli check --input data/truth/profiles/steel-2024.json  # → rc 1（校核层 M3）
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest             # → rc 0
```

## 七、下一棒建议动作顺序

1. 先跑一遍"关键命令速查"，确认基线仍绿（防"接手时已经不绿"）。
2. 读 `plan/04` §四（校核规则 schema + 四类检查 + 与门控关系）与 §五（配额方法学）与 `plan/02` FR-04/FR-05。
3. 落地 `code/src/ghg/quality.py`（`run_checks`）—— 规则 schema 与阈值位已在规则包就绪
   （`quality.rules[].type/level` + `quality.thresholds`，阈值当前 pending 待 M3 定值）。
4. 落地 `code/src/ghg/quota.py`（`compute_quota`）—— `quota.allowed_methods` + `params` 已就绪
   （注意三行业 `benchmark_value` 仍 pending，须显式处理而非静默取 0）。
5. 扩充 `data/truth/` 异常算例（错配单位 / 量级异常 / 跨年突变 / 比强度越界），断言校核命中与分级。
6. 跑测试 → 跑门禁 → 重生成四产物（守门测试判位级一致）→ 回写 `plan/05` M3 DoD 表 → 落 HANDOFF-M4。

## 八、发布前必办（记在 M6，别忘了）

| 项 | 状态 | 动作 |
|---|---|---|
| **提交元数据邮箱** | ⚠️ 当前为真实个人邮箱（`git log --format="%ae %ce"` 可见） | M6 发布前 `git filter-branch --env-filter` 全历史改写为 GitHub noreply（plan/06 O-6）；改后清 refs/original + reflog + gc，固定字面值 grep 验证 **ae 与 ce 两个字段** |
| **未提交的工作树改动** | ⚠️ M0/M1/M2 的 `code/` 与 `data/` 改动尚未提交（见 §四 坑 7） | 发布前须形成有序提交（数据产物与代码同批）；提交信息注明里程碑 |
| 远端仓库 | 尚未建立（`git remote -v` 为空） | M6 用 `gh repo create ... --source . --remote origin`（**不带 --push**）→ 切 SSH → push（对外动作，先向用户确认） |
| 脱敏审计脚本 | 尚未固化 | M6 前把脱敏四步做成入仓可复跑脚本 + 守门测试 |
| CI 首跑 | 未跑（无远端） | M6 首次 push 即首跑；按需诊断环境差异型失败（编码/EOL/系统库） |
| **官方因子库补摘** | WAF 阻断未摘录（06 O-7） | M6 前复核站点是否可直连（或改用浏览器会话）；能摘则补 `data/factors/` 并重跑相关测试 |