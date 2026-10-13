# RELEASE-M6 —— 发布留档（脱敏发布 + 收尾固化）

> 状态：**已发布**（2026-10-13）。仓库 <https://github.com/yuluo554/ghg-accounting-workbench>，
> Release [`v0.1.0`](https://github.com/yuluo554/ghg-accounting-workbench/releases/tag/v0.1.0)，
> 三矩阵 CI 全绿（run `38388887546`）。
> 本文件记录**发布前验证 + 发布时/发布后回填结果**，全部为实测值。
> 关联：`plan/05` §二 M6、`plan/06` §一之七（D6-1~7）与 §三（O-6/O-7）。

---

## 一、发布对象（实际值）

| 项 | 值 |
|---|---|
| 仓库名 | `ghg-accounting-workbench`（<https://github.com/yuluo554/ghg-accounting-workbench>） |
| 账号 | `yuluo554`（GitHub user id `282769740`） |
| 可见性 | **public**（已核对 `gh repo view`） |
| 默认分支 | `main` |
| 提交数 | **15**（含 CI 首跑修复） |
| HEAD = 标签指向 | `6ce552dc6ef435696cf4e88155d214985b69e600` |
| 标签 | `v0.1.0`（指向 HEAD，已 `--verify-tag` 创建 Release） |
| 许可 | MIT |
| 远端协议 | SSH（`git@github.com:yuluo554/ghg-accounting-workbench.git`） |

> **注**：首版标签曾指向 `e4a46a9`（CI 首跑前的提交）；CI 首跑暴露 ubuntu 缺 Qt 系统库后，
> 修复提交 `6ce552d` 已入 main，标签随之移动到该全绿提交（Release 已按 `--verify-tag` 重建）。

## 二、脱敏结果（O-6，已完成）

| 检查项 | 结果 | 证据 |
|---|---|---|
| 全历史提交身份为 noreply | ✅ | `git log --all --format="%ae %ce"` → 全部 `282769740+yuluo554@users.noreply.github.com` |
| 旧地址在 `ae` 与 `ce` 两字段均不存在 | ✅ | `tools/desensitize.py verify --deny-email <旧地址>` → rc 0（**两个字段分别断言**） |
| `refs/original` 已清 | ✅ | `git for-each-ref` 仅 `refs/heads/main` |
| reflog 已过期 + gc | ✅ | `rewrite` 四步内置执行 |
| 工作树无个人邮箱 / 开发机路径 | ✅ | `desensitize.py audit` → 工作树项 rc 0 |
| 构建产物无泄露 | ✅ | `desensitize.py audit --build-dir dist/ghg-cli --build-dir dist/ghg-gui` → rc 0 |
| 随包真值档案声明合成 | ✅ | 19 份 `profiles/*.json` 全部 `synthetic: true`，代码带 `SYN` 标记 |

**改写留档（如实）**：首版 env-filter 用 `if/elif` 串联 author 与 committer，
ae 命中即跳过 ce，导致**只改了一半**（实测 ce 仍留真实邮箱）；由 `verify` 当场暴露，
改为两段独立 `if` 后全量改写（见 `plan/06` D6-4）。

## 三、发布附件（ASCII 名 + sha256）

由 `tools/desensitize.py pack` 生成（固定时间戳，**两次打包逐字节一致**，已实测）。
重新打包命令：`py -X utf8 tools/desensitize.py pack`；核对命令：`... ledger --json`。

| 附件名 | 内容 | 字节数 | sha256 |
|---|---|---|---|
| `ghg-cli-windows-x64.zip` | `dist/ghg-cli/`（CLI exe + 随包数据） | 13,270,709 | `685b1018fc304ee64205bd13498d716cfcb2034d1f8b824fd4753ce803b1d42d` |
| `ghg-gui-windows-x64.zip` | `dist/ghg-gui/`（GUI exe + PySide6 + 随包数据） | 105,230,330 | `4d3a0e6b72abe9196d7309575935d25358b9a7dd60d1552cc3cc95e66fc780b3` |

> 附件哈希随 exe 重建而变（PyInstaller 产物本身非字节确定）；**发布时以当次 `ledger` 输出回填**。
> 可复现的是**打包这一步**（同 dist → 同 zip 字节），不是 exe 构建这一步。

## 四、发布前验证（已完成）

| 验证项 | 结果 |
|---|---|
| 全量测试（Windows / py3.8） | **310 passed** |
| 全量测试（Windows / py3.12） | **310 passed** |
| 零政策字面量门禁（含阳性对照） | rc 0（token 集 13） |
| 内置基准三类 | 全部达标（rules 480/480、factor 116/116、cases 29/29；误报 0；≈0.039 s） |
| CLI exe `--selftest` | rc 0（含"冻结态数据目录在 exe 目录内"断言） |
| GUI exe `--selftest` | rc 0 |
| 干净环境（新 clone + 全新 venv，逐条照 README §三/§三之二） | rc 全 0；`302 passed, 5 skipped`（dist 未构建项） |
| 发布后 GitHub clone（SSH） | `305 passed, 5 skipped`（装齐 `[dev,gui]` 后；与本地 310 口径一致） |
| 冻结产物字节一致（克隆后 sha256） | 与源仓库逐字节相同（`.gitattributes` 的 `-text` 生效） |
| 官方因子库复核（O-7） | 2026-10-13 复测仍 **HTTP 412**（多 UA + Referer + cookie 会话）→ 台账维持如实留空 |

**干净环境发现并修复的缺口**：`build` extra 未钉 `setuptools<81` → py3.12 新建 venv 上
`python -m PyInstaller` 直接 `ModuleNotFoundError: No module named 'pkg_resources'`
（PyInstaller 5.x 仍 import 该模块，setuptools 81 起移除）。已钉进 extra + README + 守门测试（D6-7）。

## 五、对外动作（已执行，用户确认后）

> 以下步骤**对外且不可逆**（创建公开仓库、推送全历史、发布 Release），已按 plan 纪律先向用户确认再执行。
> 记录的是**实际执行的命令**（含首跑修复后移动标签、重建 Release 的步骤）。

```bash
# 1. 建立远端（不带 --push，先建后推，便于切 SSH）
gh repo create ghg-accounting-workbench --public --source . --remote origin \
  --description "企业温室气体排放核算与报告工作台：GB/T 32150 新旧双标尺 × 年度 × 行业三维版本化规则集，全本地核算、可核证报告（CLI + PySide6 桌面 + exe）"

# 2. 切 SSH（避免 https 凭据残留）
git remote set-url origin git@github.com:yuluo554/ghg-accounting-workbench.git

# 3. 推送全历史（首次 push 即 CI 首跑）
git push -u origin main

# 4. 首跑 CI 暴露 ubuntu 缺 Qt 系统库 → 修复提交并推送（→ 三矩阵全绿）
git push origin main

# 5. 打标签 + 发布 Release（附双附件；标签移动后按 --verify-tag 重建）
git tag -a v0.1.0 -m "v0.1.0：M0–M6 全部完成，三矩阵 CI 全绿"
git push origin v0.1.0
gh release create v0.1.0 \
  dist/ghg-cli-windows-x64.zip dist/ghg-gui-windows-x64.zip \
  --title "v0.1.0 —— 企业温室气体排放核算与报告工作台" \
  --notes-file plan/RELEASE-NOTES-v0.1.0.md --verify-tag
```

## 六、发布后回填（DoD，全部实测）

| # | 项 | 结果 |
|---|---|---|
| R-1 | CI 首跑三矩阵（windows×{3.8,3.12} + ubuntu×3.12） | ✅ **全绿**（run `38388887546`）。首跑曾失败：ubuntu 缺 `libEGL.so.1`（PySide6 需系统图形库）→ 补装 `libegl1/libgl1/libxkbcommon0` 等后通过（见 `plan/05` §三 预判的"系统库"风险） |
| R-2 | GitHub 全新 clone 复核 | ✅ SSH clone 成功；HEAD `6ce552d`、标签 `v0.1.0` 在位、全历史身份为 noreply；`305 passed, 5 skipped`（dist 未构建项）+ 门禁 rc 0 + 基准三类达标 + 脱敏审计 rc 0 |
| R-3 | Release 附件与本地一致 | ✅ 双附件 `state=uploaded`，字节数与本地逐一致（`13,270,709` / `105,230,330`）；本地 sha256 见 §三 |
| R-4 | HEAD / 标签实际值 | ✅ HEAD = 标签 = `6ce552dc6ef435696cf4e88155d214985b69e600`；提交数 15 |
| R-5 | 附件 sha256（当次 ledger 实际值） | ✅ 见 §三（`pack` 两次逐字节一致已实测） |

> 回填原则：**只写实测到的**；未跑的项保持 ⬜ 并说明原因，不留空、不预填。
> 本表全部为实测值，无遗留 ⬜ 项。

