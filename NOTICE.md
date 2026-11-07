# 来源与许可

Keshig 自有内容（README、AGENTS、device/、schema/、命名与结构改造）采用
[PolyForm Noncommercial 1.0.0](LICENSE)——**仅限非商业使用**（个人使用、学习、研究、
公益与政府机构使用均允许；销售、商业服务、商业产品集成等商业利用不在授权范围内）。
下列上游材料按各自许可保留，原文见 `licenses/`。

| 上游 | 用途 | 许可 | 在 Keshig 中的位置 |
|---|---|---|---|
| [`LZheng0411/Lzheng-fitness`](https://github.com/LZheng0411/Lzheng-fitness)（训练与营养 Skill 知识库） | 训练/营养 Skill、knowledge/、tools/、docs/ | MIT | `skills/` `knowledge/` `tools/` `docs/` |
| [`superj0107/tanchengyi-perspective`](https://github.com/superj0107/tanchengyi-perspective)（谭成义训练思维框架） | 专家视角 Skill | MIT | `skills/expert-tanchengyi/` |
| [`LLzijian/vitaldock`](https://github.com/LLzijian/vitaldock)（华为手环 → Intervals.icu 只读桥） | 设备数据来源 | 见其自身 LICENSE | **不复制**，由 `device/` 以只读子进程方式调用 |
| [`kangarooking/cangjie-skill`](https://github.com/kangarooking/cangjie-skill) | 上游仅保留许可与固定版本出处 | MIT | `third_party/cangjie/` |

## 导入基准（同步锚点）

Keshig 不是 git fork，而是对上游**快照式导入 + 改名改造**。每次同步上游后更新本表：

| 上游 | 导入的 commit | 上游日期 | 上游版本 | Keshig 导入提交 |
|---|---|---|---|---|
| Lzheng-fitness | `643958790f54a7e0a89193468bc86cd279d20dd2` | 2026-11-01 | v3.5.0（见 `docs/upstream-lzheng-changelog.md`） | `aba3155`（2026-11-02） |
| tanchengyi-perspective | `ab711ea31ce53f40dd4ef8ee2aed5331ac889889` | 2026-08-26 | — | `aba3155`（2026-11-02） |

核对方法：`gh api repos/<owner>/<repo>/git/trees/main?recursive=1` 拉上游 blob SHA，
与 `git ls-tree -r HEAD` 对比；内容相同的文件 SHA 一致，不受改名影响。

## 与上游的差异

1. **去个人色彩**：所有 `lzheng-*` / `lzheng_*` 前缀、署名式命名、个人仓库地址改为中性命名
   （如 `fitness-plan`、`training-system`、`training_system.py`）；2026-11-03 起统一品牌为 Keshig
   （环境变量 `KESHIG_FITNESS_HOME`、交接标记 `KESHIG_HANDOFF` 等）。
2. **移除个人媒体**：上游 `assets/backgrounds/` 下的动漫背景图与视频（约 24 MB）未并入。
3. **移除非商业组件**：上游 `third_party/dbs-learning/`（CC BY-NC 4.0，非商业）未并入 Keshig。
4. **移除上游 CI 与前端测试**：`.github/`、`tests/`、Playwright 配置未并入。
5. **未并入的上游说明文件**（无方法论内容，同步时不必再报差异）：`README.en.md`、`ASSET-NOTICE.md`
   `SYSTEM-FLOW.html`、`knowledge/README.md`、`integrations/cloudbase/` 下两个 README、
   4 个专家模块的 README。上游的网页工作台、视频课程页面与云部署集成属于交互与发布层，
   Keshig 不提供这些形态。
6. **新增**：`device/`（VitalDock 只读适配器）、`schema/`（记录库 DDL）、`docs/PRODUCT.md`、本 NOTICE。

## 谭成义视角的边界

`skills/expert-tanchengyi/` 是基于公开言论提炼的**推断框架**，非本人观点、非本人授权；
该 Skill 自带「诚实边界」一节（一手长访谈缺失、调研截止 2026-08-21 等），引用时一并保留。
训练有风险，界面与内容不构成医疗建议。
