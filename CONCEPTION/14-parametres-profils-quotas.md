# CON-13 — Paramètres hiérarchisés, profils, valeurs par défaut, TTL et quotas

**Exigences** : D3 §5 (profils préconfigurés personnalisables, paramètres ajustables, hiérarchie des budgets global → investigation → branche → opération, avertissements à l'approche d'un plafond, validation explicite pour toute augmentation), D7 §9 (paramètres hiérarchisés : globaux → profil → investigation → branche ; chaque niveau respecte les plafonds supérieurs ; pas de rétroactivité sur les investigations en cours ; validation avant enregistrement ; historique des modifications), T4.8 (garde-fous effectifs non désactivables par une simple instruction), PERIMETRE-V1 §V1.4 (profils rapide/standard/approfondi présaisis, budget 0 € au premier démarrage puis plafond global 5 €/mois, 2 opérations externes simultanées, 15 s HTTP / 60 s IA, cache de requêtes 24 h), D4 §6 (cache technique à TTL configurable, distinct des preuves). Vérification attendue (CONCEPTION-RESTANTE) : *defaults non permissifs par accident ; restrictions supérieures appliquées*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. Les profils V1.4 existaient déjà (migration 0002) ; CON-13 ajoute le clamp des surcharges, le cache TTL, les paramètres globaux administrables et les alertes de plafonds.

## 1. Surcharge des limites : clamp, jamais au-dessus (D3 §5.4, D7 §9.2, T4.8)

- `limits_from_profile_row` (policies/limits.py) : les `limits` d'une requête de création d'investigation ou de branche sont **clamés** (`min(demande, profil)`) sur chaque champ — un override ne peut jamais augmenter une limite au-delà du profil choisi ni des garde-fous V1.4 (`max_concurrent_external_ops=2`, `http_timeout_seconds=15`, `ai_timeout_seconds=60`). Les valeurs hors bornes du schéma (`LimitSet` ge/le, ex. rebonds 1–10) sont rejetées par validation pydantic.
- Branche : une **demande** explicite au-dessus du plafond de l'investigation parente est **refusée** (`plafond_branche_superieur:<champ>`), pas clampée silencieusement (préserve le comportement livré en tranche 2) ; les limites stockées restent en outre vérifiées ≤ investigation.
- Conséquence : aucun default permissif par accident — le profil rapide reste à 2 rebonds / 5 c même si la requête demande 10 / 999.

## 2. Cache technique des requêtes source — TTL 24 h (V1.4, B-ACC-06, D4 §6)

- Migration `0006_con13.sql` : table `source_cache(connector_id, query_hash, result, fetched_at, expires_at)`, clé unique `(connector_id, query_hash)` (hash SHA-256 de `connecteur + requête normalisée`).
- `handle_source_query` (tasks.py) consulte le cache **avant** toute autorisation d'opération externe : un hit valide retourne le résultat avec `cached: true` et la fraîcheur (`fetched_at`/`expires_at`, D4 §6.2) **sans nouvel appel externe** (B-ACC-06) ; un miss déclenche l'appel, stocke la preuve (store_proof, inchangé) et alimente le cache.
- TTL configurable : paramètre global `source_cache_ttl_hours` (défaut **24 h**, V1.4), minimum 1 h. Purge manuelle `cache_purge_expired` (D4 §6.1.B : le cache est une donnée technique, jamais promue en preuve).

## 3. Paramètres globaux administrables (D7 §9.1–9.3)

- Schéma `EDITABLE_SETTINGS` (models.py) : `paid_calls_enabled` (défaut **false** — V1.4 budget 0 € au premier démarrage), `global_monthly_cap_cents` (défaut 500 = 5 €/mois présaisi V1.4), `timezone`, `source_cache_ttl_hours` (24), `audit_retention_days`, `session_ttl_hours`. **Aucun secret n'est modifiable ici** (les secrets restent dans le coffre CON-06).
- `validate_setting_value` : vérification de validité (type + bornes) **avant** enregistrement (D7 §9.3).
- API : `GET /api/v1/settings`, `PUT /api/v1/settings` (persisté en table `settings`, appliqué au runtime — rétention d'audit, TTL de session — et **audité** `op.settings.update`). CLI : `osia settings list|set <key> <value>`.
- Hiérarchie appliquée (D7 §9.2) : les paramètres globaux s'appliquent aux **futures** opérations ; les investigations en cours conservent leurs `effective_limits` figées (pas de rétroactivité, REC-D7-01) ; un plafond global restrictif bloque les futures opérations via les caps du BudgetManager.

## 4. Alertes de plafonds (D3 §5.4)

- `BudgetView.warnings` (budgets.py) : avertissement à partir de **80 %** d'un plafond (`plafond <scope> atteint à X %`), plus un avertissement explicite quand les appels payants sont désactivés (plafond global 0, V1.4). Exposé via `GET /api/v1/investigations/{id}/budget`.

## 5. Profils personnalisés (D3 §5.3)

- API `POST /api/v1/profiles` (création validée : `LimitSet` + CHECK SQL, unicité de l'id, un seul `is_default`), CLI `osia profiles list|create`. Audité (`op.profile.create`). Les profils V1.4 (rapide présélectionné / standard / approfondi) restent les préréglages.

## 6. Limites connues

- Le cache est par `(connecteur, requête)` : il ne déduplique pas sémantiquement (deux formulations proches = deux entrées) — la déduplication des contenus reste celle des preuves (SHA-256).
- Le TTL est global (24 h) ; le « ou plus tôt selon les règles de la source » (V1.4) n'est pas encore par-source (les fiches connecteurs portent `quotas`, pas de TTL individuelle).
- `test_budgets.py::test_concurrent_reservations_cannot_exceed_cap` échoue aussi sur `main` (concurrence, pré-existant) — non traité ici.

## 7. Vérifications réellement exécutées

- `pytest -q` : **145 tests passés** (1 désélectionné : `test_concurrent_reservations_cannot_exceed_cap`, défaillant aussi sur `main` avant cette tranche), dont **11 dans `tests/test_con13.py`** : clamp des overrides (jamais au-dessus du profil, garde-fous V1.4 non surchargeables à la hausse, abaissement possible, borne inférieure rejetée), `effective_limits` d'investigation clampées au profil, validation des settings (bornes, types, clé inconnue), cache set/get/expiration/purge, handler source qui réutilise le cache **sans second appel** (B-ACC-06), warnings de plafond à 80 % + avertissement « payants désactivés », API settings GET/PUT (400 invalide), API profiles create/400/409.
