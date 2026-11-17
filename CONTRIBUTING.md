# 贡献指南

感谢参与。这个仓库是**健身与饮食的操作系统**：方法论、记录结构与设备适配都在这里，交互全部通过 Agent 对话完成。提交前请先读 [AGENTS.md](AGENTS.md)——那是比本文档更硬的约定。

## 适合贡献的改动

- Skill 能力与校验器：新增功能、补校验规则、补测试
- 知识库：方法论整理、证据登记、来源核对
- 工具与 CI：安装、升级、校验、隐私发布流程的健壮性
- 文档、示例与翻译
- `device/` 适配器：在只读边界内增强设备数据接入

不适合的改动：网页、面板、播放器、云部署、账号体系——见 [AGENTS.md](AGENTS.md) 的「不做交互层」。

## 提交前必须遵守

1. **零个人数据**：不提交个人资料、训练记录、照片、数据库、API key、token 或个人机器路径。个人系统必须位于源码和已安装 `skills/` 之外；本地检查命令见下文。
2. **`device/` 只读**：只通过 `subprocess` 调上游 VitalDock CLI、读 stdout JSON；不 import 上游源码、不写上游目录、不改上游文件。
3. **不发明口径**：摄入与训练目标引用 `knowledge/` 与用户自己钉下的计划书；不确定就问，不拿通用表格冒充用户口径。
4. **推断与实测分开写**：e1RM、经验 TDEE 等推算值必须显式标注（如 `is_inferred`），不与实测混写。
5. **医疗红线**：伤病、用药、异常体征只提示「这要医生看」，不诊断、不开药。
6. **许可**：本仓库使用 [PolyForm Noncommercial 1.0.0](LICENSE)，仅限非商业使用；提交内容默认以同一许可发布。上游材料按各自许可保留，见 [NOTICE.md](NOTICE.md)。

## 开始开发

要求：Python 3.10+（设备接入相关 3.11+）；Windows、macOS、Linux 均可。工具与校验器当前只依赖 Python 标准库；确需新增第三方依赖时，请在 PR 中说明理由与版本约束。

```text
git clone https://github.com/LLzijian/Keshig.git
cd Keshig
python tools/setup_dev.py
```

`tools/setup_dev.py` 只为当前仓库启用 `.githooks` 并记录 Python 路径；已有自定义 hooks 时保留原设置、不会覆盖。hooks 是本地保护，可被 `--no-verify` 或改配置绕过，不能替代人工检查。

## 修改后验证

```text
python tools/validate_bundle.py
python tools/privacy_check.py --mode staged
python tools/privacy_check.py --mode history
```

- `tools/validate_bundle.py`：清单、Skill front matter、本地链接、隐私边界、测试与临时目录安装全链路；
- `tools/privacy_check.py`：发布候选文件检查；`staged` 查暂存区，`history` 查全部可达历史；
- CI 跑 Windows 与 Ubuntu × Python 3.10/3.12（见 [.github/workflows/check.yml](.github/workflows/check.yml)）；macOS 与更新版本目前需本地自测。

## 目录与改动落点

| 路径 | 放什么 | 改动注意 |
|---|---|---|
| [`skills/`](skills/) | 10 个可安装 Skill | 目录名 = `SKILL.md` front matter 的 `name`；新增或删除 Skill 要同步 [`keshig.manifest.json`](keshig.manifest.json) |
| [`knowledge/`](knowledge/) | 方法论文本与证据库 | 结论要有来源登记；不要复制 Skill 里的内容再改 |
| [`schema/`](schema/) | SQLite 记录结构 | 改表先写迁移路径，旧库不丢数据 |
| [`device/`](device/) | VitalDock 只读桥 | 只读、子进程、不碰上游 |
| [`tools/`](tools/) | 安装、升级、校验、发布工具 | 改动需配测试；新增公开文件或目录先更新隐私白名单 |
| [`docs/`](docs/) | 用户与开发者文档 | 面向读者写，不写临时口径 |
| [`examples/`](examples/) | 虚构示例数据 | 只用独立构造的虚构数据 |
| [`.github/`](.github/) | CI 与贡献模板 | 改 CI 需同时覆盖 Windows 与 Ubuntu |

## 新增或修改 Skill

1. 目录名与 `SKILL.md` front matter 的 `name` 必须一致，用中性功能名（不用人名或项目前缀）；
2. 方法论引用 `knowledge/` 或专家库 `references/`，不要复制一份再改；
3. 输入输出契约写清楚（字段、状态、JSON 结构），便于校验器检查；
4. 加校验器或测试：`validate_*.py` / `test_*.py`，并登记到 `tools/validate_bundle.py` 的 `validate_tests` 清单；
5. 在 `keshig.manifest.json` 的 `skills` 数组登记 `name` 与 `path`；
6. 跑一遍 `python tools/validate_bundle.py`，确认全部 Skill 通过。

## 修改知识库

- 新增来源先登记到 [knowledge/06-source-register.md](knowledge/06-source-register.md)；
- 推断与实测分写，结论要能追溯到来源；
- 不把通用建议写成用户没有确认过的处方；
- 涉及健康结论时遵守 [knowledge/01-safety-and-scope.md](knowledge/01-safety-and-scope.md)。

## 修改 Schema

- 同时改 `schema/health.sql`（及需要时 `schema/device.sql`）和相关文档、查询视图；
- 旧库通过 `health_db.py migrate` 路径升级，迁移前自动备份；
- 不把「人报的」与「表测的」合并成一张表，对照放在查询视图里；
- 新数据类型优先进 `meta_observations` 或各表的 `ext` JSON，避免频繁改表。

## 隐私自查

- 不提交个人健康数据；测试与示例只用虚构资料；
- 不要在源码目录做真实使用；个人落点由 `KESHIG_FITNESS_HOME` 或本机系统配置指定；
- 误提交时：先移除文件、清理历史，并联系维护者——不要只删当前版本就继续推送。

## 提交与 PR

- 分支命名：`feat/<简述>`、`fix/<简述>`、`docs/<简述>`、`chore/<简述>`；
- 提交信息动词开头并注明范围，如 `docs: 补贡献指南与更新日志`；
- 一次 PR 只做一件事；改 Skill 时附上校验输出；
- 默认走 PR：说明动机、改动范围、验证命令与结果；CI 会复核；
- 提交作者身份使用你自己的 GitHub 账号与已验证邮箱。

## 提 Issue

Bug 报告或功能建议请用对应模板，说明环境（操作系统、Python 版本）、复现步骤与期望结果；不要贴真实健康数据，必要时用虚构例子替代。
