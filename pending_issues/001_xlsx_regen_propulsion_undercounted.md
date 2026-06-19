# 001 — Excel 报告 / dashboard 的 regen 能量被严重低估（~5%，应 ~19%）

- **状态**：OPEN（已分析，暂缓修复）
- **发现日期**：2026-06-17
- **负责方**：`jolt-toolkit-dev`（`src/jolt_toolkit/` 唯一负责人）——这是源数据（xlsx 列）问题
- **优先级**：中（不阻塞当前交付；PDF 简报已单独在 skill 内绕过，见下）

## 摘要

`excel_report_database/<ver>/<REG>/jolt_report_*.xlsx` 里的 **`Recuperation Energy (kWh)`**
列（很可能 `Propulsion Energy` 同理）**覆盖稀疏、且逐段数值偏低**，导致所有读这一列的下游
（Excel 报告本身、data dashboard、旧版 PDF 简报）把再生能量占比显示成 **~4.5–8%**，而真实
值约 **19%**。

实测（YK73WFN，2.2.3，`...finetuned.xlsx`）：
- xlsx `Recuperation Energy`：495 kWh，**仅 55/115 段有值（48% 覆盖）**；60 段空白，其中
  **39 段明明有 SRF Logger 数据**却仍没算出 recup（→ 不只是缺源，是提取漏洞），另 21 段无 Logger。
- recup / |Energy Change| = **4.5%**（全队）/ 8.0%（仅覆盖段）。
- 对照 `data_analysis_workspace/energy_breakdown`（用 **raw_telematics 累积计数器** 在 trip 端点
  插值算 `E_recup`，**100% 覆盖**）：YK73 **E_recup/E_total = 19.4%**，官方汇总 `pct_recup_tot = 18.9%`。
  口径一致（两边分母都是净电池能量），19% vs 8% 的差距**纯来自 regen 这一项的数据源/覆盖**。

## 根因

xlsx 的 `Recuperation Energy`（及 `Propulsion Energy`）列用的是**稀疏的源**（Logger/事件提取，
覆盖不全、漏算），而不是 **raw_telematics 的累积再生计数器**。`energy_breakdown` 的 README 已
明确指出并刻意改用计数器：「*Energies come from raw_telematics cumulative counters … not the xlsx
Propulsion/Recuperation columns, which have poor coverage*」。

## 影响范围

- **受影响**：Excel 报告的再生列、data dashboard、以及任何直接读 xlsx recup/propulsion 列的消费者。
- **已绕过（DONE 2026-06-17）**：工业 **PDF 简报**已在 `generate-pdf-report` skill 内改用计数器口径
  （`_counter_recup`，只读 `raw_telematics` + `jolt_toolkit.analysis`）算 regen，全覆盖、正确——
  YK73 实测 495→**1,818 kWh（覆盖 107/107，~17%）**；无计数器的车（Scania/Mercedes/柴油）回退显示「—」。
  故现在**交付物间不一致**：PDF 简报 ≈正确，但 **Excel 报告 / dashboard 仍读稀疏 xlsx 列 ~5%**——
  这正是本问题待解决的剩余部分。

## 建议修复

在 `src/jolt_toolkit/`（由 `jolt-toolkit-dev` 实施）把 xlsx 的 `Recuperation Energy`
（及 `Propulsion Energy`）列改为**从 raw_telematics 累积计数器算**：
- 参考实现：`data_analysis_workspace/energy_breakdown/scripts/build_dataset.py`
  —— 用 `jolt_toolkit.analysis` 的 `build_interp / delta / to_utc` 及计数器列常量
  `COL_TOTAL / COL_PROP / COL_RECUP`，对每个 driving leg 取 `[Start, End]` 端点差值。
- 仅对**有全套计数器的 EV**（Volvo FM/FH、Renault 等 10 辆）；无计数器的车
  （Scania / Mercedes / DAF LN25NKE、柴油 WU70GLV）保持优雅 N/A。
- 这是**改动 canonical 数据** → 需车队重跑 + 版本 bump（按惯例先征得用户同意）。

## 参考

- 本次分析对话（2026-06-17）。
- `data_analysis_workspace/energy_breakdown/`（README §「Conventions & gotchas」、`scripts/build_dataset.py`）。
- `.claude/skills/generate-pdf-report/SKILL.md`（PDF 侧若改用计数器口径的边界说明）。
