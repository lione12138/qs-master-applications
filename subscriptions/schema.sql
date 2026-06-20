CREATE TABLE IF NOT EXISTS subscribers (
  email_hash TEXT PRIMARY KEY,
  email_ciphertext TEXT,
  email_iv TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'unsubscribed')),
  confirmation_token_hash TEXT,
  confirmation_expires_at TEXT,
  created_at TEXT NOT NULL,
  confirmed_at TEXT,
  unsubscribed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscribers_confirmation
  ON subscribers(confirmation_token_hash)
  WHERE confirmation_token_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_subscribers_status
  ON subscribers(status, confirmed_at);

CREATE TABLE IF NOT EXISTS notification_events (
  event_key TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
  event_key TEXT NOT NULL,
  email_hash TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  PRIMARY KEY (event_key, email_hash),
  FOREIGN KEY (event_key) REFERENCES notification_events(event_key)
    ON DELETE CASCADE,
  FOREIGN KEY (email_hash) REFERENCES subscribers(email_hash)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roadmap_proposals (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('owner', 'community')),
  title_en TEXT NOT NULL,
  title_zh TEXT,
  description_en TEXT,
  description_zh TEXT,
  status TEXT NOT NULL DEFAULT 'planned'
    CHECK (status IN ('planned', 'research', 'in_progress', 'complete')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  created_at TEXT NOT NULL,
  hidden_at TEXT
);

CREATE TABLE IF NOT EXISTS roadmap_votes (
  proposal_id TEXT NOT NULL,
  visitor_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (proposal_id, visitor_hash),
  FOREIGN KEY (proposal_id) REFERENCES roadmap_proposals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roadmap_rate_limits (
  scope TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  bucket INTEGER NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scope, key_hash, bucket)
);

CREATE INDEX IF NOT EXISTS idx_roadmap_proposals_visible
  ON roadmap_proposals(source, created_at)
  WHERE hidden_at IS NULL;

INSERT OR IGNORE INTO roadmap_proposals (
  id, source, title_en, title_zh, description_en, description_zh,
  status, progress, created_at, hidden_at
) VALUES
  (
    'application-planner', 'owner',
    'Personal application planner', '个人申请计划表',
    'Turn saved programmes into a personal checklist with deadlines, materials, and progress.',
    '把收藏项目整理成个人清单，统一跟踪截止日期、申请材料和完成进度。',
    'planned', 15, '2026-06-20T00:00:00Z', NULL
  ),
  (
    'programme-comparison', 'owner',
    'Programme comparison', '项目对比',
    'Compare saved programmes by application dates, location, applicant group, and source coverage.',
    '按申请日期、地区、适用人群和来源覆盖情况对比收藏项目。',
    'research', 5, '2026-06-20T00:00:00Z', NULL
  ),
  (
    'deadline-reminders', 'owner',
    'Personal deadline reminders', '个人截止日期提醒',
    'Choose saved programmes and receive reminders before their verified deadlines.',
    '选择收藏项目，在已核验截止日期前收到提醒。',
    'in_progress', 35, '2026-06-20T00:00:00Z', NULL
  );
