#!/usr/bin/env python3
"""Validate a Keshig strength cycle JSON file against cycle_contract rules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = (
    "cycle_meta",
    "baseline_facts",
    "phases",
    "weeks",
    "progression_and_adjustment_rules",
    "assumptions",
)

ALLOWED_PHASE_TYPES = {"accumulation", "intensification", "realization", "deload"}
ALLOWED_DUTIES = {"intensity", "volume", "technique", "variation", "deload", "verification"}
ALLOWED_ROLES = {"top", "backoff", "work", "technique"}

RPE_ARROW_RE = re.compile(
    r"(?:首组\s*)?(?:RPE\s*|@)?\s*(\d+(?:\.\d+)?)\s*→\s*(?:末组\s*)?(?:RPE\s*|@)?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
RPE_SINGLE_RE = re.compile(r"(?:RPE\s*|@)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def extract_peak_rpe(rpe_text: str) -> float | None:
    m_arrow = RPE_ARROW_RE.search(rpe_text)
    if m_arrow:
        return float(m_arrow.group(2))
    m_single = RPE_SINGLE_RE.search(rpe_text)
    if m_single:
        return float(m_single.group(1))
    return None


def validate_cycle(
    cycle: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(cycle, dict):
        return ["root value must be a JSON object"], warnings

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in cycle:
            errors.append(f"missing required top-level key: {key}")

    if errors:
        return errors, warnings

    meta = cycle["cycle_meta"]
    if not isinstance(meta, dict):
        errors.append("cycle_meta must be an object")
        return errors, warnings

    for k in ("title", "version", "created_date", "subject_mode", "subject_id", "movement", "goal_summary"):
        if not nonempty_string(meta.get(k)):
            errors.append(f"cycle_meta.{k} must be a non-empty string")

    duration_weeks = meta.get("duration_weeks")
    if not isinstance(duration_weeks, int) or isinstance(duration_weeks, bool) or not (8 <= duration_weeks <= 12):
        errors.append("cycle_meta.duration_weeks must be an integer between 8 and 12")
        duration_weeks = 0

    weekly_exposures = meta.get("weekly_exposures")
    if not isinstance(weekly_exposures, int) or isinstance(weekly_exposures, bool) or not (1 <= weekly_exposures <= 4):
        errors.append("cycle_meta.weekly_exposures must be an integer between 1 and 4")

    min_inc = meta.get("min_increment_kg")
    if not isinstance(min_inc, (int, float)) or isinstance(min_inc, bool) or min_inc <= 0:
        errors.append("cycle_meta.min_increment_kg must be a positive number")

    is_calisthenics = meta.get("is_weighted_calisthenics")
    if not isinstance(is_calisthenics, bool):
        errors.append("cycle_meta.is_weighted_calisthenics must be a boolean")
        is_calisthenics = False

    bw_kg = meta.get("baseline_bodyweight_kg")
    if is_calisthenics:
        if not isinstance(bw_kg, (int, float)) or isinstance(bw_kg, bool) or bw_kg <= 0:
            errors.append("cycle_meta.baseline_bodyweight_kg must be a positive number when is_weighted_calisthenics is true")

    baseline = cycle["baseline_facts"]
    if not isinstance(baseline, dict):
        errors.append("baseline_facts must be an object")
    else:
        for k in ("source_date", "verified_performance", "equipment_notes"):
            if not nonempty_string(baseline.get(k)):
                errors.append(f"baseline_facts.{k} must be a non-empty string")
        if baseline.get("e1rm_kg") is not None:
            if not isinstance(baseline.get("e1rm_kg"), (int, float)) or baseline.get("e1rm_kg") <= 0:
                errors.append("baseline_facts.e1rm_kg must be a positive number when provided")
            if baseline.get("e1rm_is_inferred") is not True:
                errors.append("baseline_facts.e1rm_is_inferred must be true when e1rm_kg is estimated")

    phases = cycle["phases"]
    has_deload_phase = False
    if not isinstance(phases, list) or not phases:
        errors.append("phases must be a non-empty array")
    else:
        for idx, p in enumerate(phases):
            if not isinstance(p, dict):
                errors.append(f"phases[{idx}] must be an object")
                continue
            ptype = p.get("phase_type")
            if ptype not in ALLOWED_PHASE_TYPES:
                errors.append(f"phases[{idx}].phase_type must be one of {sorted(ALLOWED_PHASE_TYPES)}")
            if ptype == "deload":
                has_deload_phase = True
        if not has_deload_phase:
            errors.append("phases must include at least one deload phase")

    weeks = cycle["weeks"]
    week_work_sets_count: dict[int, int] = {}
    week_peak_rpe: dict[int, float] = {}

    if not isinstance(weeks, list) or (duration_weeks and len(weeks) != duration_weeks):
        errors.append(f"weeks must be an array of length {duration_weeks}")
    else:
        for w_idx, w in enumerate(weeks):
            w_prefix = f"weeks[{w_idx}]"
            if not isinstance(w, dict):
                errors.append(f"{w_prefix} must be an object")
                continue
            wn = w.get("week_number")
            if wn != w_idx + 1:
                errors.append(f"{w_prefix}.week_number must equal {w_idx + 1}")
                wn = w_idx + 1
            w_ptype = w.get("phase_type")
            if w_ptype not in ALLOWED_PHASE_TYPES:
                errors.append(f"{w_prefix}.phase_type must be one of {sorted(ALLOWED_PHASE_TYPES)}")

            exposures = w.get("exposures")
            if not isinstance(exposures, list) or not exposures:
                errors.append(f"{w_prefix}.exposures must be a non-empty array")
                continue

            total_w_sets = 0
            max_w_rpe = 0.0

            for e_idx, exp in enumerate(exposures):
                e_prefix = f"{w_prefix}.exposures[{e_idx}]"
                if not isinstance(exp, dict):
                    errors.append(f"{e_prefix} must be an object")
                    continue
                if not nonempty_string(exp.get("exposure_id")) or not nonempty_string(exp.get("day_label")):
                    errors.append(f"{e_prefix} must have non-empty exposure_id and day_label")
                duty = exp.get("primary_duty")
                if duty not in ALLOWED_DUTIES:
                    errors.append(f"{e_prefix}.primary_duty must be one of {sorted(ALLOWED_DUTIES)}")

                w_sets = exp.get("work_sets")
                if not isinstance(w_sets, list) or not w_sets:
                    errors.append(f"{e_prefix}.work_sets must be a non-empty array")
                    continue

                exp_planned_sets = 0
                for s_idx, ws in enumerate(w_sets):
                    s_prefix = f"{e_prefix}.work_sets[{s_idx}]"
                    if not isinstance(ws, dict):
                        errors.append(f"{s_prefix} must be an object")
                        continue
                    role = ws.get("role")
                    if role not in ALLOWED_ROLES:
                        errors.append(f"{s_prefix}.role must be one of {sorted(ALLOWED_ROLES)}")
                    sc = ws.get("set_count")
                    if not isinstance(sc, int) or isinstance(sc, bool) or sc < 1:
                        errors.append(f"{s_prefix}.set_count must be a positive integer")
                        sc = 1
                    exp_planned_sets += sc
                    total_w_sets += sc

                    if not nonempty_string(ws.get("reps")):
                        errors.append(f"{s_prefix}.reps must be a non-empty string")

                    rpe_pres = ws.get("rpe_prescription")
                    if not nonempty_string(rpe_pres):
                        errors.append(f"{s_prefix}.rpe_prescription must be a non-empty string")
                    else:
                        if sc >= 2 and duty != "verification":
                            m_arrow = RPE_ARROW_RE.search(rpe_pres)
                            if not m_arrow:
                                errors.append(
                                    f"{s_prefix}.rpe_prescription ('{rpe_pres}') for multi-set work (set_count={sc}) must use '首组 RPE→末组 RPE' arrow format"
                                )
                            else:
                                r_start = float(m_arrow.group(1))
                                r_end = float(m_arrow.group(2))
                                if r_start > r_end:
                                    errors.append(
                                        f"{s_prefix}.rpe_prescription ('{rpe_pres}') has start RPE ({r_start}) > end RPE ({r_end})"
                                    )
                                if r_end > 9.0 and w_ptype != "realization":
                                    warnings.append(
                                        f"{s_prefix}.rpe_prescription ends at RPE {r_end} (>9.0) outside realization phase"
                                    )
                        peak_r = extract_peak_rpe(rpe_pres)
                        if peak_r is not None and peak_r > max_w_rpe:
                            max_w_rpe = peak_r

                    if role == "backoff" and not nonempty_string(ws.get("backoff_rule")):
                        errors.append(
                            f"{s_prefix} has role='backoff' but is missing a non-empty backoff_rule to prevent mechanical execution after top-set misses"
                        )

                    if is_calisthenics and isinstance(bw_kg, (int, float)):
                        added = ws.get("added_weight_kg")
                        total_sys = ws.get("total_system_load_kg")
                        if not isinstance(added, (int, float)) or not isinstance(total_sys, (int, float)):
                            errors.append(
                                f"{s_prefix} in weighted calisthenics cycle must specify numeric added_weight_kg and total_system_load_kg"
                            )
                        elif abs(float(total_sys) - (float(bw_kg) + float(added))) > 0.05:
                            errors.append(
                                f"{s_prefix}.total_system_load_kg ({total_sys}) must equal baseline_bodyweight_kg ({bw_kg}) + added_weight_kg ({added})"
                            )

                fb = exp.get("fallback_branch")
                if fb is not None:
                    if not isinstance(fb, dict):
                        errors.append(f"{e_prefix}.fallback_branch must be an object")
                    else:
                        if fb.get("is_replacement") is not True:
                            errors.append(f"{e_prefix}.fallback_branch.is_replacement must be true (replaces rather than adds sets)")
                        rep_sc = fb.get("replacement_set_count")
                        if isinstance(rep_sc, int) and rep_sc > exp_planned_sets:
                            errors.append(
                                f"{e_prefix}.fallback_branch.replacement_set_count ({rep_sc}) exceeds planned sets ({exp_planned_sets}); fallback must not be punitive"
                            )

            week_work_sets_count[wn] = total_w_sets
            week_peak_rpe[wn] = max_w_rpe

            if w_ptype == "deload" and wn > 1:
                prev_sets = week_work_sets_count.get(wn - 1, 0)
                prev_rpe = week_peak_rpe.get(wn - 1, 0.0)
                if prev_sets > 0 and total_w_sets >= prev_sets and max_w_rpe >= prev_rpe:
                    errors.append(
                        f"week {wn} is marked deload but neither work sets ({total_w_sets} vs {prev_sets}) nor peak RPE ({max_w_rpe} vs {prev_rpe}) decreased relative to week {wn - 1}"
                    )

    rules = cycle["progression_and_adjustment_rules"]
    if not isinstance(rules, dict):
        errors.append("progression_and_adjustment_rules must be an object")
    else:
        for k in ("top_set_rule", "backoff_rule", "autoreguation_readiness_rule", "deload_trigger_rule"):
            if not nonempty_string(rules.get(k)):
                errors.append(f"progression_and_adjustment_rules.{k} must be a non-empty string")

    if not isinstance(cycle["assumptions"], list):
        errors.append("assumptions must be an array")

    # Optional cross-check with fitness-plan JSON
    if isinstance(plan, dict):
        cycle_links = plan.get("cycle_links") if isinstance(plan.get("cycle_links"), list) else []
        active_movements = [
            str(c.get("movement") or "")
            for c in cycle_links
            if isinstance(c, dict) and c.get("status") == "active"
        ]
        if len(active_movements) > 2:
            warnings.append(
                f"plan has {len(active_movements)} simultaneous active strength cycles ({', '.join(active_movements)}); high systemic recovery conflict risk"
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle", type=Path, help="Path to cycle JSON file")
    parser.add_argument("--plan", type=Path, help="Optional path to fitness-plan JSON file for whole-week conflict check")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        cycle_data = json.loads(args.cycle.read_text(encoding="utf-8"))
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"valid": False, "errors": [f"failed to parse JSON: {exc}"], "warnings": []}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: failed to parse JSON: {exc}", file=sys.stderr)
        return 1

    plan_data = None
    if args.plan is not None:
        try:
            plan_data = json.loads(args.plan.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR: failed to parse --plan JSON: {exc}", file=sys.stderr)
            return 1

    errors, warnings = validate_cycle(cycle_data, plan=plan_data)
    if args.json_output:
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        for err in errors:
            print(f"ERROR: {err}")
        for warn in warnings:
            print(f"WARNING: {warn}")
        if not errors:
            print("VALID: cycle_contract checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
