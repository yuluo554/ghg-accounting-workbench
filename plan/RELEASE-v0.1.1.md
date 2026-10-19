# RELEASE-v0.1.1 —— 发布留档

> 状态：**已发布**（2026-10-19，Release 创建于 13:01Z，附件上传完成 13:04Z）。
> 仓库 <https://github.com/yuluo554/ghg-accounting-workbench>，
> Release 目标 [`v0.1.1`](https://github.com/yuluo554/ghg-accounting-workbench/releases/tag/v0.1.1)。
> 本文件记录**发布前验证 + 发布时/发布后回填结果**，全部为实测值。
> 关联：`plan/RELEASE-M6.md`（v0.1.0 发布留档）、`plan/RELEASE-NOTES-v0.1.1.md`、`plan/06` §一之八（D7-1~D7-6）。

---

## 一、发布对象（实际值）

| 项 | 值 |
|---|---|
| 仓库 | `ghg-accounting-workbench`（PUBLIC / MIT / non-fork） |
| 默认分支 | `main` |
| 发布提交（代码 / v0.1.1 标签） | `d7d7533dbad54ba8900411b622200340c34f800f`（代码提交为 `60aeac3`；`d7d7533` 仅新增本文件） |
| Release 地址 | <https://github.com/yuluo554/ghg-accounting-workbench/releases/tag/v0.1.1> |
| 上一版本 | `v0.1.0`（标签未移动） |
| 版本号 | `code/pyproject.toml` = `code/src/ghg/__init__.py` = `code/gui/ghg_gui/__init__.py` = `0.1.1` |
| 构建环境 | **干净 clone + 新 venv**：py3.12.10 / PySide6 6.12.0 / PyInstaller 6.22.3 |

> **附件来源**：本次附件由 **新 clone（`60aeac3`）+ 全新 venv** 构建并打包，
> 而不是本机工作树里的 `dist/`。理由：这条链路任何人都能复验
> （clone → `pip install -e "code[dev,gui,build]"` → 两个 spec → `pack`）。
> 两次独立构建的 exe **字节不同**（PyInstaller 产物非字节确定），但**目录总字节完全相同**
> （CLI 18,039,526 B / GUI 123,924,999 B），见 §四。

---

## 二、发布前验证（全部实测）

| 验证项 | 结果 | 命令 |
|---|---|---|
| CI test（ubuntu / py3.12） | ✅ success | run `39255830402` |
| CI test（windows / py3.12） | ✅ success | 同上 |
| CI **package**（windows / py3.12，双 spec 构建 + 双 exe selftest） | ✅ success | 同上 |
| 干净 clone 全量测试 | `312 passed, 5 skipped`（5 项为 dist 未构建项的既有跳过） | `pytest code/tests -q` |
| 干净 clone 零政策字面量门禁 | `ZERO_LITERAL_GATE_OK`（阳性对照命中 `0.03`） | `tools/check_zero_literals.py --selftest` |
| 干净 clone 三类基准 | 全部达标（480/480、116/116、29/29；误报 0；0.061 s） | `tools/bench.py` |
| 干净 clone 脱敏审计 | `DESENSITIZE_AUDIT_OK` | `tools/desensitize.py audit` |
| 干净 clone 构建后脱敏审计 | `DESENSITIZE_AUDIT_OK`（构建产物无泄露） | `audit --build-dir dist/ghg-cli --build-dir dist/ghg-gui` |
| CLI exe `--selftest` | rc 0（含"冻结态数据目录在 exe 目录内"） | `./dist/ghg-cli/ghg-cli.exe --selftest` |
| GUI exe `--selftest` | rc 0 | `QT_QPA_PLATFORM=offscreen ./dist/ghg-gui/ghg-gui.exe --selftest` |
| exe 版本 | `ghg 0.1.1` | `./dist/ghg-cli/ghg-cli.exe version` |
| 本机工作树全量测试 | `317 passed`（含 dist 已构建的 5 项） | `pytest code/tests -q` |

---

## 三、发布附件（ASCII 名 + sha256）

由 `tools/desensitize.py pack` 生成（固定时间戳，**两次打包逐字节一致**）。
**发布附件取自干净 clone 的 dist**（见 §一 说明）。

| 附件名 | 内容 | 字节数 | sha256 |
|---|---|---|---|
| `ghg-cli-windows-x64.zip` | `dist/ghg-cli/`（CLI exe + 随包数据） | 18,052,906 | `f6afc3221d2c1b8318e9d49b23627031bd8f350658a1aeca3c8e487fff52604b` |
| `ghg-gui-windows-x64.zip` | `dist/ghg-gui/`（GUI exe + PySide6 + 随包数据） | 123,962,741 | `a120b2d142ec39ccc677e08e8f0a02b149ba5b743c833545d27c8d105735fc22` |

### 附：本机工作树另一次构建的对照（未上传）

| 附件名 | 字节数 | sha256 |
|---|---|---|
| `ghg-cli-windows-x64.zip` | 18,052,906 | `8b56292a78d1fb7df26b887581f91dafeca1c9adb78b2ed09dd96b70aa3710d4` |
| `ghg-gui-windows-x64.zip` | 123,962,741 | `31431eb287ef6530728501e628d9789ac54a9b0c33514ec607f87b0507016d09` |

> 两次构建 zip 大小完全相同、sha256 不同：差异来自 exe 内的构建时间等非确定字段。
> **可复现的是"同一 dist → 同一 zip 字节"**（`pack` 两次实测 sha256 相同），
> 不是"同一源码 → 同一 exe 字节"。此口径与 `plan/06` D6-6 一致。

---

## 四、构建可比性（实测）

| 项 | 本机工作树构建 | 干净 clone 构建 |
|---|---|---|
| 源码提交 | `60aeac3`（工作树干净） | `60aeac3` |
| Python / PySide6 / PyInstaller | 3.12.10 / 6.12.0 / 6.22.3 | 3.12.10 / 6.12.0 / 6.22.3 |
| `ghg-cli` exe 字节数 | 1,829,983 | 1,829,983 |
| `ghg-gui` exe 字节数 | 1,859,295 | 1,859,295 |
| `ghg-cli` 目录总字节 | 18,039,526 | 18,039,526 |
| `ghg-gui` 目录总字节 | 123,924,999 | 123,924,999 |
| exe 内容 sha256 | 不同（构建时间等非确定字段） | 不同 |

结论：**尺寸与内容构成一致，exe 字节不一致**——PyInstaller 产物本身非字节确定，如实记录，不宣称"exe 可复现"。

---

## 五、发布动作（实际执行的命令）

```bash
# 1. 推送发布提交（已在发布前完成）
git push origin main                     # 462f9ad..60aeac3

# 2. 确认 CI 三 job 全绿（run 39255830402：test ubuntu / test windows / package）

# 3. 打标签
git tag -a v0.1.1 -m "v0.1.1：报告输出可复现（--generated-at）、快照台账补齐、文档回写、运行时现代化（py3.12 + PySide6 6.12 + PyInstaller 6.22）"
git push origin v0.1.1

# 4. 发布 Release（附件取自干净 clone 的 dist）
gh release create v0.1.1 \
  <clone>/dist/ghg-cli-windows-x64.zip <clone>/dist/ghg-gui-windows-x64.zip \
  --title "v0.1.1 —— 可复现口径、台账补齐与运行时现代化" \
  --notes-file plan/RELEASE-NOTES-v0.1.1.md --verify-tag
```

---

## 六、发布后回填（DoD，全部实测）

| # | 项 | 结果 |
|---|---|---|
| R-1 | CI 三 job（test ubuntu / test windows / package） | ✅ 全绿：代码提交 `60aeac3` → run `39255830402`；留档提交 `d7d7533` → run `39256392977`；两次均 test×2 + package 全 success |
| R-2 | 干净 clone 复验 | ✅ SSH clone @ `60aeac3`；`312 passed, 5 skipped` + 门禁 rc 0 + 基准三类达标 + 脱敏审计 rc 0 |
| R-3 | 干净 clone 构建 | ✅ 两个 spec `Build complete!`；双 exe `--selftest` rc 0；`version` → `ghg 0.1.1` |
| R-4 | Release 附件上传 | ✅ 双附件 `state=uploaded`；字节数与本地一致（见 §七） |
| R-5 | 发布物下载复验 | ✅ 见 §七（下载后解压 + 双 exe `--selftest` rc 0） |

---

## 七、发布物下载复验（实测）

| # | 项 | 实测结果 |
|---|---|---|
| V-1 | 下载两个附件 | `gh release download v0.1.1` rc 0；字节数 18,052,906 / 123,962,741，与上传前一致 |
| V-2 | 下载物 sha256 | CLI `f6afc322…52604b`、GUI `a120b2d1…35fc22` —— **与本地打包值逐字节相同** |
| V-3 | 解压后 CLI `--selftest` | rc **0**；输出含「冻结态数据目录在 exe 目录内」 |
| V-4 | 解压后 GUI `--selftest`（offscreen） | rc **0**；同上断言通过 |
| V-5 | 解压后 `version` | `ghg 0.1.1` |
| V-6 | 解压后 `bench` | 三类基准全部达标（12/12 命中、误报 0） |
| V-7 | 解压后 `rules check` | 核算 38/40、配额 40/40、校核 40/40，退出码 **1**（既有契约） |
| V-8 | 发布包内容 | CLI zip 76 条目、GUI zip 230 条目；两者均**不含** `knowledge/raw`；随包 `knowledge/` 只有 `clauses.json`（21,452 B） |
| V-9 | 打包可复跑 | 同一 dist 连续两次 `pack`，两个 zip sha256 完全相同 |

> 复验目录：`%TEMP%\ghg-rel-v011`（下载 + 解压 + 运行），复验后保留为证据，可按需删除。

> 回填原则：**只写实测到的**；未跑的项明确写"未验证"，不留空、不预填。
