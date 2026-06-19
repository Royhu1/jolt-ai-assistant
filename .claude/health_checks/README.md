# .claude/health_checks/ — 项目体检记录

由 `project-health-steward` agent（见 `../agents/project-health-steward.md`）维护，
用于跨次体检积累经验。随 `.claude/` 进 git，团队共享。

## 内容

| 文件 | 作用 |
|------|------|
| `LESSONS.md` | 累积的经验 / 项目惯例 / 易错点（去重、逐次精炼）——下次体检**先读这里** |
| `check_<YYYYMMDD>.md` | 每次体检一份报告：发现 / 处置 / 残留待办 / 未决问题 |

## 每次体检的闭环

1. 开工先读 `LESSONS.md` + 最近一份 `check_*.md` + 项目记忆。
2. 按 agent 定义里的 SOP 清单逐项体检。
3. 收尾写新的 `check_<YYYYMMDD>.md`，并把可复用经验去重追加进 `LESSONS.md`。
