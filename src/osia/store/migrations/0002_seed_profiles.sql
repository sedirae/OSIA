INSERT INTO profiles (id, name, max_rebonds, max_source_requests, max_ai_calls, max_duration_seconds, max_cost_cents, is_default)
VALUES
  ('rapide', 'Rapide', 2, 12, 4, 120, 5, true),
  ('standard', 'Standard', 4, 40, 12, 600, 20, false),
  ('approfondi', 'Approfondi', 8, 100, 30, 1800, 100, false)
ON CONFLICT (id) DO NOTHING;
