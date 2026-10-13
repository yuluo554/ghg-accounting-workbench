# HANDOFF-M1 —— 续接快照（M0 已完成，下一棒 = M1 数据先行）

> **用法（新对话）**：`/goal 读取 "<项目绝对路径>/plan/HANDOFF-M1.md" 继续完成任务`
> （路径用相对形式 `plan/HANDOFF-M1.md`，启动命令由用户侧拼绝对路径。）
> **本快照状态**：✅ 有效（M0 于 2026-10-13 完成，本节内容即当前真实状态）。

---

## 一、当前进度（M0 已完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 计划文档 00–06 定稿 | ✅ | `plan/00`–`plan/06` 六份；00 的文档索引与里程碑表已回写 ✅ |
| 核心包 `code/src/ghg/` | ✅ | `errors/decimals/jsonio/paths/coordinates/rules/units/engine/cli` 九个模块 |
| 三维规则包 40 份 + manifest + units | ✅ | `data/rules/`；生成器 `tools/gen_rulesets.py`；重生成位级一致（42 份 sha256 不变） |
| 坐标门控（M0 核心行为） | ✅ | `RulesIndex.effective_ruleset()` 拦截；CLI `calc` → 退出码 **1** |
| 跨坐标混算拦截（M0 核心行为） | ✅ | `detect_mixed_coordinates()`；CLI `calc` 混算 → 退出码 **2** |
| 零政策字面量门禁 | ✅ | `tools/check_zero_literals.py`（含阳性对照 selftest）→ 退出码 0 |
| 测试套件 | ✅ | `code/tests/` 8 个文件，**99 passed**（0.5 秒） |
| CI workflow | ✅ | `.github/workflows/ci.yml`，三矩阵 + `fetch-depth: 0`；本地 YAML/结构守门测试通过（**尚未在 GitHub 首跑**） |
| README / data 台账 | ✅ | README 已重写为发布向；`data/README.md` 已补 M0 初态说明 |

**未做（M0 刻意不做）**：真实政策数值入库（M1）、边界识别（M2）、校核/配额（M3）、基准（M4）、GUI/打包（M5）、发布（M6）。

## 二、M1 待办（数据先行）

按 `plan/05-数据计划与里程碑.md` §二 M1：

1. **规则数值核对与填回**（最高优先，这是解开门控的唯一路径）：
   - 逐条核对 GB/T 32150-2025 / 2015 的排放源纳入规则 → 填 `boundary.sources[].required` 与 `delta_vs_2015`；
   - 通则元数据（发布/实施日期、代替关系、有效性）→ 填 `standard.*`；
   - 氧化率系数、行业缺省因子、校核阈值、配额方法学 → 填 `engine.coefficients` / `factors` / `quality.thresholds` / `quota.*`；
   - **每条填回时必须同时**：设 `status: "verified"`、填 `clause`（标准号 + **真实**条款号）、填 `ref`（出处名 + URL + 版本/日期）。
   - 填回后**必须**在 `data/README.md` §二登记核对结论与渠道。
   - **填回位置**：`tools/gen_rulesets.py` 的模板函数（产物是冻结的，不能手改 JSON）；填完重跑生成器。

2. **官方排放因子库（第二版）入库**：`data/factors/`，登记来源 URL/版本/sha256。

3. **合成企业档案 + 真值库**：`tools/gen_synthetic.py`（自研确定性 RNG，**禁 stdlib random**）+ `data/truth/`；真值由脚本计算并断言，非手抄。

4. 核对渠道纪律：官方页面直连（openstd.samr.gov.cn / mee.gov.cn / data.ncsc.org.cn），**搜索摘要一律不采信**；两渠道查不到 → 标 `pending` 继续推进，不空转。

**M1 DoD**：见 `plan/05` §二 M1；`calc` 在至少一个坐标上端到端出数（即该坐标全部条目 verified 且门控放行）。

## 三、既定口径清单（动了会打挂基准/测试，改前先对照）

