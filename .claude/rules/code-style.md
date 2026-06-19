> Python 代码规范 —— 由根 `CLAUDE.md` 的「## 代码规范」通过 `@import` 引用。
> 改这里 = 改全项目的代码风格约定（团队共享，随 `.claude/` 提交）。

Python 代码遵循 PEP 8，并用 `pyproject.toml` 中 `[project.optional-dependencies].dev`
已配置的工具统一风格：

- **格式化**：`black`（默认行宽 88）。
- **import 排序**：`isort`（标准库 / 第三方 / 本地三组分隔）。
- **静态类型**：`mypy`；公开函数尽量给出参数与返回值的类型注解。

### 命名规则

| 对象 | 风格 | 示例 |
|------|------|------|
| 包 / 模块文件 | `snake_case` | `report_generator`、`segment_algorithms.py` |
| 函数 / 方法 / 变量 | `snake_case` | `compute_ep`、`find_speed_trips` |
| 类 | `PascalCase` | `JOLTReportGenerator`、`WeatherPatcher` |
| 常量 / 模块级配置 | `UPPER_SNAKE_CASE` | `HEADERS`、`BASELINE`、`ETA_DT` |
| 内部 / 私有（模块 / 函数 / 属性） | 前导下划线 | `_generator.py`、`_seg_to_row()`、`_safe_num()` |

- 标识符一律用英文；项目内缩写保持一致（`ep` = energy performance、`soc`、`crr`、`cda` 等）。
- 带物理单位的量在名字或注释里标明单位，如 `delta_energy_kwh`、`mass_kg`、`v_c`（m/s）。

### 其它约定

- 路径优先用 `pathlib.Path`；字符串格式化用 f-string。
- 一次性 / 临时脚本用 `_tmp_*.py` / `_patch_*.py` 命名（已 gitignore，用完即删、不写进 README）。
- **代码注释与 docstring 一律用英文**——即使工作 / 交流语言是中文。代码随仓库共享，注释统一
  英文便于国际协作；终端回复、changelog、文档正文等面向人的文字仍遵循「语言规范」。

### 子项目独立性（2026-06-11 起）

各 workspace（`data_analysis_workspace/`、`research_projects/`、`publication_workspace/`、
`monthly_presentation/` 等）下的子项目必须**互相独立**——子项目是可复现的研究存档，
应当可以被单独删除/归档而不损坏其它子项目：

- 允许的代码依赖只有三类：stdlib / pip 包、版本化的 `src/jolt_toolkit`
  （含 `jolt_toolkit.analysis`：计数器插值、OLS/FE 回归工具、`eta_bat` 物理模型）、
  子项目自身文件。**禁止 `sys.path.insert` 指向其它子项目**——需要别处的代码就拷贝（vendoring）。
- vendored 副本必须带 provenance 头：来源 repo 相对路径、拷贝日期、符号清单、
  原因（sub-project independence）；不与来源同步意图就不要改函数体。
- **三次法则**：被 3+ 个子项目复用且已稳定的机器代码，提升进 `jolt_toolkit.analysis`
  （改动 route 给 jolt-toolkit-dev agent，按 SemVer minor 升版本），不要无限复制。
- 数据依赖只允许读 `excel_report_database/<version>/`（版本化、append-only），
  **禁止读其它子项目的 `results/`**。文档互链（README link）不受限制。
- 旧于本约定的冻结快照（`monthly_presentation/20260422/`、`data_analysis_workspace/deprecated/`）
  豁免（grandfathered），不保证可重跑、不得扩展。
- 只读检查：`python .claude/scripts/check_subproject_independence.py [--verbose]`
  （AST 解析 `sys.path.insert` 目标，违规 exit 1）。

> 报告生成包的架构约定（src-layout、统一分段算法、`HEADERS` 列序、configs、deprecated 等）
> 见 `src/jolt_toolkit/README.md`；各大目录的 agent 归属与「改其代码请 route 给对应 agent」的
> 纪律见各 `.claude/agents/*.md` 定义（agent 描述里已声明 owner）。
