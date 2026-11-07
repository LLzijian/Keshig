# AGENTS.md

给在本仓库工作的 Agent 的约定。

## 这个仓库是什么

怯薛（Keshig）是一套**健身与饮食的操作系统**，由三部分组成：

1. `skills/` — 10 个可安装的 Agent Skills：建档、计划、力量周期、训练复盘、停训接回、营养系统、视频学习、专家视角。
2. `knowledge/` — 方法论文本与证据库，Skill 引用它，不重复造。
3. `device/` + `schema/` — 设备数据只读接入与记录库结构。

所有交互都在 Agent 对话中完成。仓库不提供网页、面板、播放器或云端发布；
新增能力应做成 Skill、知识或适配器，而不是交互界面。

## 硬约束

- **`device/` 对上游设备桥（VitalDock）只读**：只 `subprocess` 调它的 CLI、读 stdout JSON；
  不 import 其源码、不写其目录、不改其文件。改动方向只能是适配器，不是上游。
- **不把设备值与手记合并成一张表**：`body_vitals`/`body_grip`/`exercise_sessions`/`exercise_sets`/`diet_*` 存「人报的」，`body_device_daily`/`exercise_device_sessions` 存「表测的」，
  两者各说各话，对照放在查询视图（`v_daily_overview`、`v_exercise_day`）里并排看。
- **不发明口径**：摄入与训练目标一律引用 `knowledge/` 与用户自己钉下的计划书，
  缺口径就问，不拿通用表格冒充用户口径。
- **推断与实测分开写**：推断必须标明。
- **不复述用户原话**：只存结构化后的值；原话的权威副本在用户自己的笔记系统里。
- 医疗红线：伤病、用药、异常体征 → 只说「这要医生看」，不诊断、不开药。
- **仓库零个人数据**：不提交任何个人资料、训练记录、照片、密钥、token、个人机器路径；
  个人数据落点由 `.gitignore` 兜底，新增数据落点先进 `.gitignore` 再写代码。
  产品定义与数据边界见 `docs/PRODUCT.md`。
- **开发与自己使用分开**：个人系统、缓存、数据库、照片、设备环境和备份必须位于源码及整个已安装 `skills/` 目录之外。运行时先检查实际路径，公开测试只用独立构造的虚构数据。开发者用 `tools/setup_dev.py` 启用本地提交与推送检查，发布用 `tools/build_release.py` 的白名单打包；详见 `docs/DEVELOPMENT.md`。
- **不做交互层**：不新增网页工作台、桌面面板、视频播放器、云端部署或账号体系；
  计划、复盘、营养与设备数据都通过 Skill 在对话中读写本地文件。

## 命名

新增 Skill 用中性功能名（`fitness-plan`、`nutrition-system` 这种），
不用人名、项目人名缩写或团队前缀。目录名与 `SKILL.md` 的 `name:` 必须一致。