| # | 约定 | 位置 | 影响 |
|---|---|---|---|
| P1 | 条目 id 命名（`source.id` 全局稳定，不随年度改名） | `tools/gen_rulesets.py` | 双标尺 diff、真值库、报告溯源表 |
| P2 | `status` 门控语义：`pending` 绝不进计算路径（含 `value: null` 的 verified 条目） | `rules._entry_is_effective` | CLI 退出码、全部基准 |
| P3 | CLI 退出码 0/1/2 语义 | `errors.py` + `plan/03 §六` | CLI 测试、批处理用户 |
| P4 | 冻结产物字节口径：无 CR、无时间戳、键排序固定、`write_bytes` | `jsonio.write` + `gen_rulesets.py` | 冻结守门测试、manifest sha256 |
| P5 | 表达式文法白名单（`mul/add/sub/div/var/const`；const 必须 ref，禁内联数值） | `engine.py` | 引擎求值器、规则包校验 |
| P6 | 零政策字面量门禁：**只扫引擎/前端源码**（`code/src/ghg/**`，含注释与 docstring）；生成器 `tools/gen_*.py` 属真相源不扫（见 D0-13）；token 从规则包数值字段采集；豁免 = units.json / 免责声明法律文本 / `Decimal(1).scaleb(-n)` 精度位 / 标准号（元数据） | `tools/check_zero_literals.py` + `plan/06 §二` | 门禁测试 |
| P7 | 免责声明文本（法律文本，入代码豁免门禁） | `gen_rulesets.py` `DISCLAIMER` | 报告模板、02 R3 |
| P8 | 坐标空间与短键（`gbt32150-2015/2025`、2022–2026、power/steel/cement/aluminum） | `data/rules/manifest.json`（**单一真相源**）+ `gen_rulesets.py` | 坐标测试、CLI、文档计数 |

> ⚠️ **P8 是 M1 最易踩的坑**：年度/行业/标准短键只准在生成器与 manifest 里定义，**代码内不得内联**（由门禁与测试双重守护）。

## 四、本机环境坑（只写实测过的）

1. **解释器**：用 `py`（不是 `python`，后者可能是商店占位符）；脚本一律 `py -X utf8`（中文控制台编码）。本机 `py -0p` = 3.8.8 + 3.12。
2. **pyc 偶发损坏**：全程 `PYTHONDONTWRITEBYTECODE=1`（含 `pip install`）；出怪错先清 `__pycache__`，单轮崩溃直接重试。
3. **pip 代理污染**：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（若报代理错加 `NO_PROXY="*" no_proxy="*"`）。
4. **Path.write_text(newline=) 是 3.10+**：3.8 上报错，统一用 `write_bytes`（本仓库已如此）。
5. **Git Bash 路径**：`/tmp` 与 Windows Python 路径不通；临时文件用工作区相对路径或 `tmp_path` 夹具。
6. **测试运行**：`cd code && py -X utf8 -m pytest -q`；`capsys.readouterr()` 只能消费一次。

## 五、DoD 逐项 checklist（M0）

- [x] M0-1 plan/02–06 定稿（六份文档存在且 00 索引 ✅）
- [x] M0-2 `pip install -e ".[dev]"` 成功
- [x] M0-3 coordinates/rules/units/engine 四模块可用
- [x] M0-4 manifest + 40 坐标包 + units.json 生成，重生成位级一致
- [x] M0-5 CLI 七个子命令（coords/rules show/rules check/calc/check/convert/units/selftest/version）
- [x] M0-6 坐标门控实测拦截（`calc` → rc 1）
- [x] M0-7 混算拦截实测（`calc` 混算 → rc 2）
- [x] M0-8 零政策字面量门禁通过（含阳性对照）
- [x] M0-9 冻结守门：无 CR 字节 + 重生成 sha256 一致 + manifest 对账
- [x] M0-10 CI workflow 三矩阵 + `fetch-depth: 0`（本地守门测试通过；GitHub 首跑待 M6）
- [x] M0-11 README 快速开始可用
- [x] M0-12 HANDOFF-M1 落盘（本文件）

**偏差说明**：M0-10 的"CI 首跑"未做——本地无远端仓库（`git remote -v` 为空），推送需 M6 且是对外动作（届时向用户确认）。本地以 workflow 解析/结构守门测试替代验证，如实留档。

## 六、关键命令速查

```bash
# 全量测试
cd code && py -X utf8 -m pytest -q && cd ..

# 零政策字面量门禁（含阳性对照）
py -X utf8 tools/check_zero_literals.py --selftest

# 重生成规则包（应位级一致，git status 无变化才正常）
py -X utf8 tools/gen_rulesets.py

# CLI 实测（注意：退出码要单跑，别接管道——管道会吞掉真实退出码）
PYTHONPATH=code/src py -X utf8 -m ghg.cli coords
PYTHONPATH=code/src py -X utf8 -m ghg.cli rules check      # → rc 1（M0 预期）
PYTHONPATH=code/src py -X utf8 -m ghg.cli selftest         # → rc 0
```

## 七、下一棒建议动作顺序

1. 先跑一遍"关键命令速查"三条，确认基线仍绿（防"接手时已经不绿"）。
2. 打开 `data/README.md` §二，从**已确认的锚点**（GB/T 32150-2025 发布/实施日期）开始逐条核对。
3. 核对一条 → 改生成器 → 重跑生成器 → 跑测试（`test_rules_gate.py::test_all_policy_values_are_null_in_m0` 会变红，**这是预期的**：该测试是 M0 初态守门，M1 开始填值后应改名为"已核对条目数 > 0"的等价断言，而不是删掉）。
4. 全部核对完一个坐标 → `ghg calc` 该坐标应首次返回 0。
