#!/usr/bin/env python3
"""SQLite data layer for Keshig: side-by-side manual & device records, per-set logs, and readiness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import training_system as system

DB_RELATIVE = Path("系统/health.sqlite3")
REPO_SCHEMA_DIR = HERE.parents[2] / "schema"

REQUIRED_TABLES = (
    "vitals",
    "activity",
    "workout_sets",
    "intake",
    "slots",
    "coach_log",
    "target",
    "assumption",
    "food_est",
    "device_daily",
    "device_activity",
    "device_fetch",
    "grip",
)
REQUIRED_VIEWS = (
    "v_device_day",
    "v_daily_overview",
)

FALLBACK_DDL = """
CREATE TABLE IF NOT EXISTS vitals (
  date          TEXT NOT NULL,
  logged_at     TEXT NOT NULL,
  weight_kg     REAL,
  body_fat_pct  REAL,
  visceral      REAL,
  waist_cm      REAL,
  chest_cm      REAL,
  sleep_h       REAL,
  measured_at   TEXT,
  device        TEXT,
  source        TEXT,
  PRIMARY KEY (date, source)
);

CREATE TABLE IF NOT EXISTS activity (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  sport       TEXT NOT NULL,
  detail      TEXT,
  minutes     INTEGER,
  load_kg     REAL,
  sets        INTEGER,
  reps        INTEGER,
  witness     INTEGER,
  slot_id     INTEGER,
  reported_tod TEXT,
  source      TEXT
);

CREATE TABLE IF NOT EXISTS workout_sets (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id      INTEGER,
  date             TEXT NOT NULL,
  logged_at        TEXT NOT NULL,
  exercise         TEXT NOT NULL,
  pattern_group    TEXT,
  role             TEXT DEFAULT 'work',
  set_index        INTEGER NOT NULL,
  weight_kg        REAL,
  bodyweight_kg    REAL,
  total_load_kg    REAL,
  reps             INTEGER,
  rpe              REAL,
  rir              REAL,
  rest_sec         INTEGER,
  e1rm_kg          REAL,
  e1rm_is_inferred INTEGER DEFAULT 1,
  quality_note     TEXT,
  pain_flag        INTEGER DEFAULT 0,
  source           TEXT DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS intake (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  meal        TEXT,
  kcal        REAL,
  protein_g   REAL,
  carb_g      REAL,
  fat_g       REAL,
  items       TEXT,
  is_training_day INTEGER,
  source      TEXT
);

CREATE TABLE IF NOT EXISTS slots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  weekday         INTEGER,
  occurrence_date TEXT,
  time_hhmm       TEXT,
  raw_text        TEXT,
  sport           TEXT,
  state           TEXT NOT NULL DEFAULT 'pending',
  active          INTEGER DEFAULT 1,
  created_at      TEXT
);

