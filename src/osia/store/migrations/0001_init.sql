CREATE TABLE IF NOT EXISTS schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE profiles (
  id text PRIMARY KEY,
  name text NOT NULL,
  max_rebonds integer NOT NULL CHECK (max_rebonds BETWEEN 1 AND 10),
  max_source_requests integer NOT NULL CHECK (max_source_requests >= 0),
  max_ai_calls integer NOT NULL CHECK (max_ai_calls >= 0),
  max_duration_seconds integer NOT NULL CHECK (max_duration_seconds > 0),
  max_cost_cents integer NOT NULL CHECK (max_cost_cents >= 0),
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE investigations (
  id text PRIMARY KEY,
  title text NOT NULL,
  objective text,
  hints jsonb NOT NULL DEFAULT '[]'::jsonb,
  profile_id text NOT NULL REFERENCES profiles(id),
  effective_limits jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('created','running','suspended','stopped','error')),
  stop_reason text,
  idempotency_key text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE branches (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  parent_branch_id text REFERENCES branches(id),
  objective text NOT NULL,
  effective_limits jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('created','running','suspended','stopped','error')),
  stop_reason text,
  depth integer NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 10),
  idempotency_key text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  branch_id text REFERENCES branches(id) ON DELETE CASCADE,
  kind text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','claimed','running','succeeded','failed','cancelled','interrupted')),
  priority integer NOT NULL DEFAULT 0,
  depth integer NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 10),
  attempts integer NOT NULL DEFAULT 0,
  not_before timestamptz NOT NULL DEFAULT now(),
  idempotency_key text UNIQUE,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);
CREATE INDEX tasks_queue_idx ON tasks (priority DESC, created_at) WHERE state = 'queued';

CREATE TABLE external_ops (
  id text PRIMARY KEY,
  task_id text REFERENCES tasks(id) ON DELETE SET NULL,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('source_request','ai_call')),
  target text NOT NULL,
  is_paid boolean NOT NULL DEFAULT false,
  cost_estimated_cents integer,
  state text NOT NULL DEFAULT 'planned' CHECK (state IN ('planned','authorized','reserved','in_flight','completed','uncertain','reconciled','failed','cancelled')),
  reservation_id text,
  result jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX external_ops_investigation_idx ON external_ops (investigation_id, state);

CREATE TABLE reservations (
  id text PRIMARY KEY,
  idempotency_key text NOT NULL UNIQUE,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  branch_id text REFERENCES branches(id) ON DELETE CASCADE,
  provider text,
  model text,
  op_id text REFERENCES external_ops(id) ON DELETE SET NULL,
  amount_cents integer NOT NULL CHECK (amount_cents >= 0),
  state text NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved','consumed','released')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger (
  id bigserial PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  reservation_id text REFERENCES reservations(id) ON DELETE SET NULL,
  kind text NOT NULL CHECK (kind IN ('reserved','consumed','released','reconciled','adjustment')),
  amount_cents integer NOT NULL,
  period text NOT NULL,
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ledger_period_idx ON ledger (investigation_id, period);

CREATE TABLE events (
  id bigserial PRIMARY KEY,
  investigation_id text REFERENCES investigations(id) ON DELETE CASCADE,
  branch_id text REFERENCES branches(id) ON DELETE CASCADE,
  type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_investigation_idx ON events (investigation_id, id);

CREATE TABLE proof_files (
  sha256 text PRIMARY KEY,
  path text NOT NULL,
  size_bytes bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE proof_refs (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  proof_sha256 text NOT NULL REFERENCES proof_files(sha256),
  source_url text,
  media_type text,
  label text,
  fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX proof_refs_investigation_idx ON proof_refs (investigation_id);

CREATE TABLE entities (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  kind text NOT NULL,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE relations (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  src_id text NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  dst_id text NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  type text NOT NULL,
  status text NOT NULL DEFAULT 'hypothesis' CHECK (status IN ('confirmed','hypothesis','contradicted')),
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE assertions (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  branch_id text REFERENCES branches(id) ON DELETE CASCADE,
  statement text NOT NULL,
  nature text NOT NULL,
  support text NOT NULL,
  human_decision text NOT NULL DEFAULT 'unexamined' CHECK (human_decision IN ('unexamined','validated','rejected')),
  proof_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE decisions (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  assertion_id text REFERENCES assertions(id) ON DELETE SET NULL,
  action text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
