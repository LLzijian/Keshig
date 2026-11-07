# 记录库结构（Schema v2）

记录库按**身体 `body_*`、运动 `exercise_*`、饮食 `diet_*`、跨域 `meta_*`** 四组命名；手记（人报的）与设备（VitalDock 表测的）物理分表，并排对照只发生在视图层（`v_daily_overview`、`v_exercise_day`、`v_body_device_day`）。

## 三域一跨结构

| 域 | 手记侧（`health.sql`） | 设备侧（`device.sql`） | 并排视图 |
| --- | --- | --- | --- |
| **身体 `body`** | `body_vitals`（体重/体脂/围度/手记睡眠）、`body_grip`（晨起握力） | `body_device_daily`（开放指标词表：静息心率/睡眠/HRV/ATL/CTL 等） | `v_body_device_day`、`v_daily_overview` |
| **运动 `exercise`** | `exercise_sessions`（训练场次）、`exercise_sets`（逐组力量、RPE/RIR、e1RM） | `exercise_device_sessions`（手表运动记录） | `v_exercise_day` |
| **饮食 `diet`** | `diet_entries`（确认餐次）、`diet_food_est`（食物估值库）、`diet_targets`（计划书日型目标） | — | — |
| **跨域 `meta`** | `meta_assumptions`（口径快照）、`meta_observations`（万能扩展观测）、`meta_slots`（钉死时点）、`meta_coach_log`（沟通台账） | `meta_device_fetch`（抓取台账） | — |

## 落库与扩展通则

1. **时间戳取机器值**（落库时刻），用户不需要报钟点；用户报的时段原词存 `reported_tod`。
2. **字段全可空**（除主键与日期/运动名外），不限制记录粒度。
3. **两层无损扩展（不随手改表结构）**：
   - 已有表新增零散字段 → 写入该表 `ext` JSON 列（`CHECK (ext IS NULL OR json_valid(ext))`）；
   - 全新观测类型（如血压、臂围、主观酸痛评分） → 写入 `meta_observations(date, domain, kind, value_num, value_text, unit, ext)`；
   - 设备新数值指标 → 直接作为新 `metric` 行写入 `body_device_daily`。
4. **版本治理**：`PRAGMA user_version = 2`。旧版（v1）库由 `health_db.py` 自动备份并无损迁移至 v2。

