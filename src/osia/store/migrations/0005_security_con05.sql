-- CON-05 (T5.7) : sessions serveur authentifiées, expirables et révocables.
-- Seul le hash SHA-256 du jeton est stocké ; jamais le jeton en clair.
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    client_info TEXT
);
CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions (expires_at);
