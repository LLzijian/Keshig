---
name: training-system
description: 初始化、升级、诊断、校验和迁移 Keshig 本地训练系统的文件树，并把健身计划、力量周期、训练复盘、停训接回与营养系统串成单一主源。用于用户刚安装、说开始建立健身系统、新电脑搭建、系统升级或数据主源异常排查；首次使用时由 AI 自然语言接管引导，不要求用户先找 README、命令或 Skill 名称。
---

# Keshig 本地训练系统

把本 Skill 当作套件总控层：它只做安装、配置、路由、升级保护和验收；训练处方由四个训练处方 Skill 生成，营养系统独立维护 `nutrition_contract`，专家库只作为共享知识层。

本系统**不生成网页、不维护面板、不部署站点**。所有交互都在用户与 Agent 的对话中完成，磁盘上是一棵可移动的文件树。

## 共同训练判断协议

处理训练数据、RPE、下一次调整、计划渐进或失败反馈时，先读 [训练数据判断与渐进协议](references/training-progression-protocol.md)。它统一力量、增肌、减脂保肌三类目标，允许有理由的多变量联合调整；优先于旧参考中的固定单变量和机械重复规则，不覆盖本 Skill 的数据读取、正式记录及计划写入权限。未知 RPE、体感或休息不抹掉已完成组；先给能确定的分析，影响具体决定的未知再轻量核实，不循环追问用户已表示不记得的内容。

维护内置 AI 或训练 Skill 的共同决策规则时，执行该协议末尾的联动维护检查，不仅更新一端。

## 首次使用者引导

当用户刚完成安装、刚下载本套件，或第一次说“开始”“想增肌/减脂/提升力量”“帮我建立健身系统”时，不要要求用户先阅读 README、输入命令或记住 Skill 名称。直接回复：

> 我来帮你建立个人健身系统。先确定你的主要目标：增肌、减脂、力量，还是综合改善？

随后依次完成：

1. **先主动询问记录保存位置**，给出三个选项并允许用户自报路径，不要自行决定：
   - **跟随当前 Agent 的记忆/数据目录**（默认，免打理、随 Agent 配置走；例如某些 Agent 平台提供的 profile 级 memory/数据目录）——适合「装上就忘」的用户；
   - **可见的个人文件夹**（如文档库中新建「我的健身系统」）——适合想自己翻看、备份或网盘同步的用户；
   - **用户自定义路径**。
   选定后先运行 `check-path --path <目标>`，通过后才 `bootstrap`。个人系统必须位于源码与已安装的整个 `skills/` 目录之外。
2. 询问目标、近期训练、时间、器械、恢复、限制和可用记录；
3. 没有可靠动作重量时安排负荷校准，不让用户自行猜重量；
4. 在用户选定的空目录初始化系统文件树；
4. 生成第一版正式计划，写入当前周期与执行基准；
5. 告诉用户以后只需说“今天练了什么”和主观体感，AI 负责下一次明确处方。

若当前聊天尚未加载新 Skill，提示用户只需新开对话后说“开始建立我的健身系统”；不得让用户阅读 README 寻找下一步。

## 先选动作

| 用户意图 | 动作 |
| --- | --- |
| 新电脑、空文件夹、从零搭建 | `bootstrap` |
| 检查路径、数据主源、Skill 或目录是否可用 | `doctor` |
| 日常任务读取当前状态 | `inspect` |
| 升级系统配置 | `upgrade` |
| 只装/检查某个专业 Skill | `install-skill` |
| 导入用户自己的知识、书摘或资料包 | `import-private-pack` |
| 升级后或交付前做一致性校验 | `validate` |
| 日常训练任务 | 按下方路由转交专业 Skill |

运行前读取 [系统契约](references/system-contract.md)。

个人系统必须位于源码与已安装的整个 `skills/` 目录之外。首次写入前运行 `check-path --path <个人目录或输出文件>`；日常写入先运行 `inspect`，路径检查失败时停止写入。计划、照片、设备环境、缓存和备份都遵守同一边界。用户要求接入华为健康时读取 [设备接入与故障恢复](references/device-setup.md)，由本 Skill 完成引导，不让用户自行拼接两个仓库。

日常计划修改、训练复盘和状态确认先运行 `inspect`。`--root` 指向含 `系统/keshig-system.json` 的系统根目录。它只输出紧凑状态和权威主源路径；随后按任务读取对应的一个计划、基准或复盘文件。不得扫描历史计划目录、全部复盘或全部专家模块。