CREATE TABLE IF NOT EXISTS coach_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  kind      TEXT,
  slot_id   INTEGER,
  replied   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS target (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  effective_date TEXT NOT NULL,
  day_type       TEXT NOT NULL,
  kcal_min       REAL, kcal_max REAL,
  protein_min    REAL, protein_max REAL,
  carb_min       REAL, carb_max REAL,
  fat_min        REAL, fat_max REAL,
  water_l_min    REAL, water_l_max REAL,
  staple_min     REAL, staple_max REAL,
  source         TEXT,
  note           TEXT,
  logged_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assumption (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  key            TEXT NOT NULL,
  value          TEXT NOT NULL,
  condition      TEXT,
  effective_date TEXT NOT NULL,
  logged_at      TEXT NOT NULL,
  note           TEXT
);

CREATE TABLE IF NOT EXISTS food_est (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  item      TEXT UNIQUE NOT NULL,
  unit      TEXT,
  kcal      REAL, protein_g REAL, carb_g REAL, fat_g REAL,
  basis     TEXT,
  n_obs     INTEGER DEFAULT 1,
  last_seen TEXT,
  note      TEXT
);

CREATE INDEX IF NOT EXISTS idx_target_date         ON target(effective_date);
CREATE INDEX IF NOT EXISTS idx_food_est_item       ON food_est(item);
CREATE INDEX IF NOT EXISTS idx_activity_date       ON activity(date);
CREATE INDEX IF NOT EXISTS idx_workout_sets_date   ON workout_sets(date);
CREATE INDEX IF NOT EXISTS idx_workout_sets_ex     ON workout_sets(exercise, date);
CREATE INDEX IF NOT EXISTS idx_intake_date         ON intake(date);
CREATE INDEX IF NOT EXISTS idx_vitals_date         ON vitals(date);

CREATE TABLE IF NOT EXISTS device_daily (
  date             TEXT NOT NULL,
  metric           TEXT NOT NULL,
  value            REAL,
  unit             TEXT,
  source           TEXT,
  upstream_updated TEXT,
  fetched_at       TEXT NOT NULL,
  PRIMARY KEY (date, metric)
);

CREATE TABLE IF NOT EXISTS device_activity (
  activity_id       TEXT PRIMARY KEY,
  source            TEXT,
  type              TEXT,
  started_at_utc    TEXT,
  started_at_local  TEXT,
  finished_at_utc   TEXT,
  moving_time_s     INTEGER,
  elapsed_time_s    INTEGER,
  distance_m        REAL,
  avg_hr            REAL,
  max_hr            REAL,
  elevation_m       REAL,
  training_load     REAL,
  platform_synced_at TEXT,
  fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS device_fetch (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  fetched_at   TEXT NOT NULL,
  tool         TEXT,
  day          TEXT,
  history_days INTEGER,
  status       TEXT,
  n_records    INTEGER,
  note         TEXT
);

CREATE VIEW IF NOT EXISTS v_device_day AS
SELECT
  date,
  MAX(CASE WHEN metric = 'resting_hr'  THEN value END) AS resting_hr,
  ROUND(MAX(CASE WHEN metric = 'sleep_secs' THEN value END) / 3600.0, 2) AS sleep_h,
  MAX(CASE WHEN metric = 'sleep_score' THEN value END) AS sleep_score,
  MAX(CASE WHEN metric = 'hrv'         THEN value END) AS hrv_ms,
  MAX(CASE WHEN metric = 'atl'         THEN value END) AS atl,
  MAX(fetched_at) AS fetched_at
FROM device_daily
GROUP BY date;

CREATE INDEX IF NOT EXISTS idx_device_daily_date ON device_daily(date);
CREATE INDEX IF NOT EXISTS idx_device_activity_start ON device_activity(started_at_local);

CREATE TABLE IF NOT EXISTS grip (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  hand        TEXT NOT NULL,
  trial       INTEGER,
  kg          REAL NOT NULL,
  device      TEXT,
  protocol    TEXT,
  measured_at TEXT,
  source      TEXT,
  note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_grip_date ON grip(date);

CREATE VIEW IF NOT EXISTS v_daily_overview AS
WITH all_dates AS (
  SELECT date FROM vitals
  UNION
  SELECT date FROM device_daily
  UNION
  SELECT date FROM grip
),
vitals_day AS (
  SELECT
    date,
    MAX(weight_kg)    AS manual_weight_kg,
    MAX(body_fat_pct) AS manual_body_fat_pct,
    MAX(waist_cm)     AS manual_waist_cm,
    MAX(chest_cm)     AS manual_chest_cm,
    MAX(sleep_h)      AS manual_sleep_h
  FROM vitals
  GROUP BY date
),
grip_day AS (
  SELECT
    date,
    ROUND(MAX(CASE WHEN hand = 'right' THEN kg END), 2) AS grip_right_best_kg,
    ROUND(MAX(CASE WHEN hand = 'left'  THEN kg END), 2) AS grip_left_best_kg,
    ROUND(AVG(kg), 2)                                   AS grip_mean_kg
  FROM grip
  GROUP BY date
)
SELECT
  d.date,
  v.manual_weight_kg,
  v.manual_body_fat_pct,
  v.manual_waist_cm,
  v.manual_chest_cm,
  v.manual_sleep_h,
  g.grip_right_best_kg,
  g.grip_left_best_kg,
  g.grip_mean_kg,
  dev.resting_hr  AS device_resting_hr,
  dev.sleep_h     AS device_sleep_h,
  dev.sleep_score AS device_sleep_score,
  dev.hrv_ms      AS device_hrv_ms,
  dev.atl         AS device_atl,
  dev.fetched_at  AS device_fetched_at
FROM all_dates d
LEFT JOIN vitals_day   v   ON v.date   = d.date
LEFT JOIN grip_day     g   ON g.date   = d.date
LEFT JOIN v_device_day dev ON dev.date = d.date;
"""


def now_local_str() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(root: Path) -> Path:
    resolved_root = root.expanduser().resolve()
    system.check_private_path(resolved_root)
    target = system.safe_relative(resolved_root, DB_RELATIVE.as_posix(), DB_RELATIVE, "记录数据库")
    system.check_private_path(target)
    if target.is_symlink():
        system.stop("拒绝通过文件链接访问个人记录数据库")
    return target


def load_schema_sql() -> str:
    health_sql = REPO_SCHEMA_DIR / "health.sql"
    device_sql = REPO_SCHEMA_DIR / "device.sql"
    if health_sql.is_file() and device_sql.is_file():
        raw = health_sql.read_text(encoding="utf-8") + "\n" + device_sql.read_text(encoding="utf-8")
        # Remove WAL pragma so idle portable directory trees never leave .sqlite3-wal/.sqlite3-shm sidecars.
        lines = [line for line in raw.splitlines() if "journal_mode" not in line.lower()]
        return "\n".join(lines)
    return FALLBACK_DDL


def init_db(root: Path) -> Path:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ddl = load_schema_sql()
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(ddl)
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.commit()
    finally:
        conn.close()
    return path


def verify_db_readonly(root: Path) -> list[str]:
    path = db_path(root)
    if not path.is_file():
        return []
    problems: list[str] = []
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute("SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
        tables = {name for kind, name in rows if kind == "table"}
        views = {name for kind, name in rows if kind == "view"}
        for table in REQUIRED_TABLES:
            if table not in tables:
                problems.append(f"数据库缺少表：{table}")
        for view in REQUIRED_VIEWS:
            if view not in views:
                problems.append(f"数据库缺少视图：{view}")
    except sqlite3.Error as exc:
        problems.append(f"数据库无法只读检验：{exc}")
    finally:
        conn.close()
    return problems


def inspect_db_readonly(root: Path) -> dict[str, Any]:
    path = db_path(root)
    if not path.is_file():
        return {"initialized": False, "path": str(path)}
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        counts: dict[str, int] = {}
        for table in ("vitals", "activity", "workout_sets", "intake", "grip", "device_daily", "device_activity"):
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
            except sqlite3.Error:
                counts[table] = 0
        return {
            "initialized": True,
            "path": str(path),
            "counts": counts,
        }
    finally:
        conn.close()


def estimate_e1rm(
    weight_kg: float | None,
    reps: int | None,
    rpe: float | None = None,
    rir: float | None = None,
    bodyweight_kg: float | None = None,
) -> dict[str, Any]:
    """Estimate e1RM via Epley formula when reps + RIR <= 12; separate inferred vs measured."""
    if weight_kg is None or reps is None or reps < 1:
        return {"total_load_kg": None, "e1rm_kg": None, "e1rm_is_inferred": 1}
    total_load = (bodyweight_kg + weight_kg) if bodyweight_kg is not None else weight_kg
    if total_load <= 0:
        return {"total_load_kg": round(total_load, 2), "e1rm_kg": None, "e1rm_is_inferred": 1}

    effective_rir: float = 0.0
    if rir is not None:
        effective_rir = max(0.0, float(rir))
    elif rpe is not None:
        effective_rir = max(0.0, 10.0 - float(rpe))

    est_max_reps = float(reps) + effective_rir
    if est_max_reps > 12.0:
        return {"total_load_kg": round(total_load, 2), "e1rm_kg": None, "e1rm_is_inferred": 1}

    if reps == 1 and effective_rir == 0.0:
        e1rm_total = total_load
        inferred = 0
    else:
        e1rm_total = total_load * (1.0 + est_max_reps / 30.0)
        inferred = 1

    e1rm_external = (e1rm_total - bodyweight_kg) if bodyweight_kg is not None else e1rm_total
    return {
        "total_load_kg": round(total_load, 2),
        "e1rm_kg": round(e1rm_external, 2),
        "e1rm_total_system_kg": round(e1rm_total, 2) if bodyweight_kg is not None else None,
        "e1rm_is_inferred": inferred,
    }


def log_vitals(
    root: Path,
    date: str,
    weight_kg: float | None = None,
    body_fat_pct: float | None = None,
    waist_cm: float | None = None,
    chest_cm: float | None = None,
    sleep_h: float | None = None,
    measured_at: str = "morning_fasted",
    device: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    dt.date.fromisoformat(date)
    path = init_db(root)
    logged_at = now_local_str()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            INSERT INTO vitals (date, logged_at, weight_kg, body_fat_pct, waist_cm, chest_cm, sleep_h, measured_at, device, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source) DO UPDATE SET
              logged_at = excluded.logged_at,
              weight_kg = COALESCE(excluded.weight_kg, vitals.weight_kg),
              body_fat_pct = COALESCE(excluded.body_fat_pct, vitals.body_fat_pct),
              waist_cm = COALESCE(excluded.waist_cm, vitals.waist_cm),
              chest_cm = COALESCE(excluded.chest_cm, vitals.chest_cm),
              sleep_h = COALESCE(excluded.sleep_h, vitals.sleep_h),
              measured_at = COALESCE(excluded.measured_at, vitals.measured_at),
              device = COALESCE(excluded.device, vitals.device)
            """,
            (date, logged_at, weight_kg, body_fat_pct, waist_cm, chest_cm, sleep_h, measured_at, device, source),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "table": "vitals", "date": date, "source": source, "logged_at": logged_at}


def log_grip(
    root: Path,
    date: str,
    hand: str,
    kg: float,
    trial: int = 1,
    device: str | None = None,
    protocol: str | None = None,
    measured_at: str = "morning",
    note: str | None = None,
) -> dict[str, Any]:
    dt.date.fromisoformat(date)
    if hand not in ("right", "left"):
        raise ValueError("hand 必须是 right 或 left")
    path = init_db(root)
    logged_at = now_local_str()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            """
            INSERT INTO grip (date, logged_at, hand, trial, kg, device, protocol, measured_at, source, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)
            """,
            (date, logged_at, hand, trial, kg, device, protocol, measured_at, note),
        )
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "table": "grip", "id": row_id, "date": date, "hand": hand, "kg": kg}


