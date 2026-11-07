# CON-18 — Journaux et rétentions : audit de sécurité, journal technique, historique métier

**Exigences** : C6 (journaux distincts et protégés), D4 §6 (conservation : le cache technique est à TTL et purgeable, le dossier d'investigation n'est jamais supprimé automatiquement, l'historique métier est conservé tant que l'investigation est conservée — §6.1.A/§6.5 règle intangible), T3.13 (journalisation structurée avec masquage des secrets), T5.9 (audit de sécurité distinct, sans secrets). Vérification attendue (CONCEPTION-RESTANTE) : *finalités distinctes ; secrets absents ; historique métier conservé*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. Trois **finalités distinctes**, trois supports distincts, trois rétentions distinctes — aucune confusion possible entre elles.

## 1. Les trois finalités (jamais confondues)

| Finalité | Support | Rétention | Purge |
| --- | --- | --- | --- |
| **Audit de sécurité** (T5.9) | `security-audit.jsonl` dans `log_dir`, 0600 | `audit_retention_days` (défaut 90 j) | à l'écriture + manuelle supervisée |
| **Journal technique** (T3.13) | `tech-YYYY-MM-DD.jsonl` dans `log_dir`, 0600 | `tech_log_retention_days` (défaut 30 j, `OSIA_TECH_LOG_RETENTION_DAYS`) | à l'écriture + manuelle supervisée |
| **Historique métier** (D4 §6.1.A) | tables `events`/`decisions`/`external_ops`/`ledger` en base | **aucune** — conservé tant que l'investigation est conservée (D4 §6.5) | **jamais automatique** |

- `GET /api/v1/logs` expose explicitement les trois finalités, avec `retention_days: null` et une note « jamais de purge automatique » pour l'historique métier.

## 2. Journal technique structuré (T3.13) — `src/osia/techlog.py`

- Entrées JSONL structurées : `ts`, `level`, `component`, `event` + identifiants de corrélation (`investigation_id`, `branch_id`, `task_id`, `op_id`), `duration_ms`, `error`, `detail`.
- **Masquage des secrets identique à l'audit** : même `_scrub` (security/audit.py) — clés sensibles de dictionnaires remplacées par `***`, motifs `clé=valeur`/`clé: valeur` masqués dans les chaînes libres (ex. `token=abcdef` → `token=***`), troncature à 256 caractères. Aucun secret n'est journalisé.
- Fichier 0600, `fsync` à chaque écrit. Rétention `tech_log_retention_days` (paramètre global éditable, borné ≥ 1, D7 §9.1), purge à l'écriture.
- Câblage : `engine.setup/start/stop`, chaque requête source (`tasks.source.query` avec durée et `http_status`), chaque appel IA (`ai.broker.ai.call` avec durée, cible, rôle, coût en centimes, erreur en niveau `error`).

## 3. Purges supervisées (C6, D4 §6) — jamais automatiques sur l'historique métier

- `POST /api/v1/logs/purge {kind: tech|audit, dry_run}` : `dry_run=true` (défaut) = prévisualisation (`expired_count`, sans rien supprimer) ; `dry_run=false` = purge réelle. **Chaque purge est elle-même auditée** (`op.logs.purge`, T5.9).
- `POST /api/v1/cache/purge {dry_run}` : prévisualisation des entrées/octets expirés du cache source, puis `repo.cache_purge_expired()` (D4 §6.1.B : le cache est technique, jamais nécessaire à la traçabilité — les preuves restent dans le dossier d'investigation). Audité (`op.cache.purge`).
- CLI équivalentes : `osia logs list --kind tech|audit`, `osia logs purge --kind … [--apply]`, `osia cache purge [--apply]` (dry-run par défaut, `--apply` explicite).
- L'audit de sécurité purge aussi à chaque écrit (rétention D4) ; `expired_count()`/`purge()` sont publics pour la supervision.

## 4. Limites connues

- La purge des journaux est **manuelle/supervisée** (dry-run par défaut) : aucune suppression automatique hors rétention à l'écriture pour l'audit/tech au-delà de la purge à l'écriture déjà en place ; l'historique métier n'est jamais purgé par le moteur.
- `expired_count` parcourt les fichiers JSONL (coût linéaire en taille de journal) — acceptable à l'échelle V1, à surveiller si les volumes explosent.
- Le masquage couvre les clés connues (`_SENSITIVE_KEYS`) et les motifs `clé=valeur` ; un secret exotique hors liste et hors motif dans une chaîne libre n'est pas détecté (troncature à 256 caractères seulement).

## 5. Vérifications réellement exécutées

- `pytest -q` : **157 tests passés** (1 défaillant : `test_concurrent_reservations_cannot_exceed_cap`, défaillant aussi sur `main` avant cette tranche), dont **11 dans `tests/test_con18.py`** : structure/corrélation/masquage du journal technique (clés sensibles `***`, motif `token=…` masqué dans une chaîne d'erreur, fichier 0600), purge + dry-run tech et audit, API `GET /api/v1/logs` (3 finalités, `retention_days: null` métier), API `logs/purge` dry-run vs réel + audit des purges, API `cache/purge` dry-run (entrées + octets) vs réel avec entrée valide conservée, **historique métier conservé après purges tech/audit/cache** (D4 §6.5), `tech_log_retention_days` visible dans `GET /api/v1/settings` et modifiable à chaud (400 si borne < 1), câblage effectif (`engine.setup` journalisé ; `source.query` journalisé avec durée/op_id/http_status).
