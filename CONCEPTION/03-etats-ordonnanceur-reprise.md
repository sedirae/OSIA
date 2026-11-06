# CON-03 — Machine à états, ordonnanceur, concurrence, reprise et réconciliation

**Exigences** : T3.5/T3.6/T3.12, T4.2/T4.3/T4.7/T4.8, D7.4, OSIA-I-03/04/09, V1.1 (reprise après incident), V1.4 (2 opérations externes simultanées, timeouts 15 s HTTP / 60 s IA).
**Choix d'implémentation** : ordonnanceur persistant PostgreSQL par `SELECT … FOR UPDATE SKIP LOCKED`, sémaphore de concurrence, états explicites avec journal.

## 1. États et transitions

### Investigation / branche
`created → running ⇄ suspended → stopped` ; `running/suspended → error`.
`stopped` est terminal avec un **motif d'arrêt** (`stop_reason`) : `objective_suffisamment_etaye`, `depth_limit`, `budget_exhausted`, `sources_exhausted`, `user_interrupt`, `technical_error`, `security_block` (T4.6, A5).
Une branche ne démarre jamais automatiquement : création **uniquement sur validation explicite** des limites et du budget (T4.3, V1.1), avec sa propre profondeur (qui repart de 0) et sa clé d'idempotence (V1.5).

### Tâche (ordonnanceur)
`queued → claimed → running → succeeded | failed | cancelled` ; `claimed/running → interrupted` (crash) → `queued` après réconciliation, ou `failed`.
Claim atomique : `UPDATE tasks SET state='claimed' WHERE id = (SELECT id FROM tasks WHERE state='queued' AND not_before <= now() ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *` dans une transaction — deux workers ne peuvent jamais réclamer la même tâche (T4.2, T4.7).

### Opération externe (`external_ops`, requête source ou appel IA)
`planned → authorized → reserved → in_flight → completed → reconciled` ; branches d'échec : `failed`, `cancelled`, et **`uncertain`** (résultat/facturation inconnu).
Règle OSIA-I-09 / T3.6 / T4.7 : **jamais de rejoue aveugle** d'une opération `uncertain` ; réconciliation d'abord (interrogation du fournisseur si possible, sinon marqueur conservé et aucune nouvelle émission sans décision explicite). Une annulation locale ne libère l'enveloppe que si l'opération n'était pas `in_flight` ; sinon l'opération passe `uncertain` et l'enveloppe reste visible jusqu'à réconciliation (D7.4).

## 2. Ordonnanceur

- File persistée en table `tasks` (T4.2) ; pas de Redis/Celery/RabbitMQ (interdit V1).
- Boucle asyncio : claim → `PolicyEngine.authorize(task)` (T3.11) → exécution du handler → transition d'état + événement. Toute décision de refus est journalisée avec son motif.
- Concurrence : sémaphore asyncio borné, défaut **2 opérations externes simultanées** (V1.4), configurable par profil et installation (T4.4). Les tâches purement internes ne consomment pas ce sémaphore mais restent sous limites de profondeur/volume/temps.
- Timeouts : 15 s par requête HTTP, 60 s par appel IA (V1.4) ; dépassement → `failed` motif `timeout`, résultat partiel conservé (T3.12).

## 3. Reprise après incident (T3.6, D7.4, V1.1)

Au démarrage (`osia serve` / relance CLI) :

1. `tasks` en `claimed`/`running` → `interrupted`, puis réconciliation des `external_ops` `in_flight`/`reserved` concernés.
2. `external_ops` `in_flight` → `uncertain` ; **aucune relance automatique** ; l'investigation reprend en `suspended` et attend une décision explicite de reprise (réémission seulement après réconciliation, OSIA-I-09).
3. Investigations `running` → `suspended` avec motif `crash_recovery` ; `resume` vérifie paramètres, autorisations et budgets encore valables avant reprise (D7.4 parcours 11.2).
4. Tout est journalisé dans `events` (type `recovery.*`).

## 4. Protections anti-emballement (T4.8, OSIA-I-04)

Profondeur (1–10 rebonds, plafond par branche), volume (requêtes source, appels IA), durée, coût, concurrence : vérifiés **avant chaque opération** par le moteur de politiques, indépendamment de toute proposition IA. Détection de cycles entre entités au niveau graphe (tranche T6).

## 5. Vérifications prévues

- Test de concurrence : N workers, aucune tâche exécutée deux fois.
- Test de crash : kill entre claim et fin → reprise sans double exécution d'opération externe ; op `in_flight` → `uncertain`, non relancée.
- Test limites : profondeur max atteinte → arrêt motif `depth_limit` ; budget épuisé → `budget_exhausted` avec résultats partiels conservés.
