#!/usr/bin/env python3
"""Keshig 统一记录库：身体 / 运动 / 饮食三域，手记与设备分表并排，schema v2 自动迁移。

域结构（schema v2，PRAGMA user_version = 2）：
  身体  body_vitals / body_grip（手记） + body_device_daily（VitalDock）
  运动  exercise_sessions / exercise_sets（手记） + exercise_device_sessions（设备）
  饮食  diet_entries / diet_food_est / diet_targets（手记确认链）
  跨域  meta_assumptions / meta_observations / meta_slots / meta_coach_log / meta_device_fetch

扩展规则：新字段先进各表 ext JSON 列；全新记录类型先进 meta_observations；
被广泛使用后才提升为正式列（升 user_version）。设备与手记永不合并，并排只在视图里。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import training_system as system

DB_RELATIVE = Path("系统/health.sqlite3")
REPO_SCHEMA_DIR = HERE.parents[2] / "schema"
SCHEMA_VERSION = 2

REQUIRED_TABLES = (
    "body_vitals",
    "body_grip",
    "body_device_daily",
    "exercise_sessions",
    "exercise_sets",
    "exercise_device_sessions",
    "diet_entries",
    "diet_food_est",
    "diet_targets",
    "meta_assumptions",
    "meta_observations",
    "meta_slots",
    "meta_coach_log",
    "meta_device_fetch",
)
REQUIRED_VIEWS = (
    "v_body_device_day",
    "v_daily_overview",
    "v_exercise_day",
)

# v1 → v2 表名映射（ALTER TABLE RENAME 保数据迁移）
V1_TABLE_RENAMES = {
    "vitals": "body_vitals",
    "grip": "body_grip",
    "device_daily": "body_device_daily",
    "activity": "exercise_sessions",
    "workout_sets": "exercise_sets",
    "device_activity": "exercise_device_sessions",
    "intake": "diet_entries",
    "food_est": "diet_food_est",
    "target": "diet_targets",
    "assumption": "meta_assumptions",
    "slots": "meta_slots",
    "coach_log": "meta_coach_log",
    "device_fetch": "meta_device_fetch",
}
V1_COLUMN_RENAMES = {
    "exercise_sets": {"activity_id": "session_id"},
}
V1_VIEWS_TO_DROP = ("v_device_day", "v_daily_overview")

# 设备日指标的已知词表；records 中 metrics 字典里的其他数值字段也会透传落库
KNOWN_DEVICE_METRICS = (
    ("resting_hr", "bpm"),
    ("sleep_secs", "s"),
    ("sleep_score", "score"),
    ("ctl", "load"),
    ("atl", "load"),
    ("tsb", "load"),
    ("hrv", "ms"),
    ("hrv_sdnn", "ms"),
    ("steps", "steps"),
    ("weight_kg", "kg"),
)

FALLBACK_DDL = """
CREATE TABLE IF NOT EXISTS body_vitals (
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
  ext           TEXT CHECK (ext IS NULL OR json_valid(ext)),
  PRIMARY KEY (date, source)
);
CREATE TABLE IF NOT EXISTS body_grip (
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
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_body_grip_date ON body_grip(date);
CREATE TABLE IF NOT EXISTS exercise_sessions (
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
  source      TEXT,
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_exercise_sessions_date ON exercise_sessions(date);
CREATE TABLE IF NOT EXISTS exercise_sets (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id       INTEGER,
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
  source           TEXT DEFAULT 'manual',
  ext              TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_date ON exercise_sets(date);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_ex   ON exercise_sets(exercise, date);
CREATE TABLE IF NOT EXISTS diet_entries (
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
  source      TEXT,
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_entries_date ON diet_entries(date);
CREATE TABLE IF NOT EXISTS diet_food_est (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  item      TEXT UNIQUE NOT NULL,
  unit      TEXT,
  kcal      REAL, protein_g REAL, carb_g REAL, fat_g REAL,
  basis     TEXT,
  n_obs     INTEGER DEFAULT 1,
  last_seen TEXT,
  note      TEXT,
  ext       TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_food_est_item ON diet_food_est(item);
CREATE TABLE IF NOT EXISTS diet_targets (
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
  logged_at      TEXT NOT NULL,
  ext            TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_targets_date ON diet_targets(effective_date);
CREATE TABLE IF NOT EXISTS meta_assumptions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  key            TEXT NOT NULL,
  value          TEXT NOT NULL,
  condition      TEXT,
  effective_date TEXT NOT NULL,
  logged_at      TEXT NOT NULL,
  note           TEXT,
  ext            TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE TABLE IF NOT EXISTS meta_observations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  date       TEXT NOT NULL,
  logged_at  TEXT NOT NULL,
  domain     TEXT,
  kind       TEXT NOT NULL,
  value_num  REAL,
  value_text TEXT,
  unit       TEXT,
  source     TEXT,
  ext        TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_meta_observations_date ON meta_observations(date);
CREATE INDEX IF NOT EXISTS idx_meta_observations_kind ON meta_observations(kind, date);
CREATE TABLE IF NOT EXISTS meta_slots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  weekday         INTEGER,
  occurrence_date TEXT,
  time_hhmm       TEXT,
  raw_text        TEXT,
  sport           TEXT,
  state           TEXT NOT NULL DEFAULT 'pending',
  active          INTEGER DEFAULT 1,
  created_at      TEXT,
  ext             TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE TABLE IF NOT EXISTS meta_coach_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  kind      TEXT,
  slot_id   INTEGER,
  replied   INTEGER DEFAULT 0,
  ext       TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE TABLE IF NOT EXISTS body_device_daily (
  date             TEXT NOT NULL,
  metric           TEXT NOT NULL,
  value            REAL,
  unit             TEXT,
  source           TEXT,
  upstream_updated TEXT,
  fetched_at       TEXT NOT NULL,
  ext              TEXT CHECK (ext IS NULL OR json_valid(ext)),
  PRIMARY KEY (date, metric)
);
CREATE INDEX IF NOT EXISTS idx_body_device_daily_date ON body_device_daily(date);
CREATE TABLE IF NOT EXISTS exercise_device_sessions (
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
  fetched_at        TEXT,
  ext               TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_exercise_device_sessions_start ON exercise_device_sessions(started_at_local);
CREATE TABLE IF NOT EXISTS meta_device_fetch (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  fetched_at   TEXT NOT NULL,
  tool         TEXT,
  day          TEXT,
  history_days INTEGER,
  status       TEXT,
  n_records    INTEGER,
  note         TEXT,
  ext          TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE VIEW IF NOT EXISTS v_body_device_day AS
SELECT
  date,
  MAX(CASE WHEN metric = 'resting_hr'  THEN value END) AS resting_hr,
  ROUND(MAX(CASE WHEN metric = 'sleep_secs' THEN value END) / 3600.0, 2) AS sleep_h,
  MAX(CASE WHEN metric = 'sleep_score' THEN value END) AS sleep_score,
  MAX(CASE WHEN metric = 'hrv'         THEN value END) AS hrv_ms,
  MAX(CASE WHEN metric = 'atl'         THEN value END) AS atl,
  MAX(CASE WHEN metric = 'ctl'         THEN value END) AS ctl,
  MAX(fetched_at) AS fetched_at
FROM body_device_daily
GROUP BY date;
CREATE VIEW IF NOT EXISTS v_daily_overview AS
WITH all_dates AS (
  SELECT date FROM body_vitals
  UNION
  SELECT date FROM body_device_daily
  UNION
  SELECT date FROM body_grip
),
vitals_day AS (
  SELECT
    date,
    MAX(weight_kg)    AS manual_weight_kg,
    MAX(body_fat_pct) AS manual_body_fat_pct,
    MAX(waist_cm)     AS manual_waist_cm,
    MAX(chest_cm)     AS manual_chest_cm,
    MAX(sleep_h)      AS manual_sleep_h
  FROM body_vitals
  GROUP BY date
),
grip_day AS (
  SELECT
    date,
    ROUND(MAX(CASE WHEN hand = 'right' THEN kg END), 2) AS grip_right_best_kg,
    ROUND(MAX(CASE WHEN hand = 'left'  THEN kg END), 2) AS grip_left_best_kg,
    ROUND(AVG(kg), 2)                                   AS grip_mean_kg
  FROM body_grip
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
  dev.ctl         AS device_ctl,
  dev.fetched_at  AS device_fetched_at
FROM all_dates d
LEFT JOIN vitals_day        v   ON v.date   = d.date
LEFT JOIN grip_day          g   ON g.date   = d.date
LEFT JOIN v_body_device_day dev ON dev.date = d.date;
CREATE VIEW IF NOT EXISTS v_exercise_day AS
WITH all_dates AS (
  SELECT date FROM exercise_sessions
  UNION
  SELECT substr(started_at_local, 1, 10) FROM exercise_device_sessions
),
manual_day AS (
  SELECT
    date,
    COUNT(*)                  AS manual_sessions,
    GROUP_CONCAT(sport, '、') AS manual_sports,
    SUM(minutes)              AS manual_minutes
  FROM exercise_sessions
  GROUP BY date
),
device_day AS (
  SELECT
    substr(started_at_local, 1, 10)      AS date,
    COUNT(*)                             AS device_sessions,
    GROUP_CONCAT(type, '、')             AS device_types,
    ROUND(SUM(moving_time_s) / 60.0, 1)  AS device_minutes,
    ROUND(AVG(avg_hr), 1)                AS device_avg_hr,
    ROUND(SUM(training_load), 1)         AS device_training_load
  FROM exercise_device_sessions
  GROUP BY substr(started_at_local, 1, 10)
)
SELECT
  d.date,
  m.manual_sessions,
  m.manual_sports,
  m.manual_minutes,
  dev.device_sessions,
  dev.device_types,
  dev.device_minutes,
  dev.device_avg_hr,
  dev.device_training_load
FROM all_dates d
LEFT JOIN manual_day m   ON m.date   = d.date
LEFT JOIN device_day dev ON dev.date = d.date;
"""


def now_local_str() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(root: Path) -> Path:
    resolved_root = root.expanduser().resolve()
    system.check_private_path(resolved_root)
    rel: Path = DB_RELATIVE
    cfg_file = system.config_path(resolved_root)
    if cfg_file.is_file():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8-sig"))
            if isinstance(cfg, dict) and isinstance(cfg.get("database_path"), str) and cfg["database_path"].strip():
                rel = Path(cfg["database_path"].strip())
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    elif (resolved_root / "health.db").is_file() and not (resolved_root / DB_RELATIVE).is_file():
        rel = Path("health.db")
    target = system.safe_relative(resolved_root, rel.as_posix(), DB_RELATIVE, "记录数据库")
    system.check_private_path(target)
    if target.is_symlink():
        system.stop("拒绝通过文件链接访问个人记录数据库")
    return target


def load_schema_sql() -> str:
    health_sql = REPO_SCHEMA_DIR / "health.sql"
    device_sql = REPO_SCHEMA_DIR / "device.sql"
    if health_sql.is_file() and device_sql.is_file():
        raw = health_sql.read_text(encoding="utf-8") + "\n" + device_sql.read_text(encoding="utf-8")
        # 去掉 WAL 设置：可移动目录树不能留下 .sqlite3-wal/.sqlite3-shm 残留
        lines = [line for line in raw.splitlines() if "journal_mode" not in line.lower()]
        return "\n".join(lines)
    return FALLBACK_DDL


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def migrate_v1_to_v2(conn: sqlite3.Connection) -> list[str]:
    """把 v1 旧表名迁移到 v2 三域命名。幂等：已迁移的库重跑为空操作。"""
    existing = _table_names(conn)
    if not (set(V1_TABLE_RENAMES) & existing):
        return []

    # 先删旧视图（SQLite 会在 RENAME 时改写视图定义，必须先删再建）
    for view in V1_VIEWS_TO_DROP:
        conn.execute(f"DROP VIEW IF EXISTS {view}")

    migrated: list[str] = []
    for old, new in V1_TABLE_RENAMES.items():
        if old in existing and new not in existing:
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
            migrated.append(f"{old} → {new}")
            existing.discard(old)
            existing.add(new)

    for table, columns in V1_COLUMN_RENAMES.items():
        if table not in existing:
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for old_col, new_col in columns.items():
            if old_col in cols and new_col not in cols:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}")
                migrated.append(f"{table}.{old_col} → {new_col}")

    for table in sorted(existing & (set(REQUIRED_TABLES))):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "ext" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN ext TEXT CHECK (ext IS NULL OR json_valid(ext))")

    if "body_vitals" in existing:
        expected_cols = [
            "date", "logged_at", "weight_kg", "body_fat_pct", "visceral",
            "waist_cm", "chest_cm", "sleep_h", "measured_at", "device", "source", "ext",
        ]
        actual_cols = [r[1] for r in conn.execute("PRAGMA table_info(body_vitals)").fetchall()]
        if actual_cols != expected_cols and set(actual_cols).issubset(set(expected_cols)):
            conn.execute("ALTER TABLE body_vitals RENAME TO _body_vitals_old")
            conn.execute(
                """
                CREATE TABLE body_vitals (
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
                  ext           TEXT CHECK (ext IS NULL OR json_valid(ext)),
                  PRIMARY KEY (date, source)
                )
                """
            )
            common = [c for c in expected_cols if c in actual_cols]
            col_csv = ", ".join(common)
            conn.execute(f"INSERT INTO body_vitals ({col_csv}) SELECT {col_csv} FROM _body_vitals_old")
            conn.execute("DROP TABLE _body_vitals_old")
            migrated.append("body_vitals: 列顺序已规范化")
    return migrated


def init_db(root: Path) -> Path:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        probe = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            needs_backup = bool(set(V1_TABLE_RENAMES) & _table_names(probe))
        except sqlite3.Error:
            needs_backup = False
        finally:
            probe.close()
        if needs_backup:
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, backup_dir / f"health-v1-before-v2-{stamp}.sqlite3")
    conn = sqlite3.connect(str(path))
    try:
        migrate_v1_to_v2(conn)
        conn.executescript(load_schema_sql())
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.commit()
    finally:
        conn.close()
    return path


def migrate_db(root: Path) -> dict[str, Any]:
    """显式迁移入口：v1 → v2 前先把整库复制到 系统/backups/。"""
    path = db_path(root)
    if not path.is_file():
        return {"ok": True, "migrated": [], "message": "数据库不存在，将在首次写入时按 v2 建库"}
    uri = f"file:{path.as_posix()}?mode=ro"
    probe = sqlite3.connect(uri, uri=True)
    try:
        needs = bool(set(V1_TABLE_RENAMES) & _table_names(probe))
    finally:
        probe.close()
    if not needs:
        init_db(root)
        return {"ok": True, "migrated": [], "message": "已是 v2，无需迁移"}

    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"health-v1-before-v2-{stamp}.sqlite3"
    shutil.copy2(path, backup)

    conn = sqlite3.connect(str(path))
    try:
        migrated = migrate_v1_to_v2(conn)
        conn.executescript(load_schema_sql())
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "migrated": migrated, "backup": str(backup)}


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
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        counts: dict[str, int] = {}
        for table in REQUIRED_TABLES:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
            except sqlite3.Error:
                counts[table] = 0
        by_domain = {
            "body": sum(counts[t] for t in ("body_vitals", "body_grip", "body_device_daily")),
            "exercise": sum(counts[t] for t in ("exercise_sessions", "exercise_sets", "exercise_device_sessions")),
            "diet": sum(counts[t] for t in ("diet_entries", "diet_food_est", "diet_targets")),
            "meta": sum(counts[t] for t in ("meta_assumptions", "meta_observations", "meta_slots", "meta_coach_log", "meta_device_fetch")),
        }
        return {
            "initialized": True,
            "path": str(path),
            "schema_version": version,
            "domains": by_domain,
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
    """Epley 估算 e1RM（仅 reps + RIR <= 12）；推断与实测分开标明。"""
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
    ext: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dt.date.fromisoformat(date)
    path = init_db(root)
    logged_at = now_local_str()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            INSERT INTO body_vitals (date, logged_at, weight_kg, body_fat_pct, waist_cm, chest_cm, sleep_h, measured_at, device, source, ext)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source) DO UPDATE SET
              logged_at = excluded.logged_at,
              weight_kg = COALESCE(excluded.weight_kg, body_vitals.weight_kg),
              body_fat_pct = COALESCE(excluded.body_fat_pct, body_vitals.body_fat_pct),
              waist_cm = COALESCE(excluded.waist_cm, body_vitals.waist_cm),
              chest_cm = COALESCE(excluded.chest_cm, body_vitals.chest_cm),
              sleep_h = COALESCE(excluded.sleep_h, body_vitals.sleep_h),
              measured_at = COALESCE(excluded.measured_at, body_vitals.measured_at),
              device = COALESCE(excluded.device, body_vitals.device),
              ext = COALESCE(excluded.ext, body_vitals.ext)
            """,
            (date, logged_at, weight_kg, body_fat_pct, waist_cm, chest_cm, sleep_h, measured_at, device, source,
             json.dumps(ext, ensure_ascii=False) if ext else None),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "table": "body_vitals", "date": date, "source": source, "logged_at": logged_at}


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
        ext_json = json.dumps({"note": note}, ensure_ascii=False) if note else None
        cur = conn.execute(
            """
            INSERT INTO body_grip (date, logged_at, hand, trial, kg, device, protocol, measured_at, source, ext)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)
            """,
            (date, logged_at, hand, trial, kg, device, protocol, measured_at, ext_json),
        )
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "table": "body_grip", "id": row_id, "date": date, "hand": hand, "kg": kg}


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
            INSERT INTO exercise_sessions (date, logged_at, sport, detail, minutes, sets, reported_tod, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, logged_at, sport, detail, minutes, len(sets_data) if sets_data else None, reported_tod, source),
        )
        session_id = cur.lastrowid
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
                INSERT INTO exercise_sets (
                  session_id, date, logged_at, exercise, pattern_group, role, set_index,
                  weight_kg, bodyweight_kg, total_load_kg, reps, rpe, rir, rest_sec,
                  e1rm_kg, e1rm_is_inferred, quality_note, pain_flag, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
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
    return {"ok": True, "activity_id": session_id, "sets_logged": inserted_sets, "date": date, "logged_at": logged_at}


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
            INSERT INTO diet_entries (date, logged_at, meal, kcal, protein_g, carb_g, fat_g, items, is_training_day, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, logged_at, meal, kcal, protein_g, carb_g, fat_g, items, is_training_day, source),
        )
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "table": "diet_entries", "id": row_id, "date": date, "meal": meal, "kcal": kcal}


def log_custom(
    root: Path,
    date: str,
    kind: str,
    value_num: float | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    domain: str | None = None,
    source: str = "manual",
    ext: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """万能扩展入口：任何尚未建模的记录类型先进 meta_observations。"""
    dt.date.fromisoformat(date)
    kind = kind.strip()
    if not kind:
        raise ValueError("kind 不能为空（同一类记录用同一个词）")
    if domain is not None and domain not in ("body", "exercise", "diet", "meta"):
        raise ValueError("domain 必须是 body / exercise / diet / meta")
    path = init_db(root)
    logged_at = now_local_str()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            """
            INSERT INTO meta_observations (date, logged_at, domain, kind, value_num, value_text, unit, source, ext)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (date, logged_at, domain, kind, value_num, value_text, unit, source,
             json.dumps(ext, ensure_ascii=False) if ext else None),
        )
        conn.commit()
        row_id = cur.lastrowid
    finally:
        conn.close()
    return {"ok": True, "table": "meta_observations", "id": row_id, "date": date, "kind": kind}


def ingest_device_payloads(
    root: Path,
    day: str,
    history_days: int,
    wellness_payload: dict[str, Any] | None = None,
    activities_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把只读 VitalDock JSON 落进设备表；不触碰手记表。metric 词表开放，未知数值指标透传。"""
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
                seen: set[str] = set()
                candidates: list[tuple[str, str]] = list(KNOWN_DEVICE_METRICS)
                for key, value in metrics_map.items():
                    if key in {m for m, _ in KNOWN_DEVICE_METRICS} or key in ("date", "id", "updated", "upstream_updated"):
                        continue
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        candidates.append((key, ""))
                for metric, unit in candidates:
                    if metric in seen:
                        continue
                    seen.add(metric)
                    val = metrics_map.get(metric)
                    if val is None or isinstance(val, bool):
                        continue
                    conn.execute(
                        """
                        INSERT INTO body_device_daily (date, metric, value, unit, source, upstream_updated, fetched_at)
                        VALUES (?, ?, ?, ?, 'intervals_wellness_merged', ?, ?)
                        ON CONFLICT(date, metric) DO UPDATE SET
                          value = excluded.value,
                          unit = excluded.unit,
                          upstream_updated = excluded.upstream_updated,
                          fetched_at = excluded.fetched_at
                        """,
                        (rec_date, metric, float(val), unit or None, upstream_updated, fetched_at),
                    )
                    daily_upserted += 1
            conn.execute(
                """
                INSERT INTO meta_device_fetch (fetched_at, tool, day, history_days, status, n_records)
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
                    INSERT INTO exercise_device_sessions (
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
                INSERT INTO meta_device_fetch (fetched_at, tool, day, history_days, status, n_records)
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
    """多信号准备度：个人滚动基线（前 4..28 天）对照最近 1..3 天。

    - 单指标不独裁（反 nocebo）：单日单指标波动保持 green，用热身组现场核实；
    - yellow 需要 ≥2 项指标连续偏离（或 1 项持续 + 表现漂移）；
    - red 需要多维持续偏离（≥4 天级）或疼痛/连续表现下滑。
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

    # 1. HRV 对照个人滚动基线（无 HRV 数据源时该信号自动缺席）
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

    # 2. 静息心率对照个人滚动基线
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

    # 3. 晨起握力对照个人滚动基线
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

    # 4. 睡眠时长（手记与设备并排核对，取两者更差值，不合并覆盖）
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

    # 5. 近期逐组记录的疼痛标记与 RPE 漂移
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

    # 分流
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
        exercise_recent = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM v_exercise_day WHERE date >= ? ORDER BY date ASC",
                (cutoff_recent,),
            ).fetchall()
        ]
        recent_sets = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, exercise, pattern_group, role, set_index, weight_kg, bodyweight_kg,
                       total_load_kg, reps, rpe, rir, rest_sec, e1rm_kg, e1rm_is_inferred, quality_note, pain_flag
                FROM exercise_sets
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
                FROM diet_entries
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
        "exercise_overview": exercise_recent,
        "readiness": readiness,
        "recent_workout_sets": recent_sets,
        "daily_intake": daily_intake,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keshig 统一记录库：身体/运动/饮食三域，手记与设备分表并排")
    subs = parser.add_subparsers(dest="command", required=True)

    p_init = subs.add_parser("init")
    p_init.add_argument("--root", default=None)

    p_migrate = subs.add_parser("migrate")
    p_migrate.add_argument("--root", default=None)

    for cmd_name in ("log-vitals", "body"):
        p_vitals = subs.add_parser(cmd_name)
        p_vitals.add_argument("--root", default=None)
        p_vitals.add_argument("--date", default=dt.date.today().isoformat())
        p_vitals.add_argument("--weight-kg", type=float)
        p_vitals.add_argument("--body-fat-pct", type=float)
        p_vitals.add_argument("--waist-cm", type=float)
        p_vitals.add_argument("--chest-cm", type=float)
        p_vitals.add_argument("--sleep-h", type=float)
        p_vitals.add_argument("--measured-at", default="morning_fasted")
        p_vitals.add_argument("--device")
        p_vitals.add_argument("--source", default="manual")
        p_vitals.add_argument("--ext-json", help="扩展字段 JSON 对象")

    p_grip = subs.add_parser("log-grip")
    p_grip.add_argument("--root", default=None)
    p_grip.add_argument("--date", default=dt.date.today().isoformat())
    p_grip.add_argument("--hand", choices=("right", "left"), required=True)
    p_grip.add_argument("--kg", type=float, required=True)
    p_grip.add_argument("--trial", type=int, default=1)
    p_grip.add_argument("--device")
    p_grip.add_argument("--protocol")
    p_grip.add_argument("--measured-at", default="morning")
    p_grip.add_argument("--note")

    for cmd_name in ("log-workout", "exercise"):
        p_workout = subs.add_parser(cmd_name)
        p_workout.add_argument("--root", default=None)
        p_workout.add_argument("--date", default=dt.date.today().isoformat())
        p_workout.add_argument("--sport", default="力量")
        p_workout.add_argument("--detail")
        p_workout.add_argument("--minutes", type=int)
        p_workout.add_argument("--reported-tod")
        p_workout.add_argument("--sets-json", help="JSON array of set objects")

    for cmd_name in ("log-intake", "diet"):
        p_intake = subs.add_parser(cmd_name)
        p_intake.add_argument("--root", default=None)
        p_intake.add_argument("--date", default=dt.date.today().isoformat())
        p_intake.add_argument("--meal", required=True)
        p_intake.add_argument("--kcal", type=float, required=True)
        p_intake.add_argument("--protein-g", type=float)
        p_intake.add_argument("--carb-g", type=float)
        p_intake.add_argument("--fat-g", type=float)
        p_intake.add_argument("--items")
        p_intake.add_argument("--is-training-day", type=int, choices=(0, 1))

    for cmd_name in ("log-custom", "meta"):
        p_custom = subs.add_parser(cmd_name)
        p_custom.add_argument("--root", default=None)
        p_custom.add_argument("--date", default=dt.date.today().isoformat())
        p_custom.add_argument("--kind", required=True, help="记录类型词，同类记录用同一个词，如 fatigue_score")
        p_custom.add_argument("--value-num", type=float)
        p_custom.add_argument("--value-text")
        p_custom.add_argument("--unit")
        p_custom.add_argument("--domain", choices=("body", "exercise", "diet", "meta"))
        p_custom.add_argument("--ext-json", help="扩展字段 JSON 对象")

    p_sync = subs.add_parser("sync-device")
    p_sync.add_argument("--root", default=None)
    p_sync.add_argument("--day", default=dt.date.today().isoformat())
    p_sync.add_argument("--history-days", type=int, default=28)
    p_sync.add_argument("--limit", type=int, default=20)
    p_sync.add_argument("--timeout", type=float, default=120)

    p_query = subs.add_parser("query-context")
    p_query.add_argument("--root", default=None)
    p_query.add_argument("--days", type=int, default=14)

    args = parser.parse_args(argv)
    root = system.resolve_root(args.root)
    system.load_config_readonly(root)

    if args.command == "init":
        path = init_db(root)
        print(json.dumps({"ok": True, "db_path": str(path), "schema_version": SCHEMA_VERSION}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "migrate":
        print(json.dumps(migrate_db(root), ensure_ascii=False, indent=2))
        return 0
    if args.command in ("log-vitals", "body"):
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
            ext=json.loads(args.ext_json) if args.ext_json else None,
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
    if args.command in ("log-workout", "exercise"):
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
    if args.command in ("log-intake", "diet"):
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
    if args.command in ("log-custom", "meta"):
        res = log_custom(
            root,
            args.date,
            args.kind,
            value_num=args.value_num,
            value_text=args.value_text,
            unit=args.unit,
            domain=args.domain,
            ext=json.loads(args.ext_json) if args.ext_json else None,
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
