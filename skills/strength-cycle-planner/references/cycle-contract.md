# `cycle_contract` 专项力量周期数据协议

JSON 是 8—12 周专项力量周期的唯一结构化数据源。先用 `scripts/validate_cycle.py` 验证 JSON，再生成 Markdown 周期表；不得手写带静态多组 RPE 的表格。

## 顶层字段

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `cycle_meta` | object | 标题、版本、日期、目标动作、是否自重负重动作、周期周数（8—12）、每周暴露次数、最小加重步长 |
| `baseline_facts` | object | 基准成绩日期、已核验表现、估算 e1RM（标明 `e1rm_is_inferred: true`）、器械说明 |
| `phases` | array | 阶段划分（`accumulation` / `intensification` / `realization` / `deload`），必须覆盖第 1 至 `duration_weeks` 周且包含减量期 |
| `weeks` | array | 逐周、逐次训练暴露处方、回退规则与未完成替换分支 |
| `progression_and_adjustment_rules` | object | 顶组推进规则、回退组联动规则、多信号恢复自调节规则、提前减量触发条件 |
| `assumptions` | array | 显式标注的估算与待验证假设 |

## 核心科学校验规则（`validate_cycle.py` 强制拦截）

1. **多组工作组 RPE 箭头格式**：
   - 凡 `set_count >= 2` 的正式工作组（`work` / `backoff` / 多组 `top`），`rpe_prescription` 必须采用 **`首组 RPE→末组 RPE`**（包含 `→`，如 `首组 RPE 6.5→末组 RPE 8` 或 `@6.5→8`），且首组 RPE ≤ 末组 RPE。
   - 严禁对多组工作处方写单一静态 RPE（如 `4×6 @RPE 8`）。
2. **负重自重动作总系统负荷**：
   - 当 `cycle_meta.is_weighted_calisthenics` 为 `true` 时，必填 `baseline_bodyweight_kg`（正数），且负重处方必须同时记录 `added_weight_kg` 与 `total_system_load_kg`（等于 `baseline_bodyweight_kg + added_weight_kg`）。
3. **回退组保护与非惩罚性退行分支**：
   - `role: "backoff"` 的工作组必须提供非空 `backoff_rule`（说明顶组偏重或失手时回退组如何联动下调，禁止顶组失败后机械照做原回退重量）。
   - `fallback_branch`（未完成分支）必须声明 `is_replacement: true`，且 `replacement_set_count` 不得超过原计划组数（禁止惩罚性加组）。
4. **真实减量周（Deload）核验**：
   - `phase_type: "deload"` 的周次，总工作组数或峰值目标 RPE 必须低于前一训练周，禁止名义减量但疲劳不降。
5. **整周疲劳冲突检查（可选 `--plan <plan.json>`）**：
   - 传入关联总计划 JSON 时，自动核对 `cycle_links` 与同日高强度主项暴露冲突。
