# HANDOFF-M2 —— 续接快照（M0/M1 已完成，下一棒 = M2 核算引擎）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M2.md" 继续完成任务`
> （路径用相对形式 `plan/HANDOFF-M2.md`，启动命令由用户侧拼绝对路径。）
> **本快照状态**：✅ 有效（M1 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 + M1 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06`；05 已回写 M1 DoD，06 已加 D1-1~7 与 O-1~9 |
| 核心包 `code/src/ghg/` | ✅ | errors/decimals/jsonio/paths/coordinates/rules/units/engine/**calc**/cli 十个模块 |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；`tools/gen_rulesets.py`（v0.2.0）；重生成位级一致 |
| **门控分作用域**（M1 口径变更） | ✅ | `RulesIndex.effective_ruleset(coord, scope)`：`calc`/`quota`/`check` 三作用域（06 D1-1） |
| **规则数值逐条挂官方原文核对** | ✅ | 排放源/公式/系数/因子/校核/配额 全 verified 或显式 pending；`data/README.md` §二 |
| **官方因子库台账** | ✅ | `data/factors/manifest.json`；**站点 WAF 阻断（412）如实留空**（06 D1-4 / O-7） |
| **合成企业档案 + 真值库** | ✅ | `data/truth/`（6 档案 + 2 边界用例）；`tools/gen_synthetic.py`（自研确定性 RNG） |
| **真值双路对账** | ✅ | `test_m1_data.py::test_engine_matches_truth_for_every_profile`（引擎 vs 真值库，逐源+汇总） |
| **条款库 + 官方原文快照** | ✅ | `data/knowledge/clauses.json`（11 依据 / 21 快照）+ `raw/` |
| **`calc` 端到端出数（M1 DoD）** | ✅ | 38/40 坐标退出码 0，输出逐源明细 + 总量 |
| 测试套件 | ✅ | `code/tests/` 11 个文件，**121 passed**（1.1 秒） |
| 零政策字面量门禁 | ✅ | token 集 **7 个**（M1 起非空，门禁真正生效）→ 退出码 0 |
| CI workflow | ✅ | 三矩阵 + `fetch-depth: 0`；本地守门测试通过（**GitHub 首跑仍待 M6**） |
| README / data 台账 | ✅ | README 已转 M1 状态；`data/README.md` 已重写（含 §五 未决项） |

**M1 关键数字**：核算路径 **38/40 坐标可通过**；2 个被拦 = `gbt32150-{2015,2025}/2026/power`
（2026 年度发电碳氧化率已改由官方因子库取值，而因子库站点 WAF 阻断未能摘录 → 保持 pending）。
配额路径全 pending（三行业"平衡值"仅平台可查、发电调峰修正系数为函数）；校核路径全 pending（阈值属 M3）。

**未做（M1 刻意不做）**：边界识别引擎（M2）、完整单位链与报告导出（M2/M5）、校核层与配额试算（M3）、基准（M4）、GUI/打包（M5）、发布（M6）。

## 二、M2 待办（核算引擎）

按 `plan/05-数据计划与里程碑.md` §二 M2：

1. **边界识别 + 双标尺差异（FR-01）**：`boundary.identify_boundary(profile, coord)` → `BoundaryReport`；
   `diff_boundary(coord_2015, coord_2025)` → 按 `source.id` 集合做差（added/removed/adjusted）。
   - 数据源已就绪：规则包 `boundary.sources[].required` + `delta_vs_2015`（M1 已核对）。
   - 接口契约见 `plan/04` §二。
2. **完整计算编排 `pipeline.compute_full`（CLI/GUI 共用单点）**：把 `calc.py` 的最小路径升级为
   完整编排（边界识别 → 逐源因子选择 → 单位换算 → 表达式求值 → 汇总 → 溯源结构）。
3. **单位换算显式化（FR-02.3）**：活动数据/因子单位到规则包基本单位的换算链（现 `calc.py` 只处理系数 `%`→1）。
4. **算例回归 100%**：真值库（`data/truth/`）对账 —— 现已有 6 档案 + 2 边界用例，M2 扩充算例并断言回归全绿。
5. **失败路径退出码**：混算（2）/ 缺因子（2）/ 坏格式（2）/ 门控（1）—— 现已有基础，M2 补齐。

**M2 DoD**：见 `plan/05` §二 M2；`ghg calc` 对合成档案输出完整报告头 + 逐源明细 + 溯源表；算例回归全绿。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| P1 | 条目 id 命名（`source.id` 全局稳定，不随年度改名） | `tools/gen_rulesets.py` | 双标尺 diff、真值库、报告溯源表 |
| P2 | `status` 门控语义：`pending` 绝不进**其自身路径**（含 `value: null` 的 verified 条目） | `rules._entry_is_effective` + `SCOPE_BLOCKS` | CLI 退出码、全部基准 |
| P3 | CLI 退出码 0/1/2 语义 | `errors.py` + `plan/03 §六` | CLI 测试、批处理用户 |
| P4 | 冻结产物字节口径：无 CR、无时间戳、键排序固定、`write_bytes` | `jsonio.write` + `gen_*.py` | 冻结守门测试、manifest sha256 |
| P5 | 表达式文法白名单（`mul/add/sub/div/var/const`；const 必须 ref，禁内联数值） | `engine.py` | 引擎求值器、规则包校验 |
| P6 | 零政策字面量门禁：**只扫引擎/前端源码**（`code/src/ghg/**`）；生成器不扫（D0-13）；token 从规则包数值字段采集（M1 起 7 个） | `tools/check_zero_literals.py` + `plan/06 §二` | 门禁测试 |
| P7 | 免责声明文本（法律文本，入代码豁免门禁） | `gen_rulesets.py` `DISCLAIMER` | 报告模板、02 R3 |
| P8 | 坐标空间与短键（`gbt32150-2015/2025`、2022–2026、四行业） | `data/rules/manifest.json`（**单一真相源**）+ `gen_rulesets.py` | 坐标测试、CLI、文档计数 |
| **P9** | **门控按计算路径分作用域**（M1 新增） | `rules.SCOPE_BLOCKS` / `effective_ruleset(scope)` | CLI 退出码判据、M2/M3 各路径放行 |
| **P10** | **行业缺省因子 = 官方缺省值按标准公式合成**（发热量 × 含碳量 × 44/12） | `gen_rulesets._factors_block` + `DEFAULT_FACTOR_INPUTS` | 零字面量 token 集、算例真值 |
| **P11** | **四生成器链式依赖**：rules → factors → knowledge → synthetic（synthetic 读 rules/） | `tools/gen_*.py` | 位级一致测试、M2 算例扩充 |

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`）；脚本一律 `py -X utf8`。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__`，单轮崩溃直接重试。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **Path.write_text(newline=) 是 3.10+**：3.8 上报错，统一用 `write_bytes`（本仓库已如此）。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通（本次实测：`py` 读不到 `/tmp/x`）；临时文件用工作区相对路径或 `tmp_path` 夹具。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。
7. **pdfplumber / pdftotext 可用**：官方 PDF 取数用 `pdftotext -layout -enc UTF-8`（保列对齐）或 `pdfplumber`（`extract_tables`）。

## 五、DoD 逐项 checklist（M1）

- [x] M1-1 通则元数据核对（发布/实施/代替/有效性）→ `standard.*` verified
- [x] M1-2 排放源纳入判定核对（四行业 × 应核算源 + `delta_vs_2015`）
- [x] M1-3 公式/系数/行业缺省因子核对（挂官方条款号）
- [x] M1-4 未核实项显式 pending 并说明（2026 发电 / 配额平衡值 / 校核阈值）
- [x] M1-5 官方因子库台账（来源/版本/访问状态；WAF 阻断如实留空）
- [x] M1-6 合成档案 + 真值库（6 档案 + 2 边界用例）
- [x] M1-7 真值双路对账（引擎 vs 真值库）
- [x] M1-8 生成器可复跑位级一致（四生成器链式，53 份 JSON）
- [x] M1-9 **`calc` 至少一个坐标端到端出数**（实测 38/40 → 退出码 0）
- [x] M1-10 条款库入库（11 依据 / 21 快照 + sha256）

**偏差说明（如实留档）**：
- 官方因子库站点（data.ncsc.org.cn）直连恒返回 **HTTP 412（WAF）**，M1 **未逐条摘录因子数值**；
  按纪律不编造，台账留空并登记访问状态；缺省因子改由四行业指南附录 A 官方缺省值承担。
- 因 2026 年度发电碳氧化率改由因子库取值，该 **2 个坐标**核算路径被门控拦截（诚实留白，非缺陷）。
- 门控由 M0 的"整包单点"升级为"**按计算路径分作用域**"（06 D1-1），属会打挂测试的口径变更，
  已在决策记录登记并改写 `test_rules_gate.py` / `test_cli.py` 相关断言。
- GB/T 32150-2025 全文经 openstd 在线预览（防复制精灵图）逐页核对，但**未获取可下载 PDF 与编制说明**（06 O-9）。

## 六、关键命令速查

```bash
# 全量测试
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照；M1 起 token 集 7 个）
py -X utf8 tools/check_zero_literals.py --selftest

# 四生成器链式重生成（应位级一致，git status 无变化才正常）
py -X utf8 tools/gen_rulesets.py && py -X utf8 tools/gen_factors.py && \
py -X utf8 tools/gen_knowledge.py && py -X utf8 tools/gen_synthetic.py

# CLI 实测（退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check          # → rc 1（仍有坐标被拦）
PYTHONPATH=code/src py -X utf8 -m ghg.cli calc --input data/truth/profiles/steel-2024.json  # → rc 0 出数
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest             # → rc 0
```

## 七、下一棒建议动作顺序

1. 先跑一遍"关键命令速查"，确认基线仍绿（防"接手时已经不绿"）。
2. 读 `plan/04` §二/§三（边界识别与计算引擎接口契约）与 `plan/02` FR-01/FR-02。
3. 落地 `code/src/ghg/boundary.py`（`identify_boundary` / `diff_boundary`）——数据源已就绪
   （规则包 `boundary.sources[].required` + `delta_vs_2015` 已核对）。
4. 把 `calc.py` 的最小路径升级为 `pipeline.compute_full`（边界识别 → 因子选择 → 单位换算 → 求值 → 汇总 → 溯源）。
5. 扩充 `data/truth/` 算例（可加多源/多燃料/双标尺对比档案），断言算例回归 100%。
6. 跑测试 → 跑门禁 → 重生成四产物（位级一致）→ 回写 `plan/05` M2 DoD 表。

## 八、发布前必办（记在 M6，别忘了）

| 项 | 状态 | 动作 |
|---|---|---|
| **提交元数据邮箱** | ⚠️ 当前为真实个人邮箱（`git log --format="%ae %ce"` 可见） | M6 发布前 `git filter-branch --env-filter` 全历史改写为 GitHub noreply（plan/06 O-6）；改后清 refs/original + reflog + gc，固定字面值 grep 验证 **ae 与 ce 两个字段** |
| 远端仓库 | 尚未建立（`git remote -v` 为空） | M6 用 `gh repo create ... --source . --remote origin`（**不带 --push**）→ 切 SSH → push（对外动作，先向用户确认） |
| 脱敏审计脚本 | 尚未固化 | M6 前把脱敏四步做成入仓可复跑脚本 + 守门测试 |
| CI 首跑 | 未跑（无远端） | M6 首次 push 即首跑；按需诊断环境差异型失败（编码/EOL/系统库） |
| **官方因子库补摘** | WAF 阻断未摘录（06 O-7） | M6 前复核站点是否可直连（或改用浏览器会话）；能摘则补 `data/factors/` 并重跑相关测试 |