## 日常路由

1. 完整建档、长期训练计划、短版降级：`fitness-plan`。
2. 一个动作的 8—12 周力量周期：`strength-cycle-planner`；结果必须交回完整计划 Skill 合并后才可成为当前计划。
3. 单练或周训练复盘、下一次处方：`strength-training-review`；正式复盘写入复盘目录并更新索引。
4. 停训 7 天、连续漏练 3 次、条件明显变化：`training-return`；改变执行状态时先更新执行基准或当前计划。
5. 饮食建档、日型目标、餐食确认与两周趋势复盘：`nutrition-system`；它不按单次训练消耗补吃，也不自动确认照片估算。

四个训练处方 Skill 与营养 Skill 在需要来源限定判断时内部读取 `training-expert-library`。专家库不是独立处方入口，不拥有当前事实、计划版本或营养协议。

专业 Skill 执行前按以下优先级解析根目录：本次用户明确路径 → `系统/keshig-system.json` → 环境变量 `KESHIG_FITNESS_HOME` → 仅用于首次引导的保守默认目录。已存在系统配置时，计划、周期、复盘、状态和接回卡必须优先写入 `output_locations` 指定的分区，不得继续散落到当前工作目录。未解析到系统时停止写入并说明缺失项，不把示例数据当作训练事实。

## 命令

```bash
python scripts/training_system.py bootstrap --target "<空目录>"
python scripts/training_system.py doctor --root "<系统根目录>"
python scripts/training_system.py inspect --root "<系统根目录>"
python scripts/training_system.py upgrade --root "<系统根目录>"
python scripts/training_system.py install-skill --root "<系统根目录>" --name fitness-plan
python scripts/training_system.py import-private-pack --root "<系统根目录>" --source "<用户明确指定的目录>"
python scripts/training_system.py validate --root "<系统根目录>"
python scripts/training_system.py check-path --path "<个人目录或输出文件>"
python scripts/training_system.py db-init --root "<系统根目录>"
python scripts/health_db.py log-vitals --root "<系统根目录>" --weight-kg 75.2 --sleep-h 7.5
python scripts/health_db.py log-grip --root "<系统根目录>" --hand right --kg 52.0
python scripts/health_db.py log-workout --root "<系统根目录>" --sport 力量 --sets-json "[...]"
python scripts/health_db.py sync-device --root "<系统根目录>" --history-days 28
python scripts/health_db.py query-context --root "<系统根目录>" --days 14
```

`bootstrap` 仅接受空目录；`upgrade` 只更新配置版本与路径，发现损坏的托管文件时保留原件并报告冲突；私人知识、计划、复盘和状态档案永不覆盖。所有命令均使用 UTF-8，兼容中文、空格和非系统盘路径。

## 完成闸门

只有以下全部通过才可说本地系统可用：

- `doctor` 显示配置、六个核心 Skill、主源目录均可用；
- `validate` 通过配置与目录一致性检查；
- 在新的隔离空目录 `bootstrap` 成功，并显示“待建档”而不是假重量；
- 整套系统移动到不同盘符或改名后，旧绝对路径自动迁移，`doctor` 与 `upgrade` 继续通过。

## 一句话升级与视频学习

用户要求升级整套系统时，在已核对的官方仓库读取 `docs/UPGRADE.md`，使用 `tools/upgrade.py` 完成备份、保留记录与知识内容、更新安装 Skill。安装更新不等于线上发布。

用户要学习收藏或指定视频时，调用 `video-learning`；不同主题均可，只有健身内容按需回到本系统。私人资料放入 `健身知识库/私人知识包`，默认不参与导出。

## 当前训练记录

已有系统先运行紧凑 `inspect`，再读取当前计划、执行基准和本次相关复盘。训练记录以用户记录的事实为准；同一场次的不同来源各说各话时并排呈现，不静默合并。已记录且有实际次数的完成组即为事实，未结束场次保留原状态；未提交输入、计划值和缺失记录不能被写成已完成或未训练。实际动作替换、热身与工作组、实际休息与计划休息分别核对。

日历周与处方周遵守当前计划，不能以日期自动加重、顺移整周或补排未确认训练。正式计划、周期结构和训练事实不因工具升级而自动改变。
