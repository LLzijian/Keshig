-- 怯薛 · 设备数据层（schema v2 增补，2026-10-27）
-- 来源：VitalDock 只读接口（路径由 VITALDOCK_HOME 或同级目录探测决定）→ Intervals.icu → 华为运动健康
-- 原则：设备数据单独成表，不写进 vitals/activity。理由：
--   1) vitals/activity 存的是「他报的」，设备存的是「表测的」，两条来源不能静默合并成一条；
--   2) 同一天手记的训练与手表记的训练会各说各的时长，合并即等于替用户裁决；
--   3) 设备值会被上游修订（updated 字段），upsert 覆盖需要留 fetched_at 痕迹。

CREATE TABLE IF NOT EXISTS device_daily (
  date             TEXT NOT NULL,        -- 本人当地日期 YYYY-MM-DD（wellness 的 id）
  metric           TEXT NOT NULL,        -- resting_hr|sleep_secs|sleep_score|ctl|atl|hrv|hrv_sdnn
  value            REAL,
  unit             TEXT,
  source           TEXT,                 -- intervals_wellness_merged（来源未逐字段解析）
  upstream_updated TEXT,                 -- 平台该行的 updated
  fetched_at       TEXT NOT NULL,        -- 本次读取时刻（UTC）
  PRIMARY KEY (date, metric)
);

CREATE TABLE IF NOT EXISTS device_activity (
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
  fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS device_fetch (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  fetched_at   TEXT NOT NULL,
  tool         TEXT,                     -- check_connection|recent_activities|wellness_context
  day          TEXT,
  history_days INTEGER,
  status       TEXT,
  n_records    INTEGER,
  note         TEXT
);

-- 只读视图：设备侧每日一行，用于和 vitals 并排看，不做合并
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


-- ── 握力（用户晨起自测，2026-10-27 起）────────────────────────────
-- 逐次留档：同一天每手可多次，best/mean 由脚本算，不手工填。
-- 口径未定时 device/protocol 留空，不许猜。
CREATE TABLE IF NOT EXISTS grip (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,          -- 测量日 YYYY-MM-DD
  logged_at   TEXT NOT NULL,          -- 机器值：落库时刻
  hand        TEXT NOT NULL,          -- right|left
  trial       INTEGER,                -- 第几次（1,2,3…）
  kg          REAL NOT NULL,
  device      TEXT,                   -- 握力计型号，未知留空
  protocol    TEXT,                   -- 姿势/次数约定，未知留空
  measured_at TEXT,                   -- morning|evening|unknown
  source      TEXT,                   -- manual
  note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_grip_date ON grip(date);
