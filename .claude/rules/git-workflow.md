> Git 工作流规范 —— 由根 `CLAUDE.md` 的「## git相关工作流」通过 `@import` 引用。
> 改这里 = 改全项目的 git / 版本 / changelog 约定（团队共享，随 `.claude/` 提交）。

### 版本号（仅指 `src/jolt_toolkit` 包）

版本号**只属于 `src/jolt_toolkit` 包**，维护在 `pyproject.toml` 的 `version` 字段，遵循
SemVer；项目其它模块（`data_analysis_workspace/` / `research_projects/` / `publication_workspace/` 等）不纳入此体系、不打 tag。

- `patch`（x.x.**N**）：bug 修复 / 小调整，不改接口
- `minor`（x.**N**.0）：新增功能，向后兼容
- `major`（**N**.0.0）：破坏性接口变更
- 每次版本变更同步打 git tag：`git tag vX.Y.Z`

### Commit 消息（Conventional Commits）

`feat:` 新功能 / `fix:` 修复 / `refactor:` 重构 / `docs:` 文档 / `chore:` 版本 bump、依赖等维护。
禁止无意义消息（如 "update"、"checkpoint"、"11"）。

### 分支策略

- `main` 为稳定主线，**不在 main 上直接开发**；新改动走功能分支：`feat/<描述>` / `fix/<描述>` /
  `refactor/<描述>`。
- 合并：`git checkout main && git merge <分支>`，涉及版本变更则合并后打 tag。

### 版本发布标准流程

1. 完成代码改动 → 2. 更新 `src/jolt_toolkit/README.md`（架构/字段/模块变化）→
3. 更新 `pyproject.toml` 版本号 → 4. `git commit` → 5. `git tag vX.Y.Z`。

### 不提交 git 的产物

`cache/` / `excel_report_database/` / `figures/` / `publication_workspace/` 及生成的图表与数据不提交（已在 `.gitignore`）。

### changelog（每次对话强制）

每次对话结束前更新 `changelogs/changelog_YYYYMMDD_YYYYMMDD.md`（按周 Mon–Sun 分文件，当周周一为
start、周日为 end），以 Q&A 格式记录本次对话的任务提示与完成结果摘要；存在当周文件则追加、
否则新建。
