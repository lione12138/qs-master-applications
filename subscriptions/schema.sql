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

CREATE TABLE IF NOT EXISTS university_comments (
  id TEXT PRIMARY KEY,
  university_id TEXT NOT NULL,
  visitor_hash TEXT NOT NULL,
  author TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  hidden_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_university_comments_visible
  ON university_comments(university_id, created_at)
  WHERE hidden_at IS NULL;

DELETE FROM roadmap_proposals
WHERE source = 'owner'
  AND id IN ('application-planner', 'programme-comparison', 'deadline-reminders');

INSERT INTO roadmap_proposals (
  id, source, title_en, title_zh, description_en, description_zh,
  status, progress, created_at, hidden_at
) VALUES
  (
    'account-login-and-favorites', 'owner',
    'Account login and synced favourites', '个人注册登录与收藏',
    'Create an account to save favourite universities and programmes, then access them across devices.',
    '注册账号后收藏大学和项目，并在不同设备间同步查看。',
    'planned', 0, '2026-06-21T00:00:00Z', NULL
  ),
  (
    'wechat-mini-program', 'owner',
    'WeChat Mini Program', '微信小程序',
    'Bring application windows, saved schools, and deadline reminders into a lightweight WeChat experience.',
    '将申请窗口、收藏学校和截止提醒带到更轻量的微信使用场景。',
    'research', 0, '2026-06-21T00:00:00Z', NULL
  ),
  (
    'mobile-app', 'owner',
    'Mobile app', '手机 App',
    'Build a dedicated iOS and Android experience for quick browsing, saved items, and deadline notifications.',
    '开发 iOS 和 Android 应用，支持快速浏览、收藏与截止日期通知。',
    'planned', 0, '2026-06-21T00:00:00Z', NULL
  )
ON CONFLICT(id) DO UPDATE SET
  title_en = excluded.title_en,
  title_zh = excluded.title_zh,
  description_en = excluded.description_en,
  description_zh = excluded.description_zh,
  status = excluded.status,
  progress = excluded.progress,
  hidden_at = NULL;
