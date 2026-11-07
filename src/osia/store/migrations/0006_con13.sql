-- CON-13 (D3/D7, T4.8, V1.4) : cache technique des requêtes source avec TTL configurable
-- (défaut 24 h, V1.4 ; B-ACC-06 : une requête équivalente réutilise un résultat valide).
-- Le cache est une donnée TECHNIQUE (D4 §6.2) : il n'est jamais promu en preuve ; les preuves
-- passent par store_proof avec leur propre politique de conservation.
CREATE TABLE IF NOT EXISTS source_cache (
  id            text PRIMARY KEY,
  connector_id  text NOT NULL,
  query_hash    text NOT NULL,
  result        jsonb NOT NULL,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS source_cache_key_idx ON source_cache (connector_id, query_hash);
CREATE INDEX IF NOT EXISTS source_cache_expires_idx ON source_cache (expires_at);
