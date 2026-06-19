> 命名规范 —— 由根 `CLAUDE.md` 的「## Naming Convention」通过 `@import` 引用。
> 改这里 = 改全项目的文件 / 目录 / 产物命名约定（团队共享，随 `.claude/` 提交）。

> 本文件只管**项目级的数据 / 产物 / 文件 / 目录命名**。Python 标识符（`snake_case` /
> `PascalCase` / `UPPER_SNAKE` / 私有前导下划线）、缩写一致性、物理量单位后缀、一次性脚本
> 命名（`_tmp_*.py` / `_patch_*.py` / `tools_*.py`）见 `code-style.md`；分支 / commit /
> 版本 tag / changelog 文件名见 `git-workflow.md`。

### 车辆 / 目录 / skill

- **车牌（vehicle registration）**：大写、无空格，照车牌原样（如 `YK73WFN`、`CMZ6260`）；
  作为 `<REG>` 标记贯穿目录名、报告文件名与配置文件。
- **文件夹**：小写 `snake_case`（如 `data_analysis_workspace`、`excel_report_database`）；
  唯一例外是核心包目录 `src/jolt_toolkit`。
- **skill / agent / command**：kebab-case（如 `plot-figure`、`generate-excel-report`、
  `jolt-toolkit-dev`）。

### 日期 / 周期

- 数据字段、按天的时间戳：ISO `YYYY-MM-DD`。
- 带日期的目录（如 `monthly_presentation/<YYYYMMDD>/`）：紧凑 `YYYYMMDD`。
- 报告周期：`YYYYMMDD_YYYYMMDD`（start_end）。

### 报告产物

- 报告文件：`excel_report_database/<version>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx`。
- HTML 查看器：`inspect_*.html`；原始遥测：`raw_telematics/raw_*.csv`；
  校验图：`validation_<REG>_<date>_<HHMM>.png`。
- 后处理（finetune）产物一律加 `*_finetuned.*` 后缀，**绝不覆盖原始文件**。

### 版本化输出布局

- `excel_report_database/<version>/<REG>/` 与 `figures/<version>/{named,anon}/`
  （`named` = 真实 OEM 标签，`anon` = 匿名化）；`<version>` 即 `src/jolt_toolkit` 的 SemVer。

### 双语文档

- `README.md` 为提交入库的英文权威版；`README.zh.md` 为 gitignore 的中文副本，
  通过 `/translate-doc` 保持同步。
