-- 怯薛 · 统一记录库 schema v2 —— 手记侧（人报的）
-- 三域结构：身体 body_* ｜ 运动 exercise_* ｜ 饮食 diet_* ｜ 跨域 meta_*
-- 设备侧（表测的）在 device.sql，两域物理分表，对照只放在视图里并排。
--
-- 通则：
--   1. 除 date 等主键外字段一律可空（八段锦/走路这类记录无设备、无时长）。
--   2. 时间戳一律取落库机器值，不是用户输入的钟点。
--   3. 每张表带 ext JSON 列：新字段先进 ext，被广泛使用后才提升为正式列（需升 user_version）。
--   4. 全新类型的记录先进 meta_observations，不为其单独建表。
--   5. 只存结构化后的值，不存用户原话副本；用户报的时段原词除外（reported_tod 单列原样存）。
--
-- 版本治理：PRAGMA user_version = 2。迁移幂等，由 health_db.py 自动执行。

PRAGMA journal_mode = WAL;

-- ═══════════════ 域 1：身体（手记） ═══════════════

-- 体征读数：体重/体脂/围度/手记睡眠
CREATE TABLE IF NOT EXISTS body_vitals (
  date          TEXT NOT NULL,        -- YYYY-MM-DD
  logged_at     TEXT NOT NULL,        -- 机器值：落库时刻 YYYY-MM-DD HH:MM:SS
  weight_kg     REAL,
  body_fat_pct  REAL,
  visceral      REAL,                 -- 内脏脂肪等级（体脂仪若有）
  waist_cm      REAL,
  chest_cm      REAL,
  sleep_h       REAL,                 -- 手记睡眠时长（与设备睡眠分表并排）
  measured_at   TEXT,                 -- 'morning_fasted' | 'evening' | 'unknown'
  device        TEXT,                 -- 秤的品牌型号
  source        TEXT,                 -- 'scale_export' | 'manual'
  ext           TEXT CHECK (ext IS NULL OR json_valid(ext)),  -- 扩展字段 JSON
  PRIMARY KEY (date, source)
);

