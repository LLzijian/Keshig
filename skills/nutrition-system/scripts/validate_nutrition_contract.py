#!/usr/bin/env python3
"""Validate a portable nutrition_contract and compute EWMA / empirical TDEE adjustments."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REQUIRED = ("meta", "profile", "calculation", "day_type_rules", "tracking", "review_rules", "sources")
DAY_TYPES = ("heavy_training", "normal_training", "rest", "needs_confirmation")
GOALS = ("fat_loss", "maintenance", "muscle_gain")
ALLOWED_DELOAD_SYNC = ("maintenance_calories_keep_protein_fat", "keep_current_target", "needs_confirmation")


def compute_ewma_weight(weights: list[float], alpha: float = 0.2) -> list[float]:
    """Compute Exponentially Weighted Moving Average (EWMA) for bodyweight series."""
    if not weights:
        return []
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha must be in (0, 1]")
    smoothed: list[float] = []
    curr = float(weights[0])
    for w in weights:
        curr = alpha * float(w) + (1.0 - alpha) * curr
        smoothed.append(round(curr, 2))
    return smoothed


def estimate_empirical_tdee(
    confirmed_kcal_mean: float,
    ewma_weight_delta_kg: float,
    days: int = 14,
    adherence_days_per_week: float = 7.0,
    target_daily_kcal: float | None = None,
    max_single_adjustment_kcal: int = 150,
) -> dict[str, Any]:
    """Back-calculate empirical TDEE from confirmed intake and EWMA weight change over >=14 days."""
    if days < 14 or adherence_days_per_week < 5.0:
        return {
            "eligible": False,
            "is_inferred": True,
            "reason": "观察天数不足 14 天或周均确认记录不足 5 天，暂不依据短期波动反推 TDEE",
            "empirical_tdee_kcal": None,
            "recommended_adjustment_kcal": 0,
        }
    daily_surplus_kcal = (float(ewma_weight_delta_kg) * 7700.0) / float(days)
    empirical_tdee = round(float(confirmed_kcal_mean) - daily_surplus_kcal)
    rec_adj = 0
    if target_daily_kcal is not None:
        raw_diff = round(float(target_daily_kcal) - float(confirmed_kcal_mean))
        limit = min(int(max_single_adjustment_kcal), 150)
        rec_adj = max(-limit, min(limit, raw_diff))
    return {
        "eligible": True,
        "is_inferred": True,
        "days": days,
        "daily_energy_balance_kcal": round(daily_surplus_kcal),
        "empirical_tdee_kcal": empirical_tdee,
        "recommended_adjustment_kcal": rec_adj,
    }


def evaluate_weight_rate_guardrail(
    goal: str,
    start_ewma_kg: float,
    end_ewma_kg: float,
    days: int,
    *,
    strength_declining: bool = False,
) -> dict[str, Any]:
    """Check whether EWMA bodyweight change rate stays within safe hypertrophy/fat-loss guardrails."""
    if days <= 0 or start_ewma_kg <= 0:
        return {"status": "insufficient_data", "is_inferred": True}
    delta_kg = float(end_ewma_kg) - float(start_ewma_kg)
    weekly_pct = (delta_kg / float(start_ewma_kg)) * (7.0 / float(days)) * 100.0
    monthly_pct = (delta_kg / float(start_ewma_kg)) * (30.0 / float(days)) * 100.0

    status = "within_guardrail"
    action = "维持当前方案并继续观察"
    if goal == "fat_loss":
        if weekly_pct < -1.0 or (weekly_pct < -0.7 and strength_declining):
            status = "too_fast_deficit"
            action = "减重速率快于 -1.0% 体重/周或伴随力量下滑，建议在 <=150 kcal 上限内上调热量（优先补碳水）"
        elif weekly_pct > -0.25 and days >= 14:
            status = "stalled_loss"
            action = "14 天 EWMA 降幅慢于 -0.25% 体重/周，核对确认入账完整性后可在 <=150 kcal 内小幅下调"
    elif goal == "muscle_gain":
        if monthly_pct > 1.5:
            status = "excessive_surplus"
            action = "月增重速率快于 +1.5% 体重/月，建议在 <=150 kcal 内收窄热量盈余以防脂肪堆积过快"
        elif monthly_pct < 0.3 and days >= 14:
            status = "under_gaining"
            action = "月增重速率慢于 +0.3% 体重/月，可在 <=150 kcal 内小幅上调碳水支持训练表现"

    return {
        "status": status,
        "is_inferred": True,
        "weekly_pct": round(weekly_pct, 2),
        "monthly_pct": round(monthly_pct, 2),
        "recommended_action": action,
    }


def validate(value: dict) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != 2:
        errors.append("schema_version 必须为 2")
    for key in REQUIRED:
        if key not in value:
            errors.append("缺少字段: " + key)
    if errors:
        return errors

    meta = value["meta"]
    profile = value["profile"]
    calculation = value["calculation"]
    review = value["review_rules"]
    if meta.get("goal") not in GOALS:
        errors.append("meta.goal 必须是 fat_loss / maintenance / muscle_gain")
    if meta.get("status") not in ("awaiting_profile", "active", "needs_review"):
        errors.append("meta.status 不受支持")

    age = profile.get("age")
    if age is not None and not (18 <= age <= 100):
        errors.append("age 必须为 18–100 或 null")
    sex = profile.get("sex")
    if sex is not None and sex not in ("male", "female"):
        errors.append("sex 必须为 male / female 或 null")
    for key, low, high in (("height_cm", 120, 230), ("current_weight_kg", 35, 300)):
        number = profile.get(key)
        if number is not None and not (low <= number <= high):
            errors.append(f"{key} 超出可接受范围")

    if meta.get("status") == "active":
        for key in ("age", "sex", "height_cm", "current_weight_kg"):
            if profile.get(key) is None:
                errors.append("active 协议缺少 profile." + key)
        for key in ("activity_factor", "protein_g_per_kg", "fat_g_per_kg"):
            if calculation.get(key) is None:
                errors.append("active 协议缺少 calculation." + key)
    if calculation.get("minimum_observation_days", 0) < 14:
        errors.append("minimum_observation_days 不得少于 14")
    if abs(float(calculation.get("energy_adjustment_percent") or 0)) > 0.3:
        errors.append("energy_adjustment_percent 绝对值不得超过 0.30")

    rules = value["day_type_rules"]
    for day_type in DAY_TYPES:
        if day_type not in rules or not isinstance(rules[day_type].get("match"), list):
            errors.append("缺少日型规则: " + day_type)
    if review.get("minimum_days", 0) < 14:
        errors.append("review_rules.minimum_days 不得少于 14")
    if review.get("minimum_adherence_days_per_week", 0) < 5:
        errors.append("执行不足 5/7 天时不得自动调热量")
    if review.get("max_single_adjustment_kcal", 999) > 150:
        errors.append("单次调整不得超过 150 kcal")

    ewma_alpha = review.get("ewma_alpha")
    if ewma_alpha is not None and (not isinstance(ewma_alpha, (int, float)) or not (0.05 <= float(ewma_alpha) <= 0.5)):
        errors.append("review_rules.ewma_alpha 必须在 0.05–0.50 之间")

    guardrails = review.get("rate_guardrails")
    if guardrails is not None:
        if not isinstance(guardrails, dict):
            errors.append("review_rules.rate_guardrails 必须为对象")
        else:
            fl_range = guardrails.get("fat_loss_weekly_pct_range")
            if fl_range is not None:
                if (
                    not isinstance(fl_range, list)
                    or len(fl_range) != 2
                    or float(fl_range[0]) < -1.5
                    or float(fl_range[1]) > 0.0
                    or float(fl_range[0]) >= float(fl_range[1])
                ):
                    errors.append("rate_guardrails.fat_loss_weekly_pct_range 必须为合理的负数区间（如 [-1.0, -0.3]）")
            mg_range = guardrails.get("muscle_gain_monthly_pct_range")
            if mg_range is not None:
                if (
                    not isinstance(mg_range, list)
                    or len(mg_range) != 2
                    or float(mg_range[0]) < 0.0
                    or float(mg_range[1]) > 2.5
                    or float(mg_range[0]) >= float(mg_range[1])
                ):
                    errors.append("rate_guardrails.muscle_gain_monthly_pct_range 必须为合理的正数区间（如 [0.5, 1.5]）")

    coupling = review.get("phase_coupling")
    if coupling is not None:
        if not isinstance(coupling, dict):
            errors.append("review_rules.phase_coupling 必须为对象")
        else:
            ds = coupling.get("deload_sync")
            if ds is not None and ds not in ALLOWED_DELOAD_SYNC:
                errors.append(f"phase_coupling.deload_sync 必须为 {ALLOWED_DELOAD_SYNC}")
            db_weeks = coupling.get("diet_break_interval_weeks")
            if db_weeks is not None and (not isinstance(db_weeks, int) or not (6 <= db_weeks <= 16)):
                errors.append("phase_coupling.diet_break_interval_weeks 必须为 6–16 周整数")

    if value["tracking"].get("confirmed_meals_only") is not True:
        errors.append("日合计必须只读取 confirmed_nutrition")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_nutrition_contract.py <contract.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    value = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(value)
    if errors:
        print("NUTRITION_CONTRACT: FAIL")
        for error in errors:
            print("- " + error)
        return 1
    print("NUTRITION_CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
