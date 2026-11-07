-- CON-14/CON-16 (T7.8, T2.5) : journaux des exports et des sauvegardes techniques.
-- Aucun secret n'y est stocke (OSIA-I-12) : metadonnees uniquement (dates, perimetres, empreintes).

CREATE TABLE IF NOT EXISTS exports (
  id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  format text NOT NULL CHECK (format IN ('osia','html','both')),
  investigation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  branch_ids jsonb,
  exclusions jsonb NOT NULL DEFAULT '[]'::jsonb,
  include_proofs boolean NOT NULL DEFAULT true,
  encrypted boolean NOT NULL DEFAULT false,
  partial boolean NOT NULL DEFAULT false,
  manifest_sha256 text,
  counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  files jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS backups (
  id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  kind text NOT NULL DEFAULT 'manual' CHECK (kind IN ('manual','pre_restore')),
  dest_dir text NOT NULL,
  manifest_sha256 text,
  db_dump_sha256 text,
  schema_version integer,
  proof_files_count integer NOT NULL DEFAULT 0,
  size_bytes bigint NOT NULL DEFAULT 0,
  verified_at timestamptz,
  verify_errors jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS backups_created_idx ON backups (created_at DESC);
