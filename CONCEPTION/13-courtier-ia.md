# CON-11 — Courtier IA réel : adaptateurs, modèles/rôles, repli supervisé

**Exigences** : D2 §4 (configuration multi-fournisseurs IA avec orchestration supervisée : ajouter/tester un fournisseur, modèles principaux et alternatives explicitement autorisées, secrets jamais persistés en clair par défaut ni dans les logs/exports, test de connexion sur action explicite), T8.1 (courtier centralisé, aucun contournement), T8.3 (routage adaptatif respectant permissions de transmission et budgets), T8.4 (réservation transactionnelle avant tout appel payant, coût borné sinon refus), T8.6 (sorties typées validées avant consommation), T8.8 (confidentialité des transmissions : local préféré, autorisation spécifique avant transmission à un nouveau fournisseur, aucune fuite de secrets dans les prompts), T8.9 (repli supervisé : jamais de fournisseur de secours payant sans autorisation budgétaire ; repli ne change pas la politique de confidentialité), PERIMETRE-V1 §V1.3 (cloud Mistral Small 4 `mistral-small-2603` + local OpenAI-compatible ; repli local→cloud exige autorisation de transmission + enveloppe). Vérification attendue (CONCEPTION-RESTANTE) : *sorties invalides rejetées ; aucun repli hors permission/budget*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. V1 : le fournisseur par défaut reste **simulé** — aucun appel payant sans configuration explicite (B6, V1.4 : budget 0 € au premier démarrage).

## 1. Adaptateurs réels — `ai/real.py` (T8.1, D2 §4.2)

- `ChatCompletionsAdapter` : contrat commun **chat completions** (Mistral cloud et LLM local OpenAI-compatible). `POST {base}/chat/completions` avec `response_format: json_object`, `temperature: 0` ; la sortie est parsée en JSON puis validée par pydantic (`response_model.model_validate`) — une sortie non JSON ou non conforme lève une erreur rejetée par le courtier (**T8.6 : `sortie_ia_invalide`**, testé).
- **Réseau** : toute requête vers un host **externe** passe par le `NetworkGuard` (T5.4, domaine `api.mistral.ai` ajouté à l'allowlist à l'enregistrement) ; un endpoint **local explicite** (127.0.0.1/localhost/::1) reste hors guard (liaison locale T1, préférence local T8.8). `fetch_fn` injectable : **aucun appel réel en test** (AGENTS.md).
- `MistralCloudAdapter` (provider `mistral`, modèle `mistral-small-2603` par défaut, `paid=True`, **borne de coût** `OSIA_MISTRAL_COST_CENTS` défaut 5 c — réservation T8.4 avant l'appel). Clé API depuis `OSIA_MISTRAL_API_KEY` ou le coffre `MISTRAL_API_KEY` (D2 §4.3 : jamais en clair dans les logs, exports, prompts ou exceptions — testé).
- `LocalOpenAIAdapter` (provider `local`, modèle `ministral-3-8b` par défaut, endpoint `OSIA_AI_LOCAL_BASE_URL` défaut `http://127.0.0.1:11434/v1`, non payant).
- `build_ai_adapters(settings, secrets)` : `simulated` toujours présent (T3.14) ; `local` si endpoint configuré ; `mistral` si clé disponible ; rôles `planning`/`extraction`/`synthesis` routés vers `OSIA_AI_PROVIDER` (défaut `simulated`).
- **Test de connexion** (D2 §4.2) : `ping()` = `GET {base}/models` — listing **non facturé**, aucun prompt métier transmis ; aucun appel facturable hors investigation (B6). API `POST /api/v1/ai/test`, CLI `osia ai test <key>`, audité (`op.ai.test`) sans clé.

## 2. Courtier et repli — `ai/broker.py` + `engine.py` (T8.9, V1.3, D2 §4.4)

- Le courtier existant centralise tout : autorisation PolicyEngine (cible autorisée + limites + réservation budgétaire si payant, T8.4) → appel → validation de schéma (T8.6) → persistance/événement.
- **Repli local → cloud** : `allowed_fallbacks = {"local": "mistral"}` **uniquement si** l'autorisation de transmission `allow_ai_fallback_local_to_cloud` est persistée (API `POST /api/v1/ai/fallback`, CLI `osia ai fallback --enable/--disable`, audité `op.ai.fallback.toggle`). Sans autorisation : aucune tentative de repli (testé). Avec autorisation mais appels payants désactivés (défaut V1.4) : le repli est tenté, tracé (`ai.fallback`), puis **refusé par la réservation budgétaire** (testé). Avec enveloppe activée : le repli fonctionne (testé).
- Le repli ne contourne jamais le budget : chaque appel, y compris le secours, passe par `authorize` + réservation (T8.4/T8.9).

## 3. API / CLI (D2 §4.2)

- `GET /api/v1/ai/providers` : fournisseurs enregistrés, modèles par rôle, replis autorisés, `paid`/coût — **aucune clé API exposée** (testé).
- `POST /api/v1/ai/fallback` `{enabled}` : autorisation persistée du repli local→cloud (T8.8/T8.9).
- `POST /api/v1/ai/test` `{provider_key}` : test de connexion explicite non facturé.
- CLI : `osia ai providers|test <key>|fallback --enable/--disable`.

## 4. Limites connues

- La borne de coût Mistral (5 c/appel par défaut) est une **estimation** : la réconciliation utilise le coût réel si le fournisseur le fournit (T8.4 étape 5/6) ; un coût inconnu bloque l'appel (`cout_inconnu_bloque`, déjà en place).
- Le test de connexion ne prouve pas la disponibilité du modèle de chat (non facturable hors investigation) ; la santé réelle se constate au premier appel d'investigation.
- Un endpoint local non local (host externe) passe par le guard et doit être autorisé dans l'allowlist.

## 5. Vérifications réellement exécutées

- `pytest -q` : **132 tests passés** (pgserver embarqué), dont **12 dans `tests/test_con11.py`** : completion Mistral validée (URL, modèle Small 4, `response_format`, header `Authorization` présent), sortie non JSON rejetée, schéma invalide → `ValidationError` (T8.6), erreur HTTP 401 **sans fuite de clé**, ping `GET /models`, adaptateur local (hors guard, non payant, modèle par défaut), `build_ai_adapters` (simulé par défaut / local+mistral / clé depuis le coffre), repli non autorisé non utilisé, repli autorisé mais sans budget payant refusé (`PolicyDeny`, événement `ai.fallback` tracé), repli avec enveloppe OK, API providers/fallback/test (404 inconnu, aucune clé exposée).
- Aucun appel réseau ou payant réel exécuté pendant les tests (`fetch_fn` injecté partout).
