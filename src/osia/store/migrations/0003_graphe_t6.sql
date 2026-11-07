-- CON-09 / CON-10 (T6) : graphe, identite, decisions humaines supervisees, etayage.
-- Complete le schema v1 par ALTER/CREATE uniquement : aucune donnee n'est reecrite ni supprimee.

ALTER TABLE entities ADD COLUMN IF NOT EXISTS merged_into text REFERENCES entities(id);
ALTER TABLE entities ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS entities_investigation_kind_idx ON entities (investigation_id, kind);
CREATE INDEX IF NOT EXISTS entities_merged_idx ON entities (investigation_id, merged_into) WHERE merged_into IS NOT NULL;

CREATE TABLE IF NOT EXISTS entity_identifiers (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  entity_id text NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  scheme text NOT NULL,
  value_normalisee text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (investigation_id, scheme, value_normalisee)
);
CREATE INDEX IF NOT EXISTS entity_identifiers_entity_idx ON entity_identifiers (entity_id);

CREATE TABLE IF NOT EXISTS match_proposals (
  id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  entity_a text NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  entity_b text NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  basis text NOT NULL CHECK (basis IN ('exact_identifier','similarity','cross_reference')),
  justification text NOT NULL DEFAULT '',
  confidence text NOT NULL DEFAULT 'faible' CHECK (confidence IN ('haute','moyenne','faible')),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','validated','rejected')),
  decided_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (entity_a <> entity_b)
);
CREATE INDEX IF NOT EXISTS match_proposals_investigation_idx ON match_proposals (investigation_id, status);

ALTER TABLE relations ADD COLUMN IF NOT EXISTS branch_id text REFERENCES branches(id) ON DELETE SET NULL;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS direction text NOT NULL DEFAULT 'none' CHECK (direction IN ('out','in','none'));
ALTER TABLE relations ADD COLUMN IF NOT EXISTS valid_from date;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS valid_to date;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS proof_ids jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS support_level text NOT NULL DEFAULT 'a_confirmer' CHECK (support_level IN ('documente','corrobore','a_confirmer','contradictoire','non_etabli'));
ALTER TABLE relations ADD COLUMN IF NOT EXISTS human_decision text NOT NULL DEFAULT 'unexamined' CHECK (human_decision IN ('unexamined','validated','rejected'));
ALTER TABLE relations ADD COLUMN IF NOT EXISTS match_proposal_id text REFERENCES match_proposals(id) ON DELETE SET NULL;
ALTER TABLE relations ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS relations_src_idx ON relations (investigation_id, src_id);
CREATE INDEX IF NOT EXISTS relations_dst_idx ON relations (investigation_id, dst_id);
CREATE INDEX IF NOT EXISTS relations_type_idx ON relations (investigation_id, type);

ALTER TABLE assertions ADD COLUMN IF NOT EXISTS support_level text NOT NULL DEFAULT 'a_confirmer' CHECK (support_level IN ('documente','corrobore','a_confirmer','contradictoire','non_etabli'));
ALTER TABLE assertions ADD COLUMN IF NOT EXISTS confidence jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE assertions ADD COLUMN IF NOT EXISTS superseded_by text REFERENCES assertions(id);
ALTER TABLE assertions ADD COLUMN IF NOT EXISTS contradicted_by jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE assertions ADD COLUMN IF NOT EXISTS decisive boolean NOT NULL DEFAULT false;
ALTER TABLE assertions ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS assertions_investigation_idx ON assertions (investigation_id, branch_id);

ALTER TABLE decisions ADD COLUMN IF NOT EXISTS target_type text NOT NULL DEFAULT 'assertion' CHECK (target_type IN ('entity','relation','assertion','match_proposal'));
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS target_id text;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS reverts text REFERENCES decisions(id);
CREATE INDEX IF NOT EXISTS decisions_investigation_idx ON decisions (investigation_id, created_at);

ALTER TABLE proof_refs ADD COLUMN IF NOT EXISTS connector_id text;
