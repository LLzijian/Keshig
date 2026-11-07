#!/usr/bin/env python3
"""Integration tests for health_db, readiness autoregulation, and scientific plan/cycle/review validators."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_DB_SCRIPT = REPO_ROOT / "skills" / "training-system" / "scripts" / "health_db.py"
TRAINING_SYSTEM_SCRIPT = REPO_ROOT / "skills" / "training-system" / "scripts" / "training_system.py"
VALIDATE_PLAN_SCRIPT = REPO_ROOT / "skills" / "fitness-plan" / "scripts" / "validate_plan.py"
VALIDATE_CYCLE_SCRIPT = REPO_ROOT / "skills" / "strength-cycle-planner" / "scripts" / "validate_cycle.py"
VALIDATE_REVIEW_SCRIPT = REPO_ROOT / "skills" / "strength-training-review" / "scripts" / "validate_review.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def make_wellness(day: str, *, resting_hr: float, sleep_h: float, hrv: float) -> dict:
    return {
        "ok": True,
        "status": "success",
        "source": "garmin",
        "records": [
            {
                "date": day,
                "resting_hr": resting_hr,
                "sleep_secs": int(sleep_h * 3600),
                "sleep_score": 84,
                "hrv": hrv,
                "ctl": 42.0,
                "atl": 44.0,
            }
        ],
    }


def test_health_db_and_readiness() -> None:
    health_db = load_module("health_db", HEALTH_DB_SCRIPT)

    with tempfile.TemporaryDirectory(prefix="keshig-health-db-") as tmp:
        root = Path(tmp) / "personal-system"
        proc = subprocess.run(
            [sys.executable, "-I", str(TRAINING_SYSTEM_SCRIPT), "bootstrap", "--target", str(root)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"bootstrap failed: {proc.stdout}\n{proc.stderr}"
        db_file = root / "系统" / "health.sqlite3"
        assert db_file.is_file(), "bootstrap must initialize 系统/health.sqlite3"
        assert not (root / "系统" / "health.sqlite3-wal").exists(), "no WAL sidecar files allowed"
        assert health_db.verify_db_readonly(root) == []

        # Populate 10 days of stable baseline vitals, grip, intake, and device metrics.
        start = date.today() - timedelta(days=12)
        for offset in range(10):
            d_str = (start + timedelta(days=offset)).isoformat()
            health_db.log_vitals(root, d_str, weight_kg=75.0 - offset * 0.05, sleep_h=7.5)
            health_db.log_grip(root, d_str, "right", 54.0, trial=1)
            health_db.log_intake(root, d_str, "午餐", 2200, protein_g=160, carb_g=240, fat_g=65)
            health_db.ingest_device_payloads(
                root,
                d_str,
                28,
                wellness_payload=make_wellness(d_str, resting_hr=54, sleep_h=7.6, hrv=68.0),
            )

        # Device activity ingestion stays in device_* tables only.
        workout_day = (start + timedelta(days=9)).isoformat()
        health_db.ingest_device_payloads(
            root,
            workout_day,
            28,
            activities_payload={
                "ok": True,
                "status": "success",
                "activities": [
                    {
                        "activity_id": "garmin-act-1001",
                        "source": "HUAWEI",
                        "type": "strength_training",
                        "started_at_local": f"{workout_day}T18:00:00",
                        "moving_time_s": 3600,
                        "avg_hr": 128,
                        "max_hr": 162,
                        "training_load": 55.0,
                    }
                ],
            },
        )

        # Log a multi-set strength workout; top set 80kg x 3 @RPE 8.5 -> Epley e1RM inferred.
        w_res = health_db.log_workout(
            root,
            workout_day,
            "力量",
            sets_data=[
                {"exercise": "杠铃卧推", "role": "top", "set_index": 1, "weight_kg": 80.0, "reps": 3, "rpe": 8.5, "rest_sec": 180},
                {"exercise": "杠铃卧推", "role": "backoff", "set_index": 2, "weight_kg": 72.5, "reps": 6, "rpe": 7.0, "rest_sec": 150},
                {"exercise": "杠铃卧推", "role": "backoff", "set_index": 3, "weight_kg": 72.5, "reps": 6, "rpe": 7.5, "rest_sec": 150},
            ],
            minutes=60,
        )
        assert w_res["sets_logged"] == 3

        # Log an extensible custom observation into meta_observations.
        obs_res = health_db.log_custom(
            root,
            workout_day,
            "soreness_pectoral",
            value_num=2.0,
            unit="1-10",
            domain="body",
            ext={"side": "both"},
        )
        assert obs_res["ok"] is True and obs_res["table"] == "meta_observations"

        # Green baseline: manual and device metrics side-by-side, not merged.
        ctx = health_db.query_context(root, days=14)
        assert ctx["readiness"]["status"] == "green", ctx["readiness"]
        latest = [r for r in ctx["daily_overview"] if r["date"] == workout_day][0]
        assert latest["manual_sleep_h"] == 7.5
        assert latest["device_sleep_h"] == 7.6
        assert latest["device_hrv_ms"] == 68.0
        assert latest["grip_right_best_kg"] == 54.0
        ex_day = [r for r in ctx["exercise_overview"] if r["date"] == workout_day][0]
        assert ex_day["manual_minutes"] == 60
        assert ex_day["device_minutes"] == 60.0
        top_set = [s for s in ctx["recent_workout_sets"] if s["role"] == "top"][0]
        assert top_set["e1rm_is_inferred"] == 1
        assert top_set["e1rm_kg"] is not None and top_set["e1rm_kg"] > 85.0

        # Anti-nocebo: a single-day isolated HRV dip must stay green.
        day_10 = (start + timedelta(days=10)).isoformat()
        health_db.log_vitals(root, day_10, weight_kg=74.5, sleep_h=7.5)
        health_db.log_grip(root, day_10, "right", 54.0, trial=1)
        health_db.ingest_device_payloads(
            root, day_10, 28, wellness_payload=make_wellness(day_10, resting_hr=54, sleep_h=7.5, hrv=50.0)
        )
        ctx_dip = health_db.query_context(root, days=14)
        assert ctx_dip["readiness"]["status"] == "green", "single-metric dip must not dictate load reduction"
        assert ctx_dip["readiness"]["single_day_flags"] == 1

        # Multi-signal degradation across consecutive days (HRV + resting HR) -> yellow.
        for extra in (11, 12):
            d_bad = (start + timedelta(days=extra)).isoformat()
            health_db.log_vitals(root, d_bad, weight_kg=74.4, sleep_h=6.5)
            health_db.log_grip(root, d_bad, "right", 54.0, trial=1)
            health_db.ingest_device_payloads(
                root, d_bad, 28, wellness_payload=make_wellness(d_bad, resting_hr=61, sleep_h=6.5, hrv=48.0)
            )
        ctx_yellow = health_db.query_context(root, days=14)
        assert ctx_yellow["readiness"]["status"] == "yellow", ctx_yellow["readiness"]
        assert ctx_yellow["readiness"]["multi_day_flags"] >= 2
        flagged_metrics = {s["metric"] for s in ctx_yellow["readiness"]["signals"]}
        assert "device_hrv_ms" in flagged_metrics and "device_resting_hr" in flagged_metrics

        # doctor / validate / inspect stay read-only and pass on a healthy system.
        sub_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        for cmd in ("doctor", "validate"):
            proc = subprocess.run(
                [sys.executable, "-I", str(TRAINING_SYSTEM_SCRIPT), cmd, "--root", str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=sub_env,
            )
            assert proc.returncode == 0, f"{cmd} failed: {proc.stdout}\n{proc.stderr}"
        proc = subprocess.run(
            [sys.executable, "-I", str(TRAINING_SYSTEM_SCRIPT), "inspect", "--root", str(root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sub_env,
        )
        assert proc.returncode == 0, f"inspect failed: {proc.stderr}"
        summary = json.loads(proc.stdout)
        assert summary["database"]["initialized"] is True
        assert summary["database"]["schema_version"] == 2
        assert summary["database"]["counts"]["exercise_sets"] == 3
        assert summary["database"]["counts"]["body_device_daily"] > 0
        assert summary["database"]["counts"]["meta_observations"] == 1
        assert summary["database"]["domains"]["body"] > 0
        assert not (root / "系统" / "health.sqlite3-wal").exists(), "inspection must not create WAL sidecars"

        # Test v1 -> v2 automatic migration and existing health.db adoption in <agent_root>/data.
        import sqlite3
        data_dir = Path(tmp) / "agent-data"
        data_dir.mkdir(parents=True)
        legacy_db = data_dir / "health.db"
        conn = sqlite3.connect(str(legacy_db))
        conn.executescript(
            """
            CREATE TABLE vitals (
              date TEXT NOT NULL, logged_at TEXT NOT NULL, weight_kg REAL, body_fat_pct REAL,
              visceral REAL, waist_cm REAL, sleep_h REAL, measured_at TEXT, device TEXT, source TEXT,
              chest_cm REAL, PRIMARY KEY (date, source)
            );
            INSERT INTO vitals VALUES ('2026-10-20', '2026-10-20 08:00:00', 76.2, 22.0, NULL, 91.0, 7.2, 'morning_fasted', 'scale', 'manual', 100.0);
            CREATE TABLE activity (
              id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, logged_at TEXT NOT NULL,
              sport TEXT NOT NULL, detail TEXT, minutes INTEGER, load_kg REAL, sets INTEGER, reps INTEGER,
              witness INTEGER, slot_id INTEGER, reported_tod TEXT, source TEXT
            );
            INSERT INTO activity (date, logged_at, sport, detail, minutes, source) VALUES ('2026-10-20', '2026-10-20 20:00:00', '力量', '卧推 60kg 4x8', 60, 'manual');
            """
        )
        conn.commit()
        conn.close()

        proc_adopt = subprocess.run(
            [sys.executable, "-I", str(TRAINING_SYSTEM_SCRIPT), "bootstrap", "--target", str(data_dir)],
            capture_output=True,
            text=True,
        )
        assert proc_adopt.returncode == 0, f"adopt bootstrap failed: {proc_adopt.stdout}\n{proc_adopt.stderr}"
        assert health_db.db_path(data_dir) == legacy_db.resolve()
        info = health_db.inspect_db_readonly(data_dir)
        assert info["schema_version"] == 2
        assert info["counts"]["body_vitals"] == 1
        assert info["counts"]["exercise_sessions"] == 1


def test_plan_cycle_and_review_validators() -> None:
    validate_plan_mod = load_module("validate_plan_mod", VALIDATE_PLAN_SCRIPT)
    validate_cycle_mod = load_module("validate_cycle_mod", VALIDATE_CYCLE_SCRIPT)
    validate_review_mod = load_module("validate_review_mod", VALIDATE_REVIEW_SCRIPT)

    # 1. Fitness plan volume landmarks & concurrent cardio interference warnings.
    plan_example = json.loads(
        (REPO_ROOT / "skills" / "fitness-plan" / "references" / "plan-contract.example.json").read_text(encoding="utf-8")
    )
    errs, warns = validate_plan_mod.validate_plan(plan_example)
    assert not errs, errs

    overloaded = copy.deepcopy(plan_example)
    overloaded["training_days"][0]["exercises"][0]["prescription"]["sets"] = "10"
    overloaded["training_days"][0]["exercises"][0]["prescription"]["set_count"] = 10
    overloaded["cardio_schedule"] = [
        {
            "day_index": 1,
            "modality": "室外间歇跑",
            "intensity": "HIIT",
            "minutes": 30,
            "timing_relative_to_lifting": "before_lifting",
            "separation_hours": 0,
        }
    ]
    errs2, warns2 = validate_plan_mod.validate_plan(overloaded)
    assert not errs2, errs2
    assert any("single-session volume cap exceeded" in w for w in warns2), warns2
    assert any("concurrent training interference" in w for w in warns2), warns2

    # 2. Strength cycle contract validator.
    cycle_example = json.loads(
        (REPO_ROOT / "skills" / "strength-cycle-planner" / "references" / "cycle-contract.example.json").read_text(encoding="utf-8")
    )
    c_errs, c_warns = validate_cycle_mod.validate_cycle(cycle_example)
    assert not c_errs, c_errs

    bad_cycle = copy.deepcopy(cycle_example)
    # Multi-set backoff with a static single RPE must be rejected.
    bad_cycle["weeks"][0]["exposures"][0]["work_sets"][1]["rpe_prescription"] = "RPE 8"
    # Backoff sets without a linkage rule must be rejected.
    bad_cycle["weeks"][0]["exposures"][0]["work_sets"][1]["backoff_rule"] = ""
    c_errs2, _ = validate_cycle_mod.validate_cycle(bad_cycle)
    assert any("arrow format" in e for e in c_errs2), c_errs2
    assert any("backoff_rule" in e for e in c_errs2), c_errs2

    # Weighted calisthenics must account for total system load.
    bad_cal = copy.deepcopy(cycle_example)
    bad_cal["cycle_meta"]["is_weighted_calisthenics"] = True
    bad_cal["cycle_meta"]["baseline_bodyweight_kg"] = 70.0
    c_errs3, _ = validate_cycle_mod.validate_cycle(bad_cal)
    assert any("added_weight_kg" in e for e in c_errs3), c_errs3

    # 3. Review structure validator: 待补全 drafts cannot authorize plan changes.
    draft_review_md = """---