def log_workout(
    root: Path,
    date: str,
    sport: str,
    sets_data: list[dict[str, Any]] | None = None,
    detail: str | None = None,
    minutes: int | None = None,
    reported_tod: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    dt.date.fromisoformat(date)
    path = init_db(root)
    logged_at = now_local_str()
    sets_data = sets_data or []
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            """
            INSERT INTO activity (date, logged_at, sport, detail, minutes, sets, reported_tod, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, logged_at, sport, detail, minutes, len(sets_data) if sets_data else None, reported_tod, source),
        )
        activity_id = cur.lastrowid
        inserted_sets = 0
        for idx, item in enumerate(sets_data, start=1):
            exercise = str(item.get("exercise") or "").strip()
            if not exercise:
                raise ValueError(f"第 {idx} 组缺少动作名称 exercise")
            weight_kg = float(item["weight_kg"]) if item.get("weight_kg") is not None else None
            bodyweight_kg = float(item["bodyweight_kg"]) if item.get("bodyweight_kg") is not None else None
            reps = int(item["reps"]) if item.get("reps") is not None else None
            rpe = float(item["rpe"]) if item.get("rpe") is not None else None
            rir = float(item["rir"]) if item.get("rir") is not None else None
            rest_sec = int(item["rest_sec"]) if item.get("rest_sec") is not None else None
            role = str(item.get("role") or "work")
            set_index = int(item.get("set_index") or idx)
            calc = estimate_e1rm(weight_kg, reps, rpe=rpe, rir=rir, bodyweight_kg=bodyweight_kg)
            conn.execute(
                """
                INSERT INTO workout_sets (
                  activity_id, date, logged_at, exercise, pattern_group, role, set_index,
                  weight_kg, bodyweight_kg, total_load_kg, reps, rpe, rir, rest_sec,
                  e1rm_kg, e1rm_is_inferred, quality_note, pain_flag, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    date,
                    logged_at,
                    exercise,
                    item.get("pattern_group"),
                    role,
                    set_index,
                    weight_kg,
                    bodyweight_kg,
                    calc["total_load_kg"],
                    reps,
                    rpe,
                    rir,
                    rest_sec,
                    calc["e1rm_kg"],
                    calc["e1rm_is_inferred"],
                    item.get("quality_note"),
                    1 if item.get("pain_flag") else 0,
                    source,
                ),
            )
            inserted_sets += 1
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "activity_id": activity_id, "sets_logged": inserted_sets, "date": date, "logged_at": logged_at}


