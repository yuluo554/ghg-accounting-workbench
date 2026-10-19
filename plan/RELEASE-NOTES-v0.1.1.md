# v0.1.1 —— 可复现口径、台账补齐与运行时现代化

v0.1.0 之后的修正版（**行为不变**：规则包数值/status、引擎判定、三类基准阈值、真值 fixtures、
退出码 0/1/2、打包白名单全部未动）。四项变更：

## 1. `--generated-at`：报告与核算输出可完全复现

NFR-04 原文是「同一输入 + 同一规则包 → 逐字节相同输出」，但 FR-06.3 要求报告头固定输出生成时间——
两者只有在**时间可注入**时才能同时成立。

```bash
# 固定生成时间后，11 个产物（MD + 9 CSV + XLSX）可逐个比对 sha256
ghg report --input data/truth/profiles/steel-2024.json --out-dir out \
  --with-check --with-quota --benchmark-value 2 --output 166150 \
  --generated-at 2026-01-01T00:00:00

# calc 同样支持；两次 stdout 完全一致
ghg calc --input data/truth/profiles/steel-2024.json --generated-at 2026-01-01T00:00:00
```

- 缺省仍取当前本地时间（便于审计追溯导出时刻）；
- 非法 ISO 值 → **退出码 2**（不静默回落到当前时间）；
- CLI 级测试锁定：固定时间两次导出 11 产物 sha256 全同、`calc` stdout 两次一致、非法值 rc 2。

## 2. 知识快照台账补齐（27 份 / 9 份 PDF）

此前 `data/knowledge/raw/` 有 27 个 tracked 文件，但 `clauses.json` 只登记 21 份 sha256——
"逐份 sha256"是假话。现补齐 6 份访问证据（更新通知附件 1/2 的 PDF 原件、核查指南全文
pdftotext 文本、生态环境部栏目列表页），并新增守门测试：
`raw/` 下每个文件必须在台账中有 sha256，台账不得登记不存在的文件，逐份 sha256 必须一致。

守门可证伪：删掉任一条 `sha256`，测试立即失败。

## 3. 文档自述与事实对齐

- README 里程碑 M6 行由 `⬜` 改为 `✅ 2026-10-13`（与首屏"已发布"不再自相矛盾）；
- 测试数由陈旧的 `288` 回写为实测值（本轮 `317 passed`）；
- `data/README.md` 快照份数由「21 份含 6 份 PDF」改为实测的「27 份含 9 份 PDF」；
- 演示素材重生成：版本号同步、截图内档案路径改为仓库相对形式（不再暴露开发机绝对路径）。

## 4. 运行时与打包现代化

| 项 | v0.1.0 | v0.1.1 |
|---|---|---|
| Python | `>=3.8` | **`>=3.12`**（3.8 已于 2024-10-07 EOL） |
| GUI extra | `PySide6>=6.6,<7` | **`PySide6>=6.12,<7`** |
| build extra | `pyinstaller>=5.13,<6` + `setuptools<81` | **`pyinstaller>=6.22,<7`**（6.x 不再依赖 `pkg_resources`，无需降级 setuptools） |
| CI actions | checkout@v4 / setup-python@v5 | **checkout@v7 / setup-python@v7** |
| CI 矩阵 | windows×{3.8,3.12} + ubuntu×3.12 | **windows×3.12 + ubuntu×3.12** |
| CI 打包 | 无 | **新增 package job**：真构建两个 spec + 双 exe `--selftest` + 随包数据白名单探活 |

实测环境：py3.12.10 + PySide6 6.12.0 + PyInstaller 6.22.3 → 全量测试全绿、两个 spec 均构建成功、
双 exe `--selftest` rc 0。

## 附件

| 附件 | 说明 |
|---|---|
| `ghg-cli-windows-x64.zip` | 命令行形态（免安装，解压即用） |
| `ghg-gui-windows-x64.zip` | 桌面形态（PySide6 四页签，免安装） |

各附件字节数与 sha256 见 [RELEASE-v0.1.1.md](RELEASE-v0.1.1.md) §三。

## 已知限制（与 v0.1.0 相同，如实列出）

- **官方因子库未摘录**：`data.ncsc.org.cn` 直连恒返回 HTTP 412（WAF），台账如实留空、不编造数值；
  缺省因子由四行业指南附录 A 官方缺省值承担。
- **核算路径 38/40**：2026 年度发电碳氧化率待因子库，该 2 个坐标核算路径被门控拦截。
- **配额平衡值属外部输入**：三行业行业平衡值仅平台可查，工具按外部输入显式索取（缺失即退出码 2）。
- **首期四行业**：发电 / 钢铁 / 水泥 / 铝冶炼。
- **CBAM 未做**：属 P2 扩展位。

## 许可

MIT，见 [LICENSE](../LICENSE)。
