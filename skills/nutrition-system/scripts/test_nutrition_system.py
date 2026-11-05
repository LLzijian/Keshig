#!/usr/bin/env python3
"""Portable nutrition calculations, EWMA/TDEE estimation, and contract negative fixtures."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
validator_spec = importlib.util.spec_from_file_location("nutrition_validator", Path(__file__).with_name("validate_nutrition_contract.py"))
validator = importlib.util.module_from_spec(validator_spec)
assert validator_spec.loader
validator_spec.loader.exec_module(validator)


def bmr(weight: float, height: float, age: int, sex: str) -> float:
    offset = 5 if sex == "male" else -161
    return 10 * weight + 6.25 * height - 5 * age + offset


def main() -> None:
    example = json.loads((ROOT / "assets/examples/nutrition-contract.example.json").read_text(encoding="utf-8"))
    assert validator.validate(example) == []
    assert round(bmr(80, 180, 30, "male")) == 1780
    assert round(bmr(60, 165, 30, "female")) == 1320

    # EWMA bodyweight smoothing test
    ewma_series = validator.compute_ewma_weight([80.0, 80.5, 79.8, 79.5, 79.4], alpha=0.2)
    assert len(ewma_series) == 5
    assert ewma_series[0] == 80.0
    assert 79.5 <= ewma_series[-1] <= 80.1

    # Empirical TDEE back-calculation test (>=14 days & >=5 adherence days required)
    insufficient = validator.estimate_empirical_tdee(2200, -0.7, days=10, adherence_days_per_week=6)
    assert insufficient["eligible"] is False
    assert insufficient["is_inferred"] is True

    valid_tdee = validator.estimate_empirical_tdee(
        confirmed_kcal_mean=2100,
        ewma_weight_delta_kg=-0.7,
        days=14,
        adherence_days_per_week=6,
        target_daily_kcal=2400,
    )
    assert valid_tdee["eligible"] is True
    assert valid_tdee["is_inferred"] is True
    assert valid_tdee["empirical_tdee_kcal"] == 2485  # 2100 - (-0.7 * 7700 / 14 = -385)
    assert valid_tdee["recommended_adjustment_kcal"] == 150  # clamped to <=150 kcal

    # Rate guardrails test
    fast_cut = validator.evaluate_weight_rate_guardrail("fat_loss", 80.0, 77.6, days=14, strength_declining=True)
    assert fast_cut["status"] == "too_fast_deficit"
    fast_bulk = validator.evaluate_weight_rate_guardrail("muscle_gain", 70.0, 71.5, days=28)
    assert fast_bulk["status"] == "excessive_surplus"

    broken = copy.deepcopy(example)
    broken["tracking"]["confirmed_meals_only"] = False
    assert any("confirmed_nutrition" in item for item in validator.validate(broken))
    broken = copy.deepcopy(example)
    broken["review_rules"]["max_single_adjustment_kcal"] = 300
    assert any("150" in item for item in validator.validate(broken))
    broken = copy.deepcopy(example)
    broken["review_rules"]["phase_coupling"]["deload_sync"] = "starve_on_deload"
    assert any("deload_sync" in item for item in validator.validate(broken))
    print("NUTRITION_SYSTEM_TEST: PASS")


if __name__ == "__main__":
    main()
