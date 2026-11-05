# 怯薛 · Keshig

一个住在你自己 Agent 里的私人教练：采集身体数据、记录训练与饮食、基于公开专家方法论给建议、定计划。
**训练方法、营养口径、设备数据、记录结构**四件事收在一个仓库里，
既能给 Agent 装成 Skills 用，也能作为一套可查的方法论。产品定义见 [`docs/PRODUCT.md`](docs/PRODUCT.md)。

名出元制怯薛。《元史·卷九十九·兵志二·宿卫》：「其它预怯薛之职而居禁近者，分冠服、弓矢、食饮、文史、车马、庐帐、府库、医药、卜祝之事，悉世守之。」——
一个建制管多项技艺，「悉世守之」是长期。这里管四件：**吃、练、量、记**。

所有交互都在 Agent 对话中完成：没有网页工作台、没有本地面板、没有云端账号。
仓库本身是干净的工具与知识库，个人数据留在用户自己的电脑上。

## 组成

| 目录 | 内容 |
|---|---|
| `skills/` | 10 个可安装的 Agent Skill（见下） |
| `knowledge/` | 方法论文本、证据库、训练进阶 JSON |
| `device/` | 华为手环 → Intervals.icu 的只读适配器（子进程调用，不复制上游源码） |
| `schema/` | 记录库 DDL：身体读数、运动事件、摄入、时点、目标、口径快照、设备数据 |
| `tools/` | 安装器、升级器、专家库构建、整包校验 |
| `docs/` | 产品定义、新手引导、升级说明、上游变更存档 |
| `licenses/` | 上游 MIT 许可原文 |

## Skills

| Skill | 管什么 |
|---|---|
| `training-system` | 初始化 / 升级 / 诊断 / 校验整套系统，把各 Skill 串成单一主源 |
| `fitness-plan` | 建档、安全筛查、动作选择、完整计划与 Markdown 计划书 |
| `strength-cycle-planner` | 单个力量主项的 8—12 周周期 |
| `strength-training-review` | 单次、滚动、基准与周训练复盘 |
| `training-return` | 停训、漏练、伤病或条件变化后的接回 |
| `nutrition-system` | 建档、日型宏量、餐食确认链、两周复盘 |
| `training-expert-library` | 六个来源限定的专家模块与路由 |
| `expert-tanchengyi` | 谭成义视角的训练判断框架（专家视角，非本人） |
| `video-learning` | 视频来源核对、转写、分段学习笔记 |
| `douyin-question-distiller` | 从短视频与图文中蒸馏问题、证据与边界 |

## 设备数据

`device/vitaldock_client.py` 只做一件事：把上游 VitalDock 的 CLI 输出变成结构化 JSON。

```bash
python device/vitaldock_client.py setup      --root "<个人系统目录>"
python device/vitaldock_client.py selftest   --root "<个人系统目录>"  # 不联网
python device/vitaldock_client.py onboard    --root "<个人系统目录>"
python device/vitaldock_client.py activities --root "<个人系统目录>" --history-days 28
```

Agent 按[完整接入流程](skills/training-system/references/device-setup.md)引导官方授权、本机隐藏输入密钥、逐步验证和故障恢复。普通用户不需要准备第二份源码；`setup` 在个人目录安装固定版本。开发者仍可用 `VITALDOCK_HOME` 只读连接现有检出目录。
安装后的入口为 `training-system/scripts/vitaldock_client.py`，随 Skill 分发。**适配器不写入上游目录**，也不 import 上游源码。设备接入是可选项，不配置不影响训练与营养系统。

为什么设备值与手记分表：同一天两条来源会各说各的时长（人记 60 min vs 设备 3020 s），
自动合并等于替用户裁决。对照就放在查询里并排看。

## 记录结构

`schema/health.sql` 是记录库 DDL。通则：

- 时间戳一律取落库时的机器值，不是用户输入的钟点。
- 除 `date`／`sport` 外字段一律可空（八段锦、走路这种没有设备、时长、对手）。
- 用户报的时段原词单独一列原样存（`reported_tod`），不换算、不参与判定。
- 摄入只存结构化值（kcal／蛋白／碳水／脂肪），不存原话副本。

## 安装

```bash
python tools/install.py --platform codex      # 或 claude / agents
python tools/install.py --platform codex --all --verify   # 只做漂移检查
```

安装后新开一个对话，说「开始建立我的健身系统」。也可以只把 `skills/<name>/` 复制进对应 Agent 的 skills 目录。

默认安装全部 Skill；Codex 默认使用共享主目录 `~/.agents/skills`，保留指向该目录的已有入口联接。个人系统必须放在源码和技能目录之外。训练与营养需要 Python 3.10+，可选设备接入需要 Python 3.11+。

## 文档

- [产品定义与 Agent 职责](docs/PRODUCT.md)
- [新手搭建指南](docs/beginner-guide.md)
- [升级说明](docs/UPGRADE.md)
- [用户可见对话流程](SYSTEM-FLOW.md)
- [来源与许可](NOTICE.md)
- [开发、自己使用与发布](docs/DEVELOPMENT.md)
- [验证范围](docs/VALIDATION.md)

## 隐私

仓库零个人数据：不提交个人资料、训练记录、照片、API key、token 或个人机器路径。
个人目录由路径检查隔离，`.gitignore` 兜底；开发者运行 `python tools/setup_dev.py` 启用提交与推送前检查。发布包通过白名单构建，规则检查不能识别任意文字中的个人信息。
发现误提交时先移除文件，再清理 git 历史。

本地保存不等于所有处理都在本机：设备链路经过华为与 Intervals.icu；云端 Agent 可能把对话和工具结果发送给对应服务。Keshig 不提供集中收集个人资料的服务。

## 许可

Keshig MIT。上游材料按各自许可保留，见 [`NOTICE.md`](NOTICE.md) 与 `licenses/`。
`skills/expert-tanchengyi/` 是基于公开言论的推断框架，非本人观点、非本人授权。
训练有风险，本仓库内容不构成医疗建议。
