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