def log_intake(
    root: Path,
    date: str,
    meal: str,
    kcal: float,
    protein_g: float | None = None,
    carb_g: float | None = None,
    fat_g: float | None = None,
    items: str | None = None,
    is_training_day: int | None = None,
    source: str = "confirmed_nutrition",
) -> dict[str, Any]:
    dt.date.fromisoformat(date)
    path = init_db(root)
    logged_at = now_local_str()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            """
            INSERT INTO intake (date, logged_at, meal, kcal, protein_g, carb_g, fat_g, items, is_training_day, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, logged_at, meal, kcal, protein_g, carb_g, fat_g, items, is_training_day, source),
        )
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "table": "intake", "id": row_id, "date": date, "meal": meal, "kcal": kcal}


def ingest_device_payloads(
    root: Path,
    day: str,
    history_days: int,
    wellness_payload: dict[str, Any] | None = None,
    activities_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist read-only VitalDock JSON payloads into device_* tables without touching manual tables."""
    path = init_db(root)
    fetched_at = now_utc_iso()
    daily_upserted = 0
    activities_upserted = 0
    conn = sqlite3.connect(str(path))
    try:
        if wellness_payload and wellness_payload.get("ok"):
            records = wellness_payload.get("records") or wellness_payload.get("days") or []
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                rec_date = str(rec.get("date") or rec.get("id") or "").strip()
                if not rec_date:
                    continue
                upstream_updated = str(rec.get("updated") or rec.get("upstream_updated") or "") or None
                metrics_map = rec.get("metrics") if isinstance(rec.get("metrics"), dict) else rec
                for metric, unit in (
                    ("resting_hr", "bpm"),
                    ("sleep_secs", "s"),
                    ("sleep_score", "score"),
                    ("ctl", "load"),
                    ("atl", "load"),
                    ("hrv", "ms"),
                    ("hrv_sdnn", "ms"),
                ):
                    val = metrics_map.get(metric)
                    if val is None or isinstance(val, bool):
                        continue
                    conn.execute(
                        """
                        INSERT INTO device_daily (date, metric, value, unit, source, upstream_updated, fetched_at)
                        VALUES (?, ?, ?, ?, 'intervals_wellness_merged', ?, ?)
                        ON CONFLICT(date, metric) DO UPDATE SET
                          value = excluded.value,
                          unit = excluded.unit,
                          upstream_updated = excluded.upstream_updated,
                          fetched_at = excluded.fetched_at
                        """,
                        (rec_date, metric, float(val), unit, upstream_updated, fetched_at),
                    )
                    daily_upserted += 1
            conn.execute(
                """
                INSERT INTO device_fetch (fetched_at, tool, day, history_days, status, n_records)
                VALUES (?, 'wellness_context', ?, ?, ?, ?)
                """,
                (fetched_at, day, history_days, wellness_payload.get("status"), daily_upserted),
            )

        if activities_payload and activities_payload.get("ok"):
            items = activities_payload.get("activities") or activities_payload.get("records") or []
            for act in items:
                if not isinstance(act, dict):
                    continue
                act_id = str(act.get("activity_id") or act.get("id") or "").strip()
                if not act_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO device_activity (
                      activity_id, source, type, started_at_utc, started_at_local, finished_at_utc,
                      moving_time_s, elapsed_time_s, distance_m, avg_hr, max_hr, elevation_m,
                      training_load, platform_synced_at, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(activity_id) DO UPDATE SET
                      type = excluded.type,
                      moving_time_s = excluded.moving_time_s,
                      elapsed_time_s = excluded.elapsed_time_s,
                      distance_m = excluded.distance_m,
                      avg_hr = excluded.avg_hr,
                      max_hr = excluded.max_hr,
                      elevation_m = excluded.elevation_m,
                      training_load = excluded.training_load,
                      platform_synced_at = excluded.platform_synced_at,
                      fetched_at = excluded.fetched_at
                    """,
                    (
                        act_id,
                        act.get("source") or "HUAWEI",
                        act.get("type"),
                        act.get("started_at_utc"),
                        act.get("started_at_local") or act.get("start_date_local"),
                        act.get("finished_at_utc"),
                        act.get("moving_time_s"),
                        act.get("elapsed_time_s"),
                        act.get("distance_m"),
                        act.get("avg_hr"),
                        act.get("max_hr"),
                        act.get("elevation_m"),
                        act.get("training_load"),
                        act.get("platform_synced_at"),
                        fetched_at,
                    ),
                )
                activities_upserted += 1
            conn.execute(
                """
                INSERT INTO device_fetch (fetched_at, tool, day, history_days, status, n_records)
                VALUES (?, 'recent_activities', ?, ?, ?, ?)
                """,
                (fetched_at, day, history_days, activities_payload.get("status"), activities_upserted),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "fetched_at": fetched_at,
        "device_daily_upserted": daily_upserted,
        "device_activity_upserted": activities_upserted,
    }


def compute_readiness(
    overview_rows: list[dict[str, Any]],
    recent_sets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate multi-signal readiness relative to personal rolling baseline.

    Rules:
    - Personal rolling baseline (prior 4..28 days) vs recent window (last 1..3 days).
    - Single-metric non-dictatorship: a single-day isolated device fluctuation stays 'green'
      (with warmup verification note) to avoid nocebo load reduction.
    - 'yellow' requires >=2 coupled recovery signals over recent days (or 1 persistent signal + performance drift).
    - 'red' requires persistent multi-signal deviation (>=4 days) or coupled pain/repeated performance drop.
    """
    sorted_rows = sorted(overview_rows, key=lambda r: str(r.get("date") or ""))
    if not sorted_rows:
        return {
            "status": "unknown",
            "is_inferred": True,
            "summary": "暂无恢复或体征记录，按主观体感与热身表现决定当日负荷。",
            "signals": [],
            "baselines": {},
        }

    recent = sorted_rows[-3:]
    baseline_pool = sorted_rows[:-3][-25:] if len(sorted_rows) > 3 else sorted_rows

    def mean_std(values: list[float]) -> tuple[float | None, float | None]:
        if not values:
            return None, None
        m = sum(values) / len(values)
        if len(values) < 2:
            return m, 0.0
        var = sum((x - m) ** 2 for x in values) / len(values)
        return m, math.sqrt(var)

    hrv_base, hrv_sd = mean_std([float(r["device_hrv_ms"]) for r in baseline_pool if r.get("device_hrv_ms") is not None])
    rhr_base, _ = mean_std([float(r["device_resting_hr"]) for r in baseline_pool if r.get("device_resting_hr") is not None])
    grip_base, _ = mean_std([float(r["grip_mean_kg"]) for r in baseline_pool if r.get("grip_mean_kg") is not None])

    signals: list[dict[str, Any]] = []
    multi_day_flags = 0
    single_day_flags = 0

    # 1. HRV relative to personal rolling baseline
    recent_hrv = [float(r["device_hrv_ms"]) for r in recent if r.get("device_hrv_ms") is not None]
    if hrv_base and hrv_base > 0 and recent_hrv:
        threshold = min(hrv_base * 0.90, hrv_base - (hrv_sd or 0.0))
        low_days = sum(1 for v in recent_hrv if v < threshold)
        if low_days >= 2:
            multi_day_flags += 1
            signals.append({
                "metric": "device_hrv_ms",
                "level": "multi_day_deviation",
                "detail": f"近期 HRV 连续 {low_days} 天低于个人基线（基线 {hrv_base:.1f} ms，近期均值 {sum(recent_hrv)/len(recent_hrv):.1f} ms）",
            })
        elif low_days == 1 and recent_hrv[-1] < threshold:
            single_day_flags += 1
            signals.append({
                "metric": "device_hrv_ms",
                "level": "single_day_fluctuation",
                "detail": f"单日 HRV 低于个人基线（{recent_hrv[-1]:.1f} vs 基线 {hrv_base:.1f} ms）",
            })

    # 2. Resting HR relative to personal rolling baseline
    recent_rhr = [float(r["device_resting_hr"]) for r in recent if r.get("device_resting_hr") is not None]
    if rhr_base and recent_rhr:
        high_days = sum(1 for v in recent_rhr if v >= rhr_base + 4.0)
        if high_days >= 2:
            multi_day_flags += 1
            signals.append({
                "metric": "device_resting_hr",
                "level": "multi_day_deviation",
                "detail": f"近期静息心率连续 {high_days} 天高于个人基线 ≥4 bpm（基线 {rhr_base:.1f} bpm）",
            })
        elif high_days == 1 and recent_rhr[-1] >= rhr_base + 4.0:
            single_day_flags += 1
            signals.append({
                "metric": "device_resting_hr",
                "level": "single_day_fluctuation",
                "detail": f"单日静息心率高于个人基线（{recent_rhr[-1]:.1f} vs 基线 {rhr_base:.1f} bpm）",
            })

    # 3. Morning Grip relative to personal rolling baseline
    recent_grip = [float(r["grip_mean_kg"]) for r in recent if r.get("grip_mean_kg") is not None]
    if grip_base and grip_base > 0 and recent_grip:
        low_grip_days = sum(1 for v in recent_grip if v <= grip_base * 0.93)
        if low_grip_days >= 2:
            multi_day_flags += 1
            signals.append({
                "metric": "grip_mean_kg",
                "level": "multi_day_deviation",
                "detail": f"晨起握力连续 {low_grip_days} 天较个人基线下降 ≥7%（基线 {grip_base:.1f} kg）",
            })
        elif low_grip_days == 1 and recent_grip[-1] <= grip_base * 0.93:
            single_day_flags += 1
            signals.append({
                "metric": "grip_mean_kg",
                "level": "single_day_fluctuation",
                "detail": f"单日晨起握力较个人基线下降（{recent_grip[-1]:.1f} vs 基线 {grip_base:.1f} kg）",
            })

    # 4. Sleep duration (manual and device checked side-by-side without overwriting)
    short_sleep_days = 0
    for r in recent:
        m_sleep = r.get("manual_sleep_h")
        d_sleep = r.get("device_sleep_h")
        effective_sleep = min(x for x in (m_sleep, d_sleep) if x is not None) if (m_sleep is not None or d_sleep is not None) else None
        if effective_sleep is not None and float(effective_sleep) < 6.0:
            short_sleep_days += 1
    if short_sleep_days >= 2:
        multi_day_flags += 1
        signals.append({
            "metric": "sleep_h",
            "level": "multi_day_deviation",
            "detail": f"近 3 天内有 {short_sleep_days} 天睡眠不足 6 小时",
        })
    elif short_sleep_days == 1:
        single_day_flags += 1
        signals.append({
            "metric": "sleep_h",
            "level": "single_day_fluctuation",
            "detail": "近 3 天内有 1 天睡眠不足 6 小时",
        })

    # 5. Pain or high-RPE performance drift in recent workout sets
    recent_sets = recent_sets or []
    pain_sets = sum(1 for s in recent_sets if s.get("pain_flag"))
    overshoot_sets = sum(1 for s in recent_sets if s.get("rpe") is not None and float(s["rpe"]) >= 9.5 and s.get("role") != "top")
    if pain_sets > 0:
        signals.append({
            "metric": "workout_pain_flag",
            "level": "safety_flag",
            "detail": f"近期训练记录包含 {pain_sets} 组疼痛/不适标记",
        })
    if overshoot_sets >= 2:
        multi_day_flags += 1
        signals.append({
            "metric": "workout_rpe_overshoot",
            "level": "multi_day_deviation",
            "detail": f"近期非顶组出现 {overshoot_sets} 组 RPE ≥ 9.5 的疲劳漂移",
        })

    # Triage decision
    if pain_sets > 0 or multi_day_flags >= 3:
        status = "red"
        recommendation = "多维恢复指标持续偏离个人基线或存在疼痛信号：建议暂停高强度推进，优先评估提前减量周（Deload）或降级接回。"
    elif multi_day_flags >= 2 or (multi_day_flags == 1 and single_day_flags >= 2):
        status = "yellow"
        recommendation = "多项恢复指标连续偏离个人基线：建议结合主观体感启用当日‘状态差版’（顶组目标 RPE 下调 0.5—1.0 或回退组减 1—2 组，删除高疲劳孤立动作）。"
    else:
        status = "green"
        if single_day_flags > 0 or multi_day_flags == 1:
            recommendation = "单指标或单日波动（单指标不独裁）：不提前削减计划重量，按原计划热身并通过首组/顶组实际 RPE 现场核实。"
        else:
            recommendation = "客观恢复指标处于个人滚动基线正常范围内：可按计划推进。"

    return {
        "status": status,
        "is_inferred": True,
        "multi_day_flags": multi_day_flags,
        "single_day_flags": single_day_flags,
        "recommendation": recommendation,
        "signals": signals,
        "baselines": {
            "hrv_ms": round(hrv_base, 2) if hrv_base is not None else None,
            "resting_hr": round(rhr_base, 2) if rhr_base is not None else None,
            "grip_mean_kg": round(grip_base, 2) if grip_base is not None else None,
        },
    }


def query_context(root: Path, days: int = 14) -> dict[str, Any]:
    path = db_path(root)
    if not path.is_file():
        return {"ok": True, "initialized": False, "message": "记录库尚未初始化"}

    cutoff_overview = (dt.date.today() - dt.timedelta(days=max(days, 28))).isoformat()
    cutoff_recent = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        overview_all = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM v_daily_overview WHERE date >= ? ORDER BY date ASC",
                (cutoff_overview,),
            ).fetchall()
        ]
        overview_recent = [r for r in overview_all if str(r.get("date") or "") >= cutoff_recent]
        recent_sets = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, exercise, pattern_group, role, set_index, weight_kg, bodyweight_kg,
                       total_load_kg, reps, rpe, rir, rest_sec, e1rm_kg, e1rm_is_inferred, quality_note, pain_flag
                FROM workout_sets
                WHERE date >= ?
                ORDER BY date DESC, id ASC
                LIMIT 100
                """,
                (cutoff_recent,),
            ).fetchall()
        ]
        daily_intake = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date,
                       ROUND(SUM(kcal), 1) AS total_kcal,
                       ROUND(SUM(protein_g), 1) AS total_protein_g,
                       ROUND(SUM(carb_g), 1) AS total_carb_g,
                       ROUND(SUM(fat_g), 1) AS total_fat_g,
                       COUNT(*) AS meal_count
                FROM intake
                WHERE date >= ?
                GROUP BY date
                ORDER BY date ASC
                """,
                (cutoff_recent,),
            ).fetchall()
        ]
    finally:
        conn.close()

    readiness = compute_readiness(overview_all, recent_sets)
    return {
        "ok": True,
        "initialized": True,
        "window_days": days,
        "daily_overview": overview_recent,
        "readiness": readiness,
        "recent_workout_sets": recent_sets,
        "daily_intake": daily_intake,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keshig SQLite 记录库管理与并排对照工具")
    subs = parser.add_subparsers(dest="command", required=True)

    p_init = subs.add_parser("init")
    p_init.add_argument("--root", required=True)

    p_vitals = subs.add_parser("log-vitals")
    p_vitals.add_argument("--root", required=True)
    p_vitals.add_argument("--date", default=dt.date.today().isoformat())
    p_vitals.add_argument("--weight-kg", type=float)
    p_vitals.add_argument("--body-fat-pct", type=float)
    p_vitals.add_argument("--waist-cm", type=float)
    p_vitals.add_argument("--chest-cm", type=float)
    p_vitals.add_argument("--sleep-h", type=float)
    p_vitals.add_argument("--measured-at", default="morning_fasted")
    p_vitals.add_argument("--device")
    p_vitals.add_argument("--source", default="manual")

    p_grip = subs.add_parser("log-grip")
    p_grip.add_argument("--root", required=True)
    p_grip.add_argument("--date", default=dt.date.today().isoformat())
    p_grip.add_argument("--hand", choices=("right", "left"), required=True)
    p_grip.add_argument("--kg", type=float, required=True)
    p_grip.add_argument("--trial", type=int, default=1)
    p_grip.add_argument("--device")
    p_grip.add_argument("--protocol")
    p_grip.add_argument("--measured-at", default="morning")
    p_grip.add_argument("--note")

    p_workout = subs.add_parser("log-workout")
    p_workout.add_argument("--root", required=True)
    p_workout.add_argument("--date", default=dt.date.today().isoformat())
    p_workout.add_argument("--sport", default="力量")
    p_workout.add_argument("--detail")
    p_workout.add_argument("--minutes", type=int)
    p_workout.add_argument("--reported-tod")
    p_workout.add_argument("--sets-json", help="JSON array of set objects")

    p_intake = subs.add_parser("log-intake")
    p_intake.add_argument("--root", required=True)
    p_intake.add_argument("--date", default=dt.date.today().isoformat())
    p_intake.add_argument("--meal", required=True)
    p_intake.add_argument("--kcal", type=float, required=True)
    p_intake.add_argument("--protein-g", type=float)
    p_intake.add_argument("--carb-g", type=float)
    p_intake.add_argument("--fat-g", type=float)
    p_intake.add_argument("--items")
    p_intake.add_argument("--is-training-day", type=int, choices=(0, 1))

    p_sync = subs.add_parser("sync-device")
    p_sync.add_argument("--root", required=True)
    p_sync.add_argument("--day", default=dt.date.today().isoformat())
    p_sync.add_argument("--history-days", type=int, default=28)
    p_sync.add_argument("--limit", type=int, default=20)
    p_sync.add_argument("--timeout", type=float, default=120)

    p_query = subs.add_parser("query-context")
    p_query.add_argument("--root", required=True)
    p_query.add_argument("--days", type=int, default=14)

    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    system.load_config_readonly(root)

    if args.command == "init":
        path = init_db(root)
        print(json.dumps({"ok": True, "db_path": str(path)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "log-vitals":
        res = log_vitals(
            root,
            args.date,
            weight_kg=args.weight_kg,
            body_fat_pct=args.body_fat_pct,
            waist_cm=args.waist_cm,
            chest_cm=args.chest_cm,
            sleep_h=args.sleep_h,
            measured_at=args.measured_at,
            device=args.device,
            source=args.source,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.command == "log-grip":
        res = log_grip(
            root,
            args.date,
            args.hand,
            args.kg,
            trial=args.trial,
            device=args.device,
            protocol=args.protocol,
            measured_at=args.measured_at,
            note=args.note,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.command == "log-workout":
        sets_data = json.loads(args.sets_json) if args.sets_json else []
        res = log_workout(
            root,
            args.date,
            args.sport,
            sets_data=sets_data,
            detail=args.detail,
            minutes=args.minutes,
            reported_tod=args.reported_tod,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.command == "log-intake":
        res = log_intake(
            root,
            args.date,
            args.meal,
            args.kcal,
            protein_g=args.protein_g,
            carb_g=args.carb_g,
            fat_g=args.fat_g,
            items=args.items,
            is_training_day=args.is_training_day,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.command == "sync-device":
        import vitaldock_client as vd
        from types import SimpleNamespace as NS

        w_args = NS(command="wellness", root=str(root), day=args.day, history_days=args.history_days, limit=args.limit, timeout=args.timeout)
        a_args = NS(command="activities", root=str(root), day=args.day, history_days=args.history_days, limit=args.limit, timeout=args.timeout)
        w_res = vd.execute(w_args)
        a_res = vd.execute(a_args)
        if not w_res.get("ok") and not a_res.get("ok"):
            print(json.dumps({"ok": False, "wellness": w_res, "activities": a_res}, ensure_ascii=False, indent=2))
            return 1
        res = ingest_device_payloads(root, args.day, args.history_days, wellness_payload=w_res, activities_payload=a_res)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.command == "query-context":
        res = query_context(root, days=args.days)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
