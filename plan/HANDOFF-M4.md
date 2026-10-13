# HANDOFF-M4 —— 续接快照（M0/M1/M2/M3 已完成，下一棒 = M4 内置基准）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M4.md" 继续完成任务`
> （路径用相对形式 `plan/HANDOFF-M4.md`，启动命令由用户侧拼绝对路径。）
> **本快照状态**：✅ 有效（M3 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 + M1 + M2 + M3 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06`；05 已回写 M1/M2/**M3** DoD，06 已加 D1-1~7 / D2-1~7 / **D3-1~5** |
| 核心包 `code/src/ghg/` | ✅ | errors/decimals/jsonio/paths/coordinates/rules/units/engine/calc/boundary/pipeline/**quality**/**quota**/cli **十四个模块** |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；`tools/gen_rulesets.py`（v0.2.0）；重生成位级一致 |
| 门控分作用域 + **第三态 `input_required`** | ✅ | `RulesIndex.effective_ruleset(coord, scope)`：`calc`/`quota`/`check`；`_entry_is_effective` 放行 `input_required`（06 D1-1 / **D3-2**） |
| 规则数值逐条挂官方原文核对 | ✅ | 全 verified 或显式 pending/input_required；`data/README.md` §二 |
| 官方因子库台账 | ✅ | `data/factors/manifest.json`；**站点 WAF 阻断（412）如实留空**（06 D1-4 / O-7） |
| 边界识别 + 双标尺差异（M2） | ✅ | `code/src/ghg/boundary.py` |
| 显式单位换算链（M2） | ✅ | `calc.UnitChain`；**复合单位分隔符单一真相源已移到 `units.PER_SEPARATOR`**（06 D3-3） |
| 因子按类别分派 + 优先级（M2） | ✅ | `calc._select_factor` |
| 完整编排单点（M2） | ✅ | `code/src/ghg/pipeline.py` |
| 溯源完整性硬约束（M2） | ✅ | `pipeline._assert_provenance_complete` |
| **四类数据质量校核（M3）** | ✅ | `code/src/ghg/quality.py`：`run_checks` 按 `quality.rules[].type` 分派（06 D3-1/D3-4） |
| **校核只读 + 阈值取自规则包（M3）** | ✅ | `test_run_checks_does_not_mutate_inputs` / `test_thresholds_come_from_ruleset` |
| **配额试算方法学分支（M3）** | ✅ | `code/src/ghg/quota.py`：`compute_quota`（benchmark / intensity_coefficient / historical_intensity / none） |
| **配额外部输入显式索取（M3）** | ✅ | `input_required` 三态 + `QuotaUnavailable`（退出码 2，不得静默取 0）（06 D3-2） |
| **免责声明强制（M3）** | ✅ | `QuotaResult.disclaimer_required` 恒 True；`render_quota_text` 必含声明行（R3/NFR-10） |
| 合成企业档案 + 真值库 | ✅ | `data/truth/`（**8 核算档案 + 12 用例**）；`tools/gen_synthetic.py` |
| 真值双路对账（核算 + 校核 + 配额） | ✅ | `test_m2_engine.py` / `test_m3_quality_quota.py`（逐源 + 汇总 + 配额逐字段） |
| 条款库 + 官方原文快照 | ✅ | `data/knowledge/clauses.json`（11 依据 / 21 快照）+ `raw/` |
| `calc` 完整报告端到端（M2 DoD） | ✅ | 核算路径 38/40 坐标退出码 0 |
| **`check` 四类校核端到端（M3 DoD）** | ✅ | 校核路径 40/40；error→退出码 2，仅 warning/info→0 |
| **`quota` 试算端到端（M3 DoD）** | ✅ | 配额路径 40/40；外部输入缺失→退出码 2 |
| 测试套件 | ✅ | `code/tests/` **13 个文件，179 passed**（1.3 秒） |
| 零政策字面量门禁 | ✅ | token 集 **13 个** → 退出码 0 |
| CI workflow | ✅ | 三矩阵 + `fetch-depth: 0`；本地守门测试通过（**GitHub 首跑仍待 M6**） |
| README / data 台账 | ✅ | README 已转 M3 状态；`data/README.md` 已更新（§一 数据态 / §三 算例 / §五 未决项） |

**M3 关键数字**：核算路径 **38/40**、**配额路径 40/40**、**校核路径 40/40** 坐标可通过；
**8 核算算例 + 4 校核异常 + 2 配额算例与真值库 100% 对账**；
零字面量 token 集 7 → **13**（新增 `0.15`/`0.20`/`0.5`/`0.50`/`0.95`/`5.0`）；
四条校核异常各自命中且分级正确（unit=error / magnitude=warning / yoy=warning / intensity=info），
外加一条**误报对照**（同比未变化的档案不命中跨年突变）。

**未做（M3 刻意不做）**：内置基准（M4）、GUI/打包/XLSX·CSV 报告导出（M5）、发布（M6）。
校核与配额的报告章节（报告 §5/§6）并入 M5 的报告导出。

## 二、M4 待办（内置基准）

按 `plan/05-数据计划与里程碑.md` §二 M4 与 `plan/02` FR-07：

1. **规则自洽基准（FR-07.1）**：新旧通则 × 四行业 × 多年度规则包（40 份）的公式与系数枚举自洽扫描
   （表达式文法合法、引用完整、`delta_vs_2015` 与结构交叉一致、门控作用域一致）；
2. **因子一致性基准（FR-07.2）**：同源因子跨年变化扫描 + 单位换算往返一致率（`units.json` 全量往返）；
3. **边界与异常用例基准（FR-07.3）**：边界识别 / 跨版本混算拦截 / **数据质量校核命中率与误报率**（M3 算例已就绪）；
4. **一条命令跑全**（`ghg bench` 或 `tools/bench.py`）：退出码 0 达标 / 1 未达标 / 2 用法错误；
   指标（命中率 / 误报率 / 自洽率 / 运行时长）写进 README 基准表（当前 README 表为 ⬜ M4 占位）；
5. 单次全量运行时长符合 NFR-11（40 坐标全量扫描 < 2 秒）。

**M4 DoD**：见 `plan/05` §二 M4；三类基准全绿、指标门槛达成并进 README 表。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| P1 | 条目 id 命名（`source.id` 全局稳定，不随年度改名） | `tools/gen_rulesets.py` | 双标尺 diff、真值库、报告溯源表 |
| P2 | `status` 门控语义：`pending` 绝不进**其自身路径**（含 `value: null` 的 verified 条目）；**`input_required` 放行** | `rules._entry_is_effective` + `SCOPE_BLOCKS` | CLI 退出码、全部基准 |
| P3 | CLI 退出码 0/1/2 语义（**新增**：校核含 error→2；配额外部输入缺失→2） | `errors.py` + `plan/03 §六` | CLI 测试、批处理用户 |
| P4 | 冻结产物字节口径：无 CR、无时间戳、键排序固定、`write_bytes` | `jsonio.write` + `gen_*.py` | 冻结守门测试、manifest sha256 |
| P5 | 表达式文法白名单（`mul/add/sub/div/var/const`；const 必须 ref） | `engine.py` | 引擎求值器、规则包校验 |
| P6 | 零政策字面量门禁：**只扫引擎/前端源码**（`code/src/ghg/**`）；token 从规则包数值字段采集（**现 13 个**） | `tools/check_zero_literals.py` + `plan/06 §二` | 门禁测试 |
| P7 | 免责声明文本（法律文本，入代码豁免门禁） | `gen_rulesets.py` `DISCLAIMER` | 报告模板、02 R3、`quota` 渲染 |
| P8 | 坐标空间与短键（`gbt32150-2015/2025`、2022–2026、四行业） | `data/rules/manifest.json`（单一真相源） | 坐标测试、CLI、文档计数 |
| P9 | 门控按计算路径分作用域 | `rules.SCOPE_BLOCKS` / `effective_ruleset(scope)` | CLI 退出码判据 |
| P10 | 行业缺省因子 = 官方缺省值按标准公式合成 | `gen_rulesets._factors_block` | 零字面量 token 集、算例真值 |
| P11 | 四生成器链式依赖：rules → factors → knowledge → synthetic | `tools/gen_*.py` | 位级一致测试 |
| P12 | 双标尺差异以 `delta_vs_2015` 声明为准 + 结构交叉校验 | `boundary.diff_boundary` | 差异输出、plan/04 §二 |
| P13 | 单位换算链三段式 | `calc.UnitChain` | 明细行字段 |
| P14 | 档案自报因子来源须落在 `factors.priority` 白名单内 | `calc._select_factor` | 因子选择、退出码 2 |
| P15 | 溯源表行数 == 明细 + 因子，`rule_entry_id` 必须可解析 | `pipeline._assert_provenance_complete` | 报告导出、溯源断言 |
| P16 | CLI `calc` 走 `pipeline.compute_full` 编排单点 | `cli.cmd_calc` | CLI 输出结构 |
| **P17** | **校核阈值属工程判据（非政策数值）**：`quality.thresholds` 四项 `verified`，`clause.code=null` | `gen_rulesets.QUALITY_THRESHOLDS`（06 D3-1） | 校核路径门控、零字面量 token 集 |
| **P18** | **配额参数三态**：`verified`（规则包值）/ `input_required`（外部输入，运行时索取）/ `pending`（门控拦截） | `gen_rulesets._quota_block`（06 D3-2） | 配额路径门控、`QuotaUnavailable` |
| **P19** | **校核分级可降级**：规则的 level 是硬违规级别；可换算/可解释时降一级 | `quality._check_unit_consistency`（06 D3-4） | `check` 退出码判据 |
| **P20** | **配额结果双口径**：量化呈现字段 + `*_raw` 全精度对账字段 | `quota.compute_quota`（06 D3-5） | 配额测试对账 |
| **P21** | **复合单位分隔符单一真相源**：`units.PER_SEPARATOR` / `units.split_compound_unit` | `units.py`（06 D3-3） | 校核单位一致性 + calc 因子换算 |

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`）；脚本一律 `py -X utf8`。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`，单轮崩溃直接重试。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **Path.write_text(newline=) 是 3.10+**：3.8 上报错，统一用 `write_bytes`。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通；临时文件用工作区相对路径或 `tmp_path` 夹具。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。
7. **`git status` 的 M 状态含 M0–M3 未提交改动**：本仓库 `code/`、`data/` 改动**尚未提交**。
   判据是 `test_synthetic_regeneration_is_bitwise_identical`（临时目录重生成 + sha256 逐份比对），
   不是 `git status`。
8. **配额 CLI 的数值参数一律按字符串解析**（`as_decimal`），避免 float 进计算路径。
9. **`py -X utf8 -m ghg.cli` 需 `PYTHONPATH=code/src`**（或先 `pip install -e code`）。
10. **官方 PDF/HTML 快照为 UTF-8**：`data/knowledge/raw/*.txt` 直接 `open(...,'rb').read().decode('utf-8')`
    （勿用 gbk，会崩）；pdfplumber/pdftotext 可用。

## 五、DoD 逐项 checklist（M3）

- [x] M3-1 四类校核检查按 `quality.rules[].type` 分派（`quality.run_checks`）
- [x] M3-2 分级问题清单（error/warning/info）+ 每条挂规则依据 id / 条款 / 建议
- [x] M3-3 校核层只读（`test_run_checks_does_not_mutate_inputs`）
- [x] M3-4 阈值全部取自规则包（`test_thresholds_come_from_ruleset`）
- [x] M3-5 `pending` 规则不执行并说明原因（`rules_skipped`）
- [x] M3-6 单位错配命中且级别 error
- [x] M3-7 量级异常 / 跨年突变 / 比强度越界各自命中且分级正确
- [x] M3-8 误报对照：同比未变化档案不命中跨年突变
- [x] M3-9 配额方法学切换即切换公式分支（四分支）
- [x] M3-10 配额真值对账（基准法 / 强度系数法）
- [x] M3-11 外部输入缺失 → `QuotaUnavailable`（退出码 2）
- [x] M3-12 免责声明强制（结构体 + 渲染层）
- [x] M3-13 校核/配额路径 40/40；分作用域仍生效
- [x] M3-14 四生成器链式重跑位级一致（含新增产量与 6 份 M3 算例档案）

**偏差说明（如实留档）**：
- 官方因子库（第二版）站点（data.ncsc.org.cn）直连恒返回 **HTTP 412（WAF）**，仍无摘录条目。
- 2 个坐标（新旧通则 × 2026 发电）核算路径仍被门控拦截（碳氧化率待因子库），核算路径 **38/40**。
- 三行业配额"平衡值"与发电"调峰修正系数"标 **`input_required`**（新增第三态），非 `pending`：
  它们是"本不由规则包承载的外部输入"，不是"待核对的政策数值"；试算层运行时显式索取，缺失即退出码 2。
- 校核阈值是**工程筛查判据**（非官方数值），规则包内 `clause.code = null` 并注明，避免与政策数值混淆。
- 配额试算覆盖方案覆盖年度（发电 2025/2026、三行业 2026）；其余年度发电基准值标 `input_required`。
- 校核与配额的报告章节（报告 §5/§6）与 XLSX/CSV 机读产物属 M5；本里程碑落地引擎 API + CLI 子命令。

## 六、关键命令速查

```bash
# 全量测试（179 项）
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照；token 集 13 个）
py -X utf8 tools/check_zero_literals.py --selftest

# 四生成器链式重生成（应位级一致，用守门测试判定而非 git status）
py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_factors.py && \
py -X utf8 tools/gen_knowledge.py && py -X utf8 tools/gen_synthetic.py

# CLI 实测（退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check            # → rc 1（核算路径仍有 2 坐标被拦）
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json   # → rc 0
PYTHONPATH=code/src py -X utf8 -m ghg.cli check --input data/truth/profiles/steel-2024.json  # → rc 0（无 error）
PYTHONPATH=code/src py -X utf8 -m ghg.cli check --input data/truth/profiles/steel-2024-bad-unit.json  # → rc 2（Q-UNIT-01 error）
PYTHONPATH=code/src py -X utf8 -m ghg.cli check --input data/truth/profiles/steel-2024-yoy-jump.json \
  --baseline data/truth/profiles/steel-2023-yoy-baseline.json                                # → rc 0（Q-YOY-01 warning）
PYTHONPATH=code/src py -X utf8 -m ghg.cli quota --input data/truth/profiles/power-2025.json \
  --correction-factor 0.97                                                                   # → rc 0（基准法）
PYTHONPATH=code/src py -X utf8 -m ghg.cli quota --input data/truth/profiles/steel-2024.json \
  --benchmark-value 2.1                                                                      # → rc 0（强度系数法）
PYTHONPATH=code/src py -X utf8 -m ghg.cli quota --input data/truth/profiles/steel-2024.json  # → rc 2（缺外部输入）
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest                                            # → rc 0
```

## 七、下一棒建议动作顺序

1. 先跑一遍"关键命令速查"，确认基线仍绿（防"接手时已经不绿"）。
2. 读 `plan/02` FR-07 与 `plan/05` §二 M4、`plan/04` §七 接口表。
3. 落地 `tools/bench.py`（或 `code/src/ghg/bench.py` + CLI `bench` 子命令）：
   - 规则自洽扫描（遍历 40 包，校验表达式/引用/delta 交叉一致）；
   - 因子一致性 + 单位往返（`units.json` 全量）；
   - 边界与异常用例（复用 `data/truth/expected.json` 的 cases，含 M3 校核算例）；
4. 指标（自洽率 / 命中率 / 误报率 / 运行时长）写进 README §五 基准表（现为 ⬜ 占位）；
5. 跑测试 → 跑门禁 → 重生成四产物（守门测试判位级一致）→ 回写 `plan/05` M4 DoD 表 → 落 HANDOFF-M5。

## 八、发布前必办（记在 M6，别忘了）

| 项 | 状态 | 动作 |
|---|---|---|
| **提交元数据邮箱** | ⚠️ 当前为真实个人邮箱（`git log --format="%ae %ce"` 可见） | M6 发布前 `git filter-branch --env-filter` 全历史改写为 GitHub noreply（plan/06 O-6）；改后清 refs/original + reflog + gc，固定字面值 grep 验证 **ae 与 ce 两个字段** |
| **未提交的工作树改动** | ⚠️ M0–M3 的 `code/` 与 `data/` 改动尚未提交（见 §四 坑 7） | 发布前须形成有序提交（数据产物与代码同批）；提交信息注明里程碑 |
| 远端仓库 | 尚未建立（`git remote -v` 为空） | M6 用 `gh repo create ... --source . --remote origin`（**不带 --push**）→ 切 SSH → push（对外动作，先向用户确认） |
| 脱敏审计脚本 | 尚未固化 | M6 前把脱敏四步做成入仓可复跑脚本 + 守门测试 |
| CI 首跑 | 未跑（无远端） | M6 首次 push 即首跑；按需诊断环境差异型失败（编码/EOL/系统库） |
| **官方因子库补摘** | WAF 阻断未摘录（06 O-7） | M6 前复核站点是否可直连（或改用浏览器会话）；能摘则补 `data/factors/` 并重跑相关测试 |