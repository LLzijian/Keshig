## 改动概述

一两句话说明做了什么、为什么做。

## 变更类型

- [ ] Skill 能力 / 校验器
- [ ] 知识库 / 证据
- [ ] Schema / 数据迁移
- [ ] 工具 / CI
- [ ] 文档 / 示例
- [ ] `device/` 设备适配（只读）

## 涉及范围

列出改动的目录与文件；新增或删除 Skill 时说明 `keshig.manifest.json` 是否同步。

## 验证

- [ ] `python tools/validate_bundle.py` 通过
- [ ] `python tools/privacy_check.py --mode staged` 通过
- [ ] `python tools/privacy_check.py --mode history` 通过
- [ ] 新测试已登记到 `tools/validate_bundle.py` 的 `validate_tests` 清单（如有）
- [ ] 新增公开文件或目录已更新 `tools/privacy_check.py` 白名单（如有）

## 隐私与边界

- [ ] 不含个人训练/健康数据、照片、密钥、token 或个人机器路径
- [ ] 未新增网页、面板、播放器、云部署或账号体系
- [ ] `device/` 仍为只读子进程调用，未 import 或修改上游源码

## 关联 Issue

Closes #
