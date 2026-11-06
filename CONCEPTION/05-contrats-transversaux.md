# Contrats transversaux du socle — modèles, événements, API, connecteurs, courtier IA, sécurité des modes

**Exigences** : T3.7 (contrats typés versionnés), T3.13 (journal structuré), T4.9 (SSE), T5.7 (sécurité des modes), T8.1/T8.6 (courtier IA), B1/B7 (contrat connecteurs), V1.3/V1.5 (modèles, `/api/v1`, SSE, idempotence), CON-07/CON-11/CON-12.
**Choix d'implémentation** : pydantic pour les contrats, FastAPI pour l'API (OpenAPI généré = contrat `/api/v1`), événements persistés en table `events` avec curseur.

## 1. Contrats internes (T3.7)

- Tous les échanges entre modules passent par des **modèles pydantic typés** (`osia.models`) ; pas de sérialisation JSON forcée sur les appels Python internes.
- Contrats persistés/externes versionnés : schéma SQL v1 (CON-02), `format_version: "1.0"` pour `.osia` (V1.5), préfixe API `/api/v1` (V1.5).

## 2. Événements et journal (T3.13, T4.9)

- Table `events(id bigserial, investigation_id, branch_id, type, payload jsonb, created_at)`. Le journal complète l'état, ne le remplace pas (EXEC-04).
- Types socle : `investigation.created/started/suspended/stopped/resumed`, `branch.created`, `task.queued/claimed/succeeded/failed`, `op.authorized/reserved/in_flight/completed/uncertain/reconciled`, `budget.reserved/consumed/released`, `recovery.*`, `policy.denied` (avec motif).
- **SSE** : `GET /api/v1/investigations/{id}/events?last_event_id=` ; `id:` = curseur, `event:` = type, resynchronisation par relecture de l'état si l'historique manque (V1.5). L'état persistant reste la référence après déconnexion (EXEC-04).
- Journaux structurés (JSON lines, `OSIA_LOG_DIR`), corrélation par `investigation_id`/`task_id`/`op_id`, **sans secrets** (OSIA-I-12, masque des champs `key`/`token`/`secret`/`password`).

## 3. API REST `/api/v1` (V1.5, CON-12)

- Contrat OpenAPI généré par FastAPI, servi sur `/api/v1/openapi.json`. Évolutions compatibles dans `v1` ; rupture → `v2`.
- Ressources socle : `GET /health`, `GET/PUT /settings` (sans secrets), `GET /profiles`, `POST /investigations` (header `Idempotency-Key`, body : indices, objectif facultatif, profil, surcharges de limites) → `201` + investigation, `GET /investigations`, `GET /investigations/{id}`, `POST /investigations/{id}/stop`, `POST /investigations/{id}/resume`, `POST /investigations/{id}/branches` (validation explicite des limites/budget requise), `GET /investigations/{id}/budget` (estimé/réservé/constaté/disponible, jamais confondu — FONCTIONNEL §5), `GET /investigations/{id}/events` (SSE).
- Erreurs : JSON `{error: {code, message, details}}`, codes stables (`idempotency_conflict`, `policy_denied`, `limit_reached`, `not_found`, …). `409` si la clé d'idempotence renvoie une ressource différente.

## 4. Contrat connecteur (B1, T3.8, T5.1, CON-07)

Manifeste déclaratif par connecteur : `id`, `version`, `trust_level` (`official` | `approved` | `experimental`), `capabilities`, `permissions` (domaines, méthodes), `network` (domaines autorisés, quotas, timeout, taille max), `costs` (payant ou non, unité), dépendances.

Interface : `async fetch(request: FetchRequest) -> FetchResult` où `FetchResult` = contenu brut + `Provenance(source_id, url, fetched_at, method, http_status)` + métadonnées. **Tout passage par le PolicyEngine avant exécution** (autorisation source, réseau, budget) ; un connecteur ne décide jamais seul (B4). Connecteurs V1.2 : API Recherche d'entreprises, BODACC, GLEIF, Web par URL (HTTP d'abord, Playwright isolé si nécessaire et autorisé, T5.3). En test : connecteurs **simulés** (T3.14).

## 5. Contrat courtier IA (T8.1, T8.6, V1.3, CON-11)

- **Tous les appels modèles passent par `AIBroker`** ; aucun module ni connecteur n'appelle un modèle directement.
- `async call(role, input, response_model) -> validated output` : rôles = `planning`, `source_selection`, `extraction`, `matching`, `analysis`, `synthesis` (T8.2 : fonctions, pas six agents imposés).
- Cycle : PolicyEngine (transmission autorisée vers le fournisseur, budget) → réservation si payant (CON-04) → adaptateur fournisseur → **validation du schéma de sortie** (pydantic, T8.6) → rejet contrôlé si invalide (nouvelle tentative soumise aux mêmes règles) → événement + persistance de la sortie structurée et de sa provenance (fournisseur/modèle/version, T8.7).
- Fournisseurs V1.3 : cloud Mistral (`mistral-small-2603`), local OpenAI-compatible (Ministral 3 8B candidat). Repliuniquement vers alternative autorisée (T8.9). En test : adaptateur **simulé**.

## 6. Sécurité des modes (T5.7, EXEC-05, CON-05 socle)

- Desktop : API sur `127.0.0.1` uniquement par défaut ; aucune exposition distante sans configuration explicite.
- Server : authentification **obligatoire même sans frontend web** : jeton Bearer (stocké hashé SHA-256 en settings, comparaison en temps constant), sessions avec expiration, audit des accès sensibles en `events` type `security.*` (T5.9). HTTPS requis pour tout accès distant (V1.5/T5.7) ; en V1 la terminaison TLS peut être un proxy inverse, documenté en config.
- Réseau sortant : contrôle centralisé (domaines autorisés/interdits, blocage SSRF vers IP privées/locales non autorisées, contrôle des redirections, délais, tailles) — T5.4, appliqué par défaut aux connecteurs HTTP.
- Contenus externes = données non fiables (T5.6, OSIA-I-01) : jamais d'instruction de pilotage ; sorties IA = propositions soumises aux politiques.

## 7. Vérifications prévues

- Tests de contrats (schémas pydantic) avec adaptateurs/connecteurs simulés.
- SSE : reprise par curseur après déconnexion, resync si historique manquant, aucune tâche relancée en double (CON-12).
- Mode server : toute requête sans jeton valide → `401`, y compris sans frontend installé.
- Aucun secret dans logs/exports (test de filtrage).
