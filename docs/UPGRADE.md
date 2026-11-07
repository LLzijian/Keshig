# 让 Agent 帮你升级

源码仓库只是运输包装：升级就是重新下载一份最新源码（Release 压缩包或 `git clone`），跑一遍安装器覆盖 Skill，再对个人系统执行 `upgrade`；完成后这份源码同样可以删除。你的全部数据都在个人系统目录里，不在源码中。

对你的 Agent 说：

```text
帮我升级健身系统，保留我的计划、复盘、状态档案、营养记录和私人知识包。
```

Agent 先确认官方发布版本与本地改动，不要覆盖用户自己改过的仓库。然后在 Keshig 仓库运行：

```bash
python tools/upgrade.py --root <用户系统目录> --platform codex
```

不带 `--apply` 只做兼容性检查；用户确认后再加 `--apply`：

```bash
python tools/upgrade.py --root <用户系统目录> --platform codex --apply
```

Claude Code 用 `--platform claude`，其他兼容 Agent 用 `agents`；需要指定安装位置时传 `--agent-root`。

Codex 默认使用共享的 `~/.agents/skills`。已有指向该主目录的 Codex/Claude 入口联接会保留；自定义 `CODEX_HOME` 仍有效，任意其他目录联接仍拒绝安装。0.3.1 开始要求个人系统位于源码和技能目录之外；发现旧数据位于这些目录时先保留原件，制定单独的迁移方案，不自动移动或删除。

0.4.0 起，个人系统采用三域统一记录库 Schema v2（身体 `body_*`、运动 `exercise_*`、饮食 `diet_*`、跨域 `meta_*`，默认位于 `<agent_root>/data/health.db` 或 `<个人系统>/系统/health.sqlite3`）。`bootstrap` 自动建库或接管已有 `health.db`；旧版（v1）数据库运行 `upgrade` 或 `health_db.py migrate` 时会自动先备份至 `backups/` 再无损迁移表名与 `ext` 扩展列，不丢失任何既有记录。

## 升级会做什么

1. 对系统目录运行 `validate`，先确认配置与目录结构可迁移；
2. 运行 `upgrade`：只迁移 `系统/keshig-system.json` 的路径与版本号，旧配置备份到 `系统/backups/config-migrations/`；
3. 用安装器更新已安装的 Skills，覆盖前把旧版本备份到 Agent 根目录下的 `.fitness/backups/`；
4. 再运行一次 `--verify`，输出 `KESHIG_FITNESS_VERIFY: PASS` 才算完成。

## 升级不会做什么

- 不覆盖用户计划、复盘、状态档案、执行基准、营养记录和私人知识包；
- 不重新制定计划，不导入学习示例；
- 不修改上游 VitalDock 的目录；
- 不部署网站，不上传任何个人数据。

## 迁移到新电脑

整套目录一起复制，不要只拿一个计划文件。到新电脑后：

1. 安装 Python 与本地 Agent；
2. 重新安装最新 Skills；
3. 对复制后的系统目录运行 `doctor`；
4. 运行 `upgrade --apply`，把旧电脑的绝对路径迁移到当前位置；
5. 再用 `validate` 核对，并读取当前计划、执行基准和最近一次复盘。

目录换盘符、改名字、放进带中文和空格的路径都可以；系统内部只使用相对路径。

## 出问题时

把「Agent 说了什么、你期望什么、哪个文件不对」交给 Agent，让它只改受影响的部分，并保留原有记录。不要在系统目录里手工制造版本副本；需要备份时使用 `backup_root` 指定的位置。
