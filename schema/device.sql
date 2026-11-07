-- 怯薛 · 统一记录库 schema v2 —— 设备侧（表测的）与并排视图
-- 来源：VitalDock 只读接口 → Intervals.icu → 华为运动健康
-- 原则：设备数据单独成表，不写进 body_*/exercise_* 手记表。理由：
--   1) 手记存的是「他报的」，设备存的是「表测的」，两条来源不能静默合并成一条；
--   2) 同一天手记的训练与手表记的训练会各说各的时长，合并即等于替用户裁决；
--   3) 设备值会被上游修订（updated 字段），upsert 覆盖需要留 fetched_at 痕迹。
-- 扩展规则与手记侧一致：新指标先进 ext JSON 或按 metric 行扩展；全新设备类型先进 meta_observations。

-- ═══════════════ 域 1：身体（设备） ═══════════════

-- 设备日指标：一行一个指标，新指标类型只需新增 metric 词，不改表结构
CREATE TABLE IF NOT EXISTS body_device_daily (
  date             TEXT NOT NULL,        -- 本人当地日期 YYYY-MM-DD（wellness 的 id）
  metric           TEXT NOT NULL,        -- resting_hr|sleep_secs|sleep_score|ctl|atl|hrv|hrv_sdnn|…（开放词表）
  value            REAL,
  unit             TEXT,
  source           TEXT,                 -- intervals_wellness_merged（来源未逐字段解析）
  upstream_updated TEXT,                 -- 平台该行的 updated
  fetched_at       TEXT NOT NULL,        -- 本次读取时刻（UTC）
  ext              TEXT CHECK (ext IS NULL OR json_valid(ext)),
  PRIMARY KEY (date, metric)
);
CREATE INDEX IF NOT EXISTS idx_body_device_daily_date ON body_device_daily(date);

-- 只读视图：设备侧每日一行，用于和手记并排看，不做合并
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

-- ═══════════════ 域 2：运动（设备） ═══════════════

CREATE TABLE IF NOT EXISTS exercise_device_sessions (
  activity_id       TEXT PRIMARY KEY,    -- 平台 ID，天然幂等键
  source            TEXT,                -- HUAWEI
  type              TEXT,                -- Workout|Run|…（原文，不翻译）
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

-- ═══════════════ 跨域 meta ═══════════════

-- 设备抓取台账
CREATE TABLE IF NOT EXISTS meta_device_fetch (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  fetched_at   TEXT NOT NULL,
  tool         TEXT,                     -- check_connection|recent_activities|wellness_context
  day          TEXT,
  history_days INTEGER,
  status       TEXT,
  n_records    INTEGER,
  note         TEXT,
  ext          TEXT CHECK (ext IS NULL OR json_valid(ext))
);

-- ═══════════════ 并排对照视图（唯一的「合并」发生地：只并排，不裁决） ═══════════════

-- 身体：手记体征 + 手记握力 vs 设备日指标
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
LEFT JOIN vitals_day       v   ON v.date   = d.date
LEFT JOIN grip_day         g   ON g.date   = d.date
LEFT JOIN v_body_device_day dev ON dev.date = d.date;

-- 运动：手记场次 vs 设备场次（人记 60 min 与表测 3020 s 各说各话，并排看）
CREATE VIEW IF NOT EXISTS v_exercise_day AS
WITH all_dates AS (
  SELECT date FROM exercise_sessions
  UNION
  SELECT substr(started_at_local, 1, 10) FROM exercise_device_sessions
),
manual_day AS (
  SELECT
    date,
    COUNT(*)        AS manual_sessions,
    GROUP_CONCAT(sport, '、') AS manual_sports,
    SUM(minutes)    AS manual_minutes
  FROM exercise_sessions
  GROUP BY date
),
device_day AS (
  SELECT
    substr(started_at_local, 1, 10)        AS date,
    COUNT(*)                               AS device_sessions,
    GROUP_CONCAT(type, '、')                AS device_types,
    ROUND(SUM(moving_time_s) / 60.0, 1)    AS device_minutes,
    ROUND(AVG(avg_hr), 1)                  AS device_avg_hr,
    ROUND(SUM(training_load), 1)           AS device_training_load
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
