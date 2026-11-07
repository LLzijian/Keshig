# 系统契约

Keshig 是一棵纯文件树，没有网页、面板或线上发布。所有读写由 Agent 在对话中完成。

源码、安装后的 Skill 和个人系统是三个独立位置。个人系统必须位于源码和整个已安装 `skills/` 目录之外；缓存、数据库、照片、设备运行环境与备份同样如此。初始化和读取配置会检查实际路径及目录联接；正式文件写入前使用 `training_system.py check-path --path <目标>`，并先运行 `inspect` 验证个人系统内的所有输出路径。检查失败时保留文件并解释下一步，不自动移动或删除旧资料。

公开仓库与安装包不包含个人记录。使用云端 Agent 时，送入对话或工具结果的数据可能交给对应服务处理；设备路线还经过华为和 Intervals.icu。不得把本地保存记录描述成所有处理都在本机。

## 主源

- 当前训练计划：`个人训练系统/训练与周期/当前周期` 中唯一有效的版本化 JSON 与 Markdown。
- 当前执行基准：`个人训练系统/训练复盘与状态/当前执行基准`。
- 训练复盘：复盘文件及其 `INDEX.md`。
- 状态与接回：状态档案与接回卡；若状态过期，不能把旧计划当作今日处方。
- 动态训练/体重：用户本轮提供或本地统一记录库（`<agent_root>/data/health.db` 或 `<系统根目录>/系统/health.sqlite3` 中的三域手记表 `body_vitals`/`body_grip`/`exercise_sessions`/`exercise_sets`/`diet_entries`/`diet_food_est`/`diet_targets`/`meta_*` 与设备表 `body_device_daily`/`exercise_device_sessions`/`meta_device_fetch`）；缺失、过期或冲突时通过 `v_daily_overview`、`v_exercise_day` 与 `health_db.py query-context` 并排显示，不静默合并或沿用旧值。

## 正式产物归属

初始化后的系统根目录是正式产物的首选位置。除非用户本次明确指定其他交付目录，否则先读取 `系统/keshig-system.json` 的 `output_locations`，并按以下固定分区写入：

- 建档快照：`个人训练系统/训练复盘与状态/状态档案`；
- 完整计划 JSON 与 Markdown：`个人训练系统/训练与周期/当前周期`；
- 专项力量周期 JSON 与 Markdown：`个人训练系统/训练与周期/力量周期`；
- 训练复盘：`个人训练系统/训练复盘与状态/训练复盘`；
- 状态快照与接回卡：`个人训练系统/训练复盘与状态/状态档案`；
- 营养契约与记录：`个人训练系统/饮食与营养`。

临时文件、测试、缓存和备份不得混入这些正式目录。所有引用使用系统内相对路径，不得依赖固定盘符或仓库名称。

## 周切换同步

周复盘确认下一周处方后，必须在同一次更新中完成：复盘与索引 → 当前计划 `schedule` → 当前执行基准。`schedule` 需覆盖今天，训练日使用唯一 Wn，数量等于 `plan.frequency`；今天为训练日时必须存在今日处方。历史动态记录只能补充计划未指定的重量，不能覆盖明确的“自重”。任一条件失败时不得报告“已更新”，并说明缺口。

## 保护边界

用户内容包括计划、复盘、状态档案、私人知识包和外部导出。升级不得覆盖它们。系统托管文件的备份写到配置中 `backup_root`，不得在正式根目录创建版本副本。

`upgrade` 只迁移配置路径与版本号，不触碰计划、复盘与状态档案。配置迁移会把旧配置备份到 `系统/backups/config-migrations/`。

## 专家知识层

六个来源限定专家模块由 `training-expert-library` 统一承载。计划、周期、复盘和接回 Skill 可按变量读取它，但专家库不拥有当前事实、计划版本、执行基准或最终处方。升级可以更新公开蒸馏模块和登记表，不得把用户私人知识包合并进公开专家库。

## 套件配置

`系统/keshig-system.json` 使用 schema 1，最少包含 `suite_version`、`project_root`、`skills_root`、`backup_root`、`portable_config_version`、`output_locations`、`managed_files`。默认值分别为相对当前系统根目录的 `个人训练系统`、运行时标记 `@runtime` 和 `系统/backups`。`doctor`、`upgrade`、`validate` 必须先迁移旧电脑绝对路径，并在当前系统内留下可恢复的配置备份；旧路径即使仍存在，也不能覆盖当前位置的事实文件。缺失时先运行 `bootstrap` 或 `doctor`，不猜测其他机器的盘符。
