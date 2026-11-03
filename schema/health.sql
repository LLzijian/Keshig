-- 怯薛 · 健康与运动记录
-- 单文件、单写者。schema v1，2026-10-13。
-- 通则：除 date 与 sport 外，所有字段一律可空（八段锦/走路这类记录无设备、无时长、无对手）。
-- 通则：时间戳一律取机器值（落库时刻），不是用户输入。他不需要报钟点。

PRAGMA journal_mode = WAL;

-- 身体读数
CREATE TABLE IF NOT EXISTS vitals (
  date          TEXT NOT NULL,        -- YYYY-MM-DD
  logged_at     TEXT NOT NULL,        -- 机器值：落库时刻 YYYY-MM-DD HH:MM:SS
  weight_kg     REAL,
  body_fat_pct  REAL,
  visceral      REAL,                 -- 内脏脂肪等级（体脂仪若有）
  waist_cm      REAL,
  chest_cm      REAL,                 -- 胸围；2026-11-01 加（原 schema 无围度位）
  sleep_h       REAL,
  measured_at   TEXT,                 -- 'morning_fasted' | 'evening' | 'unknown'
  device        TEXT,                 -- 秤的品牌型号（Gate 0 之后才填得上）
  source        TEXT,                 -- 'scale_export' | 'manual'
  PRIMARY KEY (date, source)
);

-- 运动事件
CREATE TABLE IF NOT EXISTS activity (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,          -- 机器值：落库时刻（判定「是否落进钉死时段」用这一列）
  sport       TEXT NOT NULL,          -- 力量|跑步|游泳|球类|骑行|爬山|八段锦|走路|山间漫步|…
  detail      TEXT,                   -- 结构化摘要，不是原话副本
  minutes     INTEGER,
  load_kg     REAL,
  sets        INTEGER,
  reps        INTEGER,
  witness     INTEGER,                -- 1=有人一起/有教练；0=独练；NULL=未说
  slot_id     INTEGER,                -- 命中的钉死时段；NULL=未命中
  reported_tod TEXT,                  -- 他报的时段原词（'早上'/'晚上'/'周三'），原样存，不换算
  source      TEXT
);

-- 摄入
CREATE TABLE IF NOT EXISTS intake (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  logged_at   TEXT NOT NULL,          -- 机器值
  meal        TEXT,                   -- 早餐|午餐|训练前|训练后|加餐|晚餐
  kcal        REAL,
  protein_g   REAL,
  carb_g      REAL,
  fat_g       REAL,
  items       TEXT,                   -- 结构化条目清单（非原话副本）
  is_training_day INTEGER,            -- 1/0/NULL，对照减脂计划 §二 哪张表
  source      TEXT
);

-- 钉死的时点（他自己钉，怯薛只登记；开口只在这些窗口内）
--
-- 【判定语义 · 2026-10-13 定，@remy 报的默认值陷阱】
--   分母 = 所有 state IN ('pending','hit','expired') 的时点。
--   `active` 只是「还接不接受未来的发生」，**不参与判定**——默认值不许把分母清零。
--   一次性时点：钉下的那天 23:59 之前 state='pending'；之后
--     窗口内有落账 → 'hit'；窗口内无落账 → 'expired'（**expired 仍进分母**）。
--   'void' 只有两种来源：他自己撤回/改口，或该行是测试/误录 → 不进分母。
--   ⇒ 11-10 出表前必须先看这一格，别让一个默认值把整张表判空。
CREATE TABLE IF NOT EXISTS slots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  weekday         INTEGER,            -- 0=周一 … 6=周日；NULL=一次性
  occurrence_date TEXT,               -- 这一次的具体日期；一次性时点必填
  time_hhmm       TEXT,               -- 他自己报的原词优先，如 '20:00'
  raw_text        TEXT,               -- 原样存。容量上限＝一个时点短语，永不许长成叙述
  sport           TEXT,
  state           TEXT NOT NULL DEFAULT 'pending',  -- pending|hit|expired|void
  active          INTEGER DEFAULT 1,  -- 仅「是否还接受未来的发生」，不参与判定
  created_at      TEXT
);

-- 沟通台账：只记开口与回执的计数，不记「未回应账」
CREATE TABLE IF NOT EXISTS coach_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,            -- 机器值
  kind      TEXT,                     -- 'echo' | 'confirm' | 'weekly' | 'receipt'
  slot_id   INTEGER,
  replied   INTEGER DEFAULT 0         -- 用于统计「回了一行的次数」，不作为失败记账
);

-- 每日摄入目标（源自 减脂计划.md §二；不发明新目标，改口径先改计划书）
CREATE TABLE IF NOT EXISTS target (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  effective_date TEXT NOT NULL,      -- 该口径从哪天起生效
  day_type       TEXT NOT NULL,      -- '训练日' | '非训练日'
  kcal_min       REAL, kcal_max REAL,
  protein_min    REAL, protein_max REAL,
  carb_min       REAL, carb_max REAL,
  fat_min        REAL, fat_max REAL,
  water_l_min    REAL, water_l_max REAL,
  staple_min     REAL, staple_max REAL,  -- 主食份数
  source         TEXT,               -- 出处，如 '减脂计划.md §二'
  note           TEXT,
  logged_at      TEXT NOT NULL
);

-- 核算口径快照（每行带条件与生效日期；口径变了另起一行，不覆盖旧行）
CREATE TABLE IF NOT EXISTS assumption (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  key            TEXT NOT NULL,      -- activity_commute|steps_daily|training_freq|bmr|tdee_factor|expected_loss|protein_basis
  value          TEXT NOT NULL,
  condition      TEXT,               -- 该值的条件（口述日期／计算前提）
  effective_date TEXT NOT NULL,
  logged_at      TEXT NOT NULL,
  note           TEXT
);

-- 常用食物条目估值库：重复出现的条目固定估值，长期用体重趋势反向校正，不每次重估
CREATE TABLE IF NOT EXISTS food_est (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  item      TEXT UNIQUE NOT NULL,    -- 结构化条目名，不是原话副本
  unit      TEXT,                    -- '1 杯' | '1 个' | '100 g' | '1 份'
  kcal      REAL, protein_g REAL, carb_g REAL, fat_g REAL,
  basis     TEXT,                    -- '常见值' | '食堂估' | '称重'
  n_obs     INTEGER DEFAULT 1,       -- 已知出现次数
  last_seen TEXT,
  note      TEXT
);

CREATE INDEX IF NOT EXISTS idx_target_date   ON target(effective_date);
CREATE INDEX IF NOT EXISTS idx_food_est_item ON food_est(item);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity(date);
CREATE INDEX IF NOT EXISTS idx_intake_date   ON intake(date);
CREATE INDEX IF NOT EXISTS idx_vitals_date   ON vitals(date);