-- 晨起握力（恢复自调节信号之一）
CREATE TABLE IF NOT EXISTS body_grip (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  hand        TEXT NOT NULL,          -- 'right' | 'left'
  trial       INTEGER,
  kg          REAL NOT NULL,
  device      TEXT,
  protocol    TEXT,                   -- 测量条件（站姿/晨起等），条件不固定的读数不参与趋势
  measured_at TEXT,
  source      TEXT,
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_body_grip_date ON body_grip(date);

-- ═══════════════ 域 2：运动（手记） ═══════════════

-- 训练场次：一行为一场；detail 是结构化摘要，不是原话副本
CREATE TABLE IF NOT EXISTS exercise_sessions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  sport       TEXT NOT NULL,          -- 力量|跑步|游泳|球类|骑行|八段锦|走路|…（自由文本）
  detail      TEXT,                   -- 结构化摘要（动作 重量 组×次，竖线分隔）
  minutes     INTEGER,
  load_kg     REAL,
  sets        INTEGER,
  reps        INTEGER,
  witness     INTEGER,                -- 1=有人一起/有教练；0=独练；NULL=未说
  slot_id     INTEGER,                -- 命中的钉死时段；NULL=未命中
  reported_tod TEXT,                  -- 用户报的时段原词（'早上'/'昨天晚上 9点~10点'），原样存，不换算
  source      TEXT,
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_exercise_sessions_date ON exercise_sessions(date);

-- 逐组力量记录（用户给得出逐组数据时才写；空着不代表没练，看 exercise_sessions）
CREATE TABLE IF NOT EXISTS exercise_sets (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id       INTEGER,           -- 关联 exercise_sessions(id)；可空以兼容独立逐组落账
  date             TEXT NOT NULL,
  logged_at        TEXT NOT NULL,
  exercise         TEXT NOT NULL,     -- 动作标准名（如 '杠铃卧推' | '负重引体'）
  pattern_group    TEXT,              -- '蹲' | '髋铰链' | '推' | '拉' | '单腿' | '核心'
  role             TEXT DEFAULT 'work',-- 'warmup' | 'top' | 'backoff' | 'work' | 'technique'
  set_index        INTEGER NOT NULL,
  weight_kg        REAL,              -- 外部器械负重或附加重量 kg
  bodyweight_kg    REAL,              -- 自重负重动作当日体重 kg（未知留空，不猜）
  total_load_kg    REAL,              -- 总系统负荷 = bodyweight_kg + weight_kg
  reps             INTEGER,
  rpe              REAL,              -- 逐组实际 RPE（1-10）
  rir              REAL,              -- 逐组实际 RIR
  rest_sec         INTEGER,           -- 实际组间休息（区别于计划休息）
  e1rm_kg          REAL,              -- Epley 粗算 e1RM（仅 reps + rir <= 12 时推算）
  e1rm_is_inferred INTEGER DEFAULT 1, -- 1=公式推断；0=实测 1RM（推断与实测分开标明）
  quality_note     TEXT,              -- 动作标准/幅度/停顿备注（结构化短语）
  pain_flag        INTEGER DEFAULT 0, -- 1=出现不适/疼痛中止
  source           TEXT DEFAULT 'manual',
  ext              TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_date ON exercise_sets(date);
CREATE INDEX IF NOT EXISTS idx_exercise_sets_ex   ON exercise_sets(exercise, date);

-- ═══════════════ 域 3：饮食（手记） ═══════════════

-- 确认摄入：只有用户确认后才入账；meal 是自由文本（早餐/午餐/下午/睡前/训练后…）
CREATE TABLE IF NOT EXISTS diet_entries (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,
  meal        TEXT,                   -- 自由文本，不硬编码餐别枚举
  kcal        REAL,
  protein_g   REAL,
  carb_g      REAL,
  fat_g       REAL,
  items       TEXT,                   -- 结构化条目清单（非原话副本）
  is_training_day INTEGER,            -- 1/0/NULL，对照计划书日型
  source      TEXT,                   -- 'confirmed_nutrition' | …
  ext         TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_entries_date ON diet_entries(date);

-- 常用食物条目估值库：重复出现的条目固定估值，长期用体重趋势反向校正
CREATE TABLE IF NOT EXISTS diet_food_est (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  item      TEXT UNIQUE NOT NULL,     -- 结构化条目名
  unit      TEXT,                     -- '1 杯' | '1 个' | '100 g' | '1 份'
  kcal      REAL, protein_g REAL, carb_g REAL, fat_g REAL,
  basis     TEXT,                     -- '常见值' | '食堂估' | '称重'
  n_obs     INTEGER DEFAULT 1,        -- 已知出现次数
  last_seen TEXT,
  note      TEXT,
  ext       TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_food_est_item ON diet_food_est(item);

-- 每日摄入目标（源自用户确认的计划书；改口径先改计划书）
CREATE TABLE IF NOT EXISTS diet_targets (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  effective_date TEXT NOT NULL,       -- 该口径从哪天起生效
  day_type       TEXT NOT NULL,       -- '训练日' | '非训练日'
  kcal_min       REAL, kcal_max REAL,
  protein_min    REAL, protein_max REAL,
  carb_min       REAL, carb_max REAL,
  fat_min        REAL, fat_max REAL,
  water_l_min    REAL, water_l_max REAL,
  staple_min     REAL, staple_max REAL,
  source         TEXT,                -- 出处，如 '减脂计划.md §二'
  note           TEXT,
  logged_at      TEXT NOT NULL,
  ext            TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_diet_targets_date ON diet_targets(effective_date);

-- ═══════════════ 跨域 meta ═══════════════

-- 口径快照：每行带条件与生效日期；口径变了另起一行，不覆盖旧行
CREATE TABLE IF NOT EXISTS meta_assumptions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  key            TEXT NOT NULL,       -- bmr|tdee_factor|expected_loss|machine_display_bias|…
  value          TEXT NOT NULL,
  condition      TEXT,                -- 该值成立的条件/前提
  effective_date TEXT NOT NULL,
  logged_at      TEXT NOT NULL,
  note           TEXT,
  ext            TEXT CHECK (ext IS NULL OR json_valid(ext))
);

-- 万能扩展记录：任何尚未建模的数据类型先进这里
-- 例：主观疲劳 kind='fatigue_score' value_num=7 unit='1-10'；血压 kind='blood_pressure' value_text='120/80'
CREATE TABLE IF NOT EXISTS meta_observations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  date       TEXT NOT NULL,
  logged_at  TEXT NOT NULL,
  domain     TEXT,                    -- 'body' | 'exercise' | 'diet' | 'meta'
  kind       TEXT NOT NULL,           -- 记录类型（自由文本，同一类用同一个词）
  value_num  REAL,
  value_text TEXT,
  unit       TEXT,
  source     TEXT,
  ext        TEXT CHECK (ext IS NULL OR json_valid(ext))
);
CREATE INDEX IF NOT EXISTS idx_meta_observations_date ON meta_observations(date);
CREATE INDEX IF NOT EXISTS idx_meta_observations_kind ON meta_observations(kind, date);

-- 钉死的时点（用户自己钉，怯薛只登记；开口只在这些窗口内）
--   分母 = 所有 state IN ('pending','hit','expired') 的时点。
--   active 只是「还接不接受未来的发生」，不参与判定——默认值不许把分母清零。
CREATE TABLE IF NOT EXISTS meta_slots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  weekday         INTEGER,            -- 0=周一 … 6=周日；NULL=一次性
  occurrence_date TEXT,
  time_hhmm       TEXT,
  raw_text        TEXT,               -- 原样存。容量上限＝一个时点短语
  sport           TEXT,
  state           TEXT NOT NULL DEFAULT 'pending',  -- pending|hit|expired|void
  active          INTEGER DEFAULT 1,
  created_at      TEXT,
  ext             TEXT CHECK (ext IS NULL OR json_valid(ext))
);

-- 沟通台账：只记开口与回执计数，不记「未回应账」
CREATE TABLE IF NOT EXISTS meta_coach_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  kind      TEXT,                     -- 'echo' | 'confirm' | 'weekly' | 'receipt'
  slot_id   INTEGER,
  replied   INTEGER DEFAULT 0,
  ext       TEXT CHECK (ext IS NULL OR json_valid(ext))
);
