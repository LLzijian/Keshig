# device · 设备数据只读接入

华手环的数据链路是：

```
华为运动健康 → Intervals.icu（本人 API key，存 Windows 凭据管理器）
             → 上游 VitalDock 的只读 CLI → 本适配器 → 结构化 JSON / 记录库
```

## 为什么是适配器，不是合并

上游 VitalDock 是一个独立维护的项目。把它整包搬进来会带来两个问题：版本耦合（它升级，
我们要跟着改）和写权限扩散（它的目录里躺着凭据与缓存）。

所以本仓库**只放适配器**：

- 只 `subprocess` 调上游 CLI，读 stdout；
- 不 `import` 上游源码；
- 不写上游目录、不改上游文件（`selftest` 会查一次 `git status --porcelain` 作为证据）。

## 用法

```bash
python device/vitaldock_client.py selftest
python device/vitaldock_client.py check      --day 2026-11-02
python device/vitaldock_client.py wellness   --day 2026-11-02 --history-days 28
python device/vitaldock_client.py activities --day 2026-11-02 --history-days 28 --limit 100
```

上游路径用 `VITALDOCK_HOME` 指定；未设置时自动探测本仓库同级目录下的 `vitaldock/`、`VitalDock/`、`BioDeviceData/`（按序，取第一个存在的）。

退出码：`0` 成功（含「当天无记录」）；`1` 上游失败（stdout 里是 JSON 错误体）；`2` 找不到上游 venv。

## 上游错误码（原样透传，不改写）

`authentication_failed`／`credential_not_configured`／`credential_unavailable`／
`rate_limited`（带 `retry_after_seconds`）／`network_unavailable`／`wellness_not_granted`。

## 两条落库纪律

1. **缺失不补零**：某天没有睡眠就是没有，不写 0；`today_present=false` 是「还没同步」，不是「没睡」。
2. **设备值不并进手记表**：`vitals`／`activity` 存人报的，`device_*` 存表测的。
   同一天两条来源会各说各的时长，自动合并等于替用户裁决。对照放在查询里并排看。
