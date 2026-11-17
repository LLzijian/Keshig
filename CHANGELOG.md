# 更新日志

本文件记录用户可见的变化。格式参考 Keep a Changelog，遵循语义化版本；日期为 ISO 8601（YYYY-MM-DD），括号内为对应提交。

## [Unreleased]

### Added

- 文档：新增贡献指南（`CONTRIBUTING.md`）、Issue/PR 模板与更新日志（`CHANGELOG.md`）

### Changed

- 许可：改为 PolyForm Noncommercial 1.0.0，仅限非商业使用（2026-11-07，`95e02c3`）
- `video-learning`：动作库可选接入 video-reader MCP，把视频沉淀为动作条目与示范片段（2026-11-12，`df62619`）

## [0.4.0] - 2026-11-05

### Added

- SQLite 数据层闭环与多信号准备度自调节：HRV、静息心率、睡眠、晨起握力对照个人滚动基线（`716bd6d`）
- 容量地标审计、力量周期契约与复盘守门校验器、动态 TDEE（`dbb31de`）
- 三域统一 Schema v2：身体、运动、饮食、跨域记录库与查询视图
- GitHub 主页改版与版本对齐（`10381d1`）

### Changed

- 引导：数据落点先询问，源码即用即弃（`c1b6dec`）

## [0.3.1] - 2026-11-05

### Added

- 设备只读接入：VitalDock 子进程桥与双表对照
- 隐私发布检查、整包校验、安装/升级工具与 CI 基线（`6e331fb`）

## [0.1.0] - 2026-11-03

### Added

- 初始化：怯薛 Keshig——健身与饮食操作系统（`91118e2`）
