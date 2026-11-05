# device · 设备数据只读接入

链路：华为运动健康 → Intervals.icu → VitalDock 公开 CLI → Keshig → Agent。

普通用户从 Keshig 开始，由 Agent 按[完整接入流程](../skills/training-system/references/device-setup.md)完成环境准备、官方授权、本机隐藏输入 key、分步检查与失败恢复。VitalDock 独立维护；Keshig 在个人系统内准备固定版本，用户不需要手工摆放两个源码目录。

```text
python device/vitaldock_client.py setup --root "<个人系统目录>"
python device/vitaldock_client.py selftest --root "<个人系统目录>"
python device/vitaldock_client.py authorize --root "<个人系统目录>"
python device/vitaldock_client.py onboard --root "<个人系统目录>"
python device/vitaldock_client.py activities --root "<个人系统目录>" --history-days 28 --limit 20
python device/vitaldock_client.py wellness --root "<个人系统目录>" --history-days 28
```

`authorize` 必须由本人在本机交互终端运行，不能把密钥发到聊天。`selftest` 不联网；`onboard` 验证连接、活动、恢复指标，只报告接入状态。退出码 `0` 表示成功，包括当前范围没有可用记录；`1` 表示失败。错误保留已知错误码和下一步，不回显上游原始错误正文或凭据。

实际代码随 `training-system/scripts/vitaldock_client.py` 安装；这里的入口转交给同一份代码。固定依赖和公开提交见 [版本记录](../skills/training-system/references/vitaldock.json)。开发者可设置 `VITALDOCK_HOME` 指向含 `.venv` 的现有检出目录，读取命令省略 `--root` 时使用；不再依赖相邻目录猜测。

适配器只通过子进程调用上游，不 import 上游源码；读取子进程禁止生成 Python 缓存，不写上游目录。`setup` 只管理个人系统的 `系统/vitaldock`，安装失败可再次执行，已有无归属标记的目录会保留。固定版本不兼容时停止读取，不追随上游主分支。

缺失数据不补零。无活动不代表没训练，无睡眠记录不代表没睡；需要检查日期、授权、设备同步和平台日历。设备值与手记分表保存并排核对，不静默合并。适配器自身不持久保存健康数值；若用户选择记录，写到个人系统的 `device_*` 表。

设备链路经过华为与 Intervals.icu；使用云端 Agent 时，工具结果可能交给对应模型服务。设备接入可跳过，不影响训练和营养系统。
