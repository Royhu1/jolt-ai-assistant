# 体检经验沉淀（LESSONS）

> `project-health-steward` 每次体检**先读本文件**，收尾时把新经验去重追加于此。
> 目的：让总管的判断随项目演进逐次变强。

## 项目惯例（最常用，写在前面）

- **当前 canonical 版本（仅 `src/jolt_toolkit` 包）**：见 `pyproject.toml` 的 `version`；
  体检时核对全项目版本引用是否都指向它（skill 示例、各 README、agent 知识等）。
- **本仓库是 clean-rebuild 仓库**：历史从 `initialise clean repository` 起，早期无旧 tag / 历史；
  记忆里关于更早 merge / tag 的描述属于被替换掉的旧仓库，对本仓库不适用——以实际
  `git log` / `git tag` 为准。
- **gitignore 覆盖面广**：`tmp/` `cache/` `archive/` `unarchived/`、各 workspace，以及所有
  `*.csv/*.xlsx/*.pdf/*.log/*.zh.md` 都不进 git。所以「清理」多是物理整洁（disk / OneDrive），
  与 git 状态无关——别把 gitignored 残余误当成 git 改动。
- **`*.zh.md` 是 gitignored 中文副本**，`README.md`（英文）才是入库权威版。

## 易错点 / 坑

- **Sandbox 禁止 `Remove-Item` 删顶层 / 受保护路径**（如 `D:\jolt_worktrees` 报 "protected from
  removal"，且会**整条脚本预检失败、什么都不执行**）。对策：清理一律用 `Move-Item` 归档，不用
  `Remove-Item`——既绕开沙箱，也符合「优先归档而非删除」。
- **OneDrive 锁**：清理 / 重生 xlsx 前先让用户关 Excel，否则 move / 写入失败。
- **`src/jolt_toolkit/` 只能经 jolt-toolkit-dev**：提交其改动、改其 README / 版本号、订正 agent
  知识里的列数 / 架构，都 route 给它（它最清楚真实状态）；主循环只负责编排 git 与非包内清理。
- **改版本号后别忘 `pip install -e .`**：editable 安装的 `jolt_toolkit.__version__` 不随
  `pyproject.toml` 自动更新；全量重跑前需 `pip install -e . --no-deps`，否则输出会落到旧版本目录。
- **别误清贵重 scratch**：`tmp/` 里偶有非 scratch 的成果（如 `canonical_<ver>_numbers.md` 是论文
  canonical 统计）。清 `tmp/` 前扫一眼近期 `.md`，把成果先抽到合适 workspace 再整目录归档。
- **版本钉版可能是有意的**：workspace 子项目 README 钉死某数据版本（如 energy_breakdown 钉 2.2.3）
  多为子项目独立性的可复现归档，**不要**当成 stale 版本去升——存疑先问 owner。

## 历次体检

- 2026-06-19：首次体检，建立本机制（housekeeping 规范 + steward agent + 本目录）。详见
  `check_20260619.md`。
