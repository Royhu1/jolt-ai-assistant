# pending_issues/ — 待处理问题登记

存放**已知、已分析、但当下不立即修复**的问题（deferred issues）：每个问题一个 Markdown 文件，
本 README 是索引。目的是不让「先记录、之后再解决」的问题丢失。

## 约定

- 一问题一文件，文件名 `NNN_<kebab-描述>.md`（NNN 递增编号）。
- 每个问题文件包含：**状态 / 发现日期 / 摘要 / 根因 / 影响范围 / 建议修复 / 负责方 / 参考**。
- 状态：`OPEN`（待办）/ `IN PROGRESS` / `RESOLVED`（解决后在文件顶部标注解决日期与去向，并从下表移除或划掉）。
- 解决一个问题时：更新该文件状态，并在下方索引表里更新。

## 索引

| # | 问题 | 状态 | 负责方 |
|---|------|------|--------|
| 001 | [Excel 报告 / dashboard 的 regen（再生）能量被低估到 ~5%（应 ~19%）](001_xlsx_regen_propulsion_undercounted.md) | OPEN | jolt-toolkit-dev |