title: 2026-11-05 上肢A Keshig 力量训练复盘
date: 2026-11-05
week: W2
training_day: 上肢A
review_mode: cycle
status: 待补全
source_type: local
source_ref: "local:2026-11-05-upper-a"
progression_basis: "bench-cycle-v01"
plan: "bench-cycle-v01"
external_source: ""
---

## 1. 复盘模式与依据
周期单练复盘。

## 2. 本次判定
顶组达标。

## 3. 个人体感与记录澄清
待用户补充肩部体感。

## 4. 恢复与干扰
手记与设备并排正常。

## 6. 下一次训练
保持计划。

## 7. 待确认调整
当前计划不修改。

## 8. 待补全记录与已沉淀
已保存草稿。
"""
    r_draft = validate_review_mod.validate_review_text(draft_review_md, require_confirmed=False)
    assert r_draft["valid"] is True, r_draft["errors"]
    assert r_draft["can_modify_plan"] is False

    r_strict = validate_review_mod.validate_review_text(draft_review_md, require_confirmed=True)
    assert r_strict["valid"] is False
    assert any("待补全" in e for e in r_strict["errors"])

    # Frontmatter token leaks must be rejected.
    leaked = draft_review_md.replace('source_ref: "local:2026-11-05-upper-a"', 'source_ref: "ntn_ABCdef123456"')
    r_leak = validate_review_mod.validate_review_text(leaked)
    assert r_leak["valid"] is False
    assert any("token" in e for e in r_leak["errors"])


def main() -> int:
    test_health_db_and_readiness()
    test_plan_cycle_and_review_validators()
    print("PASS: health_db, readiness autoregulation, and scientific validators verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
