<div align="center">

# 怯薛 · Keshig

**住在你自己 Agent 里的私人教练 —— 健身与饮食的操作系统**

[![Checks](https://github.com/LLzijian/Keshig/actions/workflows/check.yml/badge.svg?branch=main)](https://github.com/LLzijian/Keshig/actions/workflows/check.yml)
[![Version](https://img.shields.io/badge/version-0.4.0-orange)](keshig.manifest.json)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](docs/beginner-guide.md)
[![License](https://img.shields.io/badge/license-PolyForm--NC_1.0.0-orange)](LICENSE)

*An agent-native operating system for training & nutrition: methodology, records and device data live in one repo — every interaction happens in conversation, personal data never leaves your own machine.*

</div>

---

名出元制怯薛。《元史·卷九十九·兵志二·宿卫》：「其它预怯薛之职而居禁近者，分冠服、弓矢、食饮、文史、车马、庐帐、府库、医药、卜祝之事，悉世守之。」——
一个建制管多项技艺，「悉世守之」是长期。这里管四件：**吃、练、量、记**。

没有网页工作台，没有本地面板，没有云端账号。安装后新开一个对话，说「开始建立我的健身系统」，
Agent 就会建档、筛查、定计划、做复盘。仓库本身是干净的工具与知识库；你的数据留在你自己的电脑上。

## ✨ 核心设计

| 原则 | 做法 |
| --- | --- |
| **对话即界面** | 计划、复盘、营养、设备数据全部由 Agent 在对话中读写本地文件；不生成网页与面板 |
| **手记与设备分表** | `vitals`/`activity` 存「人报的」，`device_*` 存「表测的」，对照在查询里并排看，绝不静默合并 |
| **推断与实测分离** | e1RM、经验 TDEE 等推算值一律显式标注 `is_inferred`，不与实测混写 |
| **不发明口径** | 摄入与训练目标只引用 `knowledge/` 证据库与用户自己钉下的计划书 |
| **零个人数据** | 仓库不提交任何个人资料；个人系统必须位于源码与已安装 `skills/` 之外，由路径检查与 `.gitignore` 双重兜底 |
| **医疗红线** | 伤病、用药、异常体征一律「这要医生看」，不诊断、不开药 |

## 🧠 科学性引擎（v0.4.0）

- **多信号准备度自调节**：HRV、静息心率、睡眠、晨起握力对照个人 7—28 天滚动基线，绿/黄/红三级分流；单指标单日波动不独裁砍负荷（反 nocebo）。
- **容量地标审计**：单次单肌群直接组上限（防垃圾容量）、分层周有效组数（MV/MEV/MAV/MRV）、推拉结构平衡、有氧与下肢抗阻干扰预警，全部由 `validate_plan.py` 自动执行。
- **力量周期契约**：`validate_cycle.py` 硬校验多组 `首组 RPE→末组 RPE` 箭头处方、回退组联动规则、负重自重总系统负荷与真实减量周。
- **复盘守门**：`validate_review.py` 校验复盘结构，`待补全` 状态不得作为改计划的依据。
- **动态营养**：EWMA 指数平滑体重 + 14 天确认摄入反推真实 TDEE（单次调整硬限 150 kcal），体重变化速率护栏与减量周/饮食间歇联动。

## 🏗️ 结构

```
┌──────────────────────────────────────────────┐
│            Agent 对话（唯一交互界面）            │
└───────────────────┬──────────────────────────┘
                    │ tools/install.py 一键安装
        ┌───────────▼────────────┐
        │    skills/  × 10        │  建档→计划→周期→复盘→接回→营养→学习
        └──┬─────────┬─────────┬─┘
           │         │         │
  ┌────────▼───┐ ┌───▼────┐ ┌──▼───────────────┐
  │ knowledge/ │ │schema/ │ │ device/           │
  │ 方法论+证据 │ │ SQLite │ │ VitalDock 只读桥  │
  └────────────┘ └───┬────┘ └──────┬───────────┘
                     ▼             ▼
        ┌────────────────────────────────┐
        │  个人系统（源码与 skills/ 之外）   │
        │  系统/health.sqlite3            │
        │  手记表 × 设备表 → 并排对照查询   │
        └────────────────────────────────┘
```

## 📦 Skills

| Skill | 管什么 |
| --- | --- |
| `training-system` | 初始化 / 升级 / 诊断 / 校验整套系统，内置 SQLite 记录库与设备同步 |
| `fitness-plan` | 建档、安全筛查、动作选择、完整计划与容量审计 |
| `strength-cycle-planner` | 单个力量主项的 8—12 周周期与契约校验 |
| `strength-training-review` | 单次、滚动、基准与周训练复盘 |
| `training-return` | 停训、漏练、伤病或条件变化后的接回 |
| `nutrition-system` | 建档、日型宏量、餐食确认链、EWMA/TDEE 两周复盘 |
| `training-expert-library` | 六个来源限定的专家模块与路由 |
| `expert-tanchengyi` | 谭成义视角的训练判断框架（专家视角，非本人） |
| `video-learning` | 视频来源核对、转写、分段学习笔记 |
| `douyin-question-distiller` | 从短视频与图文中蒸馏问题、证据与边界 |

## 🚀 快速开始

下载 [Release 压缩包](https://github.com/LLzijian/Keshig/releases)并解压，或 `git clone` 本仓库，然后：

```bash
python tools/install.py --platform codex      # 或 claude / agents
python tools/install.py --platform codex --all --verify   # 只做漂移检查
```

也可以只把 `skills/<name>/` 复制进对应 Agent 的 skills 目录。安装与验证通过后**源码即可删除**——装上就是你的东西，个人数据不在源码里，升级时重新下载一份即可。

安装后新开一个对话，说「开始建立我的健身系统」。Agent 会先问你想把训练记录保存在哪（跟随 Agent 记忆目录 / 可见的个人文件夹 / 自定义路径），再开始建档。

默认安装全部 Skill；Codex 默认使用共享主目录 `~/.agents/skills`，保留指向该目录的已有入口联接。
个人系统必须放在源码和技能目录之外。训练与营养需要 Python 3.10+，可选设备接入需要 Python 3.11+。

## ⌚ 设备数据（可选）

`device/vitaldock_client.py` 只做一件事：把上游 VitalDock 的 CLI 输出变成结构化 JSON，落进 `device_*` 表。

```bash
python device/vitaldock_client.py setup      --root "<个人系统目录>"
python device/vitaldock_client.py selftest   --root "<个人系统目录>"   # 不联网
python device/vitaldock_client.py onboard    --root "<个人系统目录>"
python device/vitaldock_client.py activities --root "<个人系统目录>" --history-days 28
```

Agent 按[完整接入流程](skills/training-system/references/device-setup.md)引导官方授权、本机隐藏输入密钥、逐步验证和故障恢复。
**适配器不写入上游目录**，也不 import 上游源码；设备接入是可选项，不配置不影响训练与营养系统。

为什么设备值与手记分表：同一天两条来源会各说各的时长（人记 60 min vs 设备 3020 s），自动合并等于替用户裁决。对照就放在查询里并排看。

## 🗄️ 记录结构（三域统一 Schema v2）

`schema/health.sql` + `schema/device.sql` 定义三域记录库（默认位于 `<agent_root>/data/health.db` 或 `<个人系统目录>/系统/health.sqlite3`）：

- **身体域 `body_*`**：`body_vitals`（体重/体脂/围度/手记睡眠）、`body_grip`（晨起握力）与 `body_device_daily`（VitalDock 开放指标词表），通过 `v_daily_overview` 并排对照。
- **运动域 `exercise_*`**：`exercise_sessions`（训练场次）、`exercise_sets`（逐组力量：顶组/回退/工作组、RPE/RIR、总系统负荷、e1RM 推断标记）与 `exercise_device_sessions`（设备运动），通过 `v_exercise_day` 并排对照。
- **饮食域 `diet_*`**：`diet_entries`（已确认餐次）、`diet_food_est`（食物估值库）、`diet_targets`（计划书日型目标）。
- **跨域与开放扩展 `meta_*`**：每张表均带 `ext` JSON 扩展列；尚未专门建模的新数据类型直接写入 `meta_observations`（`domain` + `kind` + `value_num`/`value_text` + `unit`），无需频繁改动表结构。

## 📚 文档

- [产品定义与 Agent 职责](docs/PRODUCT.md)
- [新手搭建指南](docs/beginner-guide.md)
- [升级说明](docs/UPGRADE.md)
- [用户可见对话流程](SYSTEM-FLOW.md)
- [开发、自己使用与发布](docs/DEVELOPMENT.md)
- [验证范围](docs/VALIDATION.md)
- [贡献与仓库约定](AGENTS.md)
- [来源与许可](NOTICE.md)

## 🔒 隐私

仓库零个人数据：不提交个人资料、训练记录、照片、API key、token 或个人机器路径。
个人目录由路径检查隔离，`.gitignore` 兜底；开发者运行 `python tools/setup_dev.py` 启用提交与推送前检查。
发布包通过白名单构建。发现误提交时先移除文件，再清理 git 历史。

本地保存不等于所有处理都在本机：设备链路经过华为与 Intervals.icu；云端 Agent 可能把对话和工具结果发送给对应服务。Keshig 不提供集中收集个人资料的服务。

## 📄 许可

Keshig 采用 [PolyForm Noncommercial 1.0.0](LICENSE)：**仅限非商业使用**（个人使用、学习、研究、公益与政府机构使用均允许；商业利用不在授权范围内）。
上游材料按各自许可保留，见 [`NOTICE.md`](NOTICE.md) 与 `licenses/`。
`skills/expert-tanchengyi/` 是基于公开言论的推断框架，非本人观点、非本人授权。
训练有风险，本仓库内容不构成医疗建议。
