> 整洁与本地存储规范 —— 由根 `CLAUDE.md` 的「## Housekeeping & Local Storage」通过 `@import` 引用。
> 改这里 = 改全项目的临时文件清理 / 归档 / 本地存储约定（团队共享，随 `.claude/` 提交）。

> 本文件管**项目整洁与文件落位**：临时 / 过时文件往哪清、往哪归档，以及哪些文件该留在
> 本地磁盘而非 OneDrive。Python 标识符 / 一次性脚本命名见 `code-style.md`；数据 / 产物 /
> 目录命名见 `naming.md`；分支 / commit / changelog 见 `git-workflow.md`。

### 临时文件：分区与清理

| 区域 | 用途 | 进 git | 清理策略 |
|------|------|--------|---------|
| `tmp/` | 一次性 scratch（日志 / 中间 CSV / 调试图 / `_tmp_*.py`） | 否 | 用完即清；体检时整目录归档到本地 `scratch_archive/`（move，非删除） |
| `cache/` | SRF / 天气等 API 缓存 | 否 | **不要轻易清**——重建昂贵且有 API 配额；至多清根目录游离测试文件 |
| `archive/` | 回收站：被取代 / 退役的产物 | 否 | 只进不出；体检产生的根级 scratch 落到 `archive/root_scratch_<YYYYMMDD>/` |
| `unarchived/` | 尚未归位的「持有区」 | 否 | 定期 triage：要么归位到蓝图目录，要么退役进 `archive/` |

- **仓库根目录保持干净**：禁止把一次性脚本 / 日志直接丢在根目录；它们属于 `tmp/`，
  或体检时移入 `archive/root_scratch_<YYYYMMDD>/`。已 gitignore 的根级 scratch 也应物理移走，
  不只靠 gitignore 掩盖。
- **优先归档而非删除**：清理用 `Move-Item` 到 `archive/` 或本地 `scratch_archive/`，保留可追溯性；
  确属可重现废弃物再删。（注：sandbox 会拦截对顶层 / 受保护路径的 `Remove-Item`，move 更稳妥。）
- **OneDrive 注意**：清理 / 重生 xlsx 前先关 Excel（锁文件会让 move 失败）；大体量 scratch
  归档到本地盘可顺带减轻 OneDrive 同步负担。

### 本地存储：OneDrive vs 本地盘

仓库本体在 OneDrive 下随云同步。**需要留在本地、不该上云**的 JOLT 文件统一收敛到本地根
**`D:\JOLT_local\`**（机器本地、不进 git、不上 OneDrive）：

| 子目录 | 放什么 |
|--------|--------|
| `git_backups/` | 旧仓库 / bare `.git` 历史备份（如 clean-rebuild 时的快照） |
| `scratch_archive/` | 从仓库 `tmp/` 或 D 盘各处归档来的 scratch（按来源分子目录：`repo_tmp_<日期>` / `D_temp` …） |
| `<service>/` | 本地服务 / 大体量数据（如本地路由引擎、OSM extract），按需另设 |

- 选本地盘的判据：**大体量、可重建、机器本地、或不宜上云**（备份、缓存快照、路由数据等）。
  真正的项目源码 / 文档仍留在仓库内、随 git 与 OneDrive 走。
- 不要把 JOLT 残余散落在 `D:\temp` / `D:\tmp` / `D:\` 根等随手位置——统一收敛到 `D:\JOLT_local\`。

> 本规范的执行与定期体检由 `project-health-steward` agent（见 `.claude/agents/`）负责，
> 每次体检记录留存在 `.claude/health_checks/`，经验逐次累积。
