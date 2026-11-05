# 华为健康接入与故障恢复

用户选择接入后，由 Agent 一步一步带到验证完成。先确认用户已建立个人系统；没有设备也能使用训练、营养和复盘。每步说明当前结果和下一步，已经完成的步骤直接验证，不重复建档或要求重新授权。

## 1. 准备设备环境

要求 Python 3.11 或以上。运行本 Skill 自带的适配器：

```text
python scripts/vitaldock_client.py setup --root <个人系统根目录>
python scripts/vitaldock_client.py selftest --root <个人系统根目录>
```

`setup` 在个人系统的 `系统/vitaldock/.venv` 安装固定版本；安装依据见同目录 `vitaldock.json`。不会安装到 Skill 或上游检出目录，不使用可编辑安装。重复执行会复用已验证版本；下载中断后可重新执行。已有无归属标记的目录会被保留并停止安装。`selftest` 不联网、不读取凭据。

开发者已安装兼容版本时，可通过 `VITALDOCK_HOME` 指定含 `.venv` 的现有检出目录；读取命令省略 `--root` 时使用它。此模式仍只通过子进程读取，不改上游文件。普通用户不需要获取或摆放第二份源码。

## 2. 注册并连接账号

1. 用户打开 [Intervals.icu 注册页](https://intervals.icu/signup)，创建自己的账号。
2. 在 [Settings → Connections](https://intervals.icu/settings/connections) 找到 HUAWEI Health 并连接；登录与授权由本人在官方页面完成。账号与地区是否可用，以实际授权结果为准。
3. 在手机华为运动健康中打开“我的 → 第三方服务”，确认 Health Service Kit 已连接。实际名称可能随版本变化。
4. 让手表或手环同步到手机，再检查 Intervals.icu 日历有没有活动。需要历史时使用连接卡片的 Download Old Data；官方说明最多回查一年。Keshig 只读，无需开启上传计划训练。

依据：[Intervals.icu 官方华为接入说明](https://www.intervals.icu/integrations/huawei/)，核对日期 2026-11-03。不要承诺手表尚未上传的数据已经可读，也不保证每日 HRV、步数等字段一定由当前适配器提供。

## 3. 本机保存个人 API key

用户在 Intervals.icu 设置底部的 Developer Settings 找到个人 API key。让本人在本机交互终端运行以下命令，隐藏输入；Agent 不索取、不代填密钥，不把它写进命令、聊天、截图或配置文件。

```text
python scripts/vitaldock_client.py authorize --root <个人系统根目录>
```

Agent 应把命令替换为实际 Python、已安装脚本和个人根目录的带引号路径，再交给用户运行。Windows 使用系统凭据管理器，macOS 使用 Keychain；Linux 需要受支持的系统密钥服务。运行授权与 Agent 时须使用同一系统用户。无交互终端时程序拒绝读取密钥；不会回退到明文文件。

这是个人用户在自己电脑上配置自己的 key；Keshig 不集中收集凭据，也不提供代管账号服务。

## 4. 分步验证

```text
python scripts/vitaldock_client.py onboard --root <个人系统根目录>
```

按顺序验证账号连接、近期活动、恢复指标；只输出各步状态，不在接入诊断里展开健康数值。报告成功必须依据 `ok: true` 与 `stage: verified`。实际读取使用 `activities` 或 `wellness` 子命令；可传 `--day YYYY-MM-DD`、`--history-days 28`、活动的 `--limit 20`，日期默认取本机当地日期。

| 结果 | 下一步 |
|---|---|
| 缺少运行环境或版本不兼容 | 运行 `setup`，再 `selftest` |
| `credential_not_configured` | 由本人在本机终端运行 `authorize` |
| `credential_unavailable` | 核对授权和 Agent 是否由同一系统用户运行 |
| `authentication_failed` | 用户重新生成 key，再本机授权 |
| `access_denied` | 核对账号与华为连接权限 |
| `network_unavailable` 或 `timeout` | 网络恢复后重试原命令，保留已有安装和授权 |
| `rate_limited` | 按返回的等待时间重试，不持续轮询 |
| `no_activities` | 连接成功但范围内没有活动；检查日期、手机同步与平台日历 |
| `no_measurements` | 范围内没有恢复观测；不补零、不推断没睡或没恢复 |
| `invalid_response` | 返回格式不兼容，停止使用本次数据并检查版本 |

失败后重新运行 `onboard` 会验证当前状态；不重新建档、不改变训练安排。只验证失败相关部分也可使用 `check`、`activities`、`wellness`。不自动修改凭据或替用户选择另一条数据路线。

## 数据去向

这条链路是华为 → Intervals.icu → 本机 VitalDock → Agent。VitalDock 的按需读取不自动建立本地健康数据库；Keshig 适配器只把结果返回对话工具，不写健康值缓存。若另行记录设备值，写入个人系统的 `device_*` 表并保留来源与读取时间，与手记分开。云端 Agent 可能把工具结果发给模型服务；授权前讲清楚这些去向。
