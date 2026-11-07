# CON-07 / CON-08 — Connecteurs réels V1.2, catalogue et surveillance de santé

**Exigences** : B1 §3.2 (contrat commun des connecteurs), B2 (sources publiques documentées, conditions d'accès vérifiées au moment de l'intégration), B3 (accès autorisés, normalisation, extraction web standard), B7 §9.1 (surveillance : disponibilité, authentification, structure/cohérence des réponses, quotas, évolutions des conditions ; états opérationnel/dégradé/suspendu/obsolète ; une HTTP 200 ne suffit pas), B7 §9.4 (fiche par connecteur : périmètre, types de données, méthodes d'accès, authentification, quotas, tarifs, conditions de collecte/conservation/réutilisation/redistribution, date de vérification), B7 §9.5 (sondes proportionnées, contrôles légers préférés, fréquence configurable — planification hors V1), T3.8 (contrat logiciel), T5 (connecteur défaillant isolé, changements sensibles non activés implicitement), PERIMETRE-V1 §V1.2 (quatre connecteurs initiaux). Vérification attendue (CONCEPTION-RESTANTE) : *connecteur défaillant isolé ; changements sensibles non activés implicitement* (CON-07) et *capacités réellement vérifiées et date de contrôle* (CON-08).
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. V1.2 = quatre connecteurs officiels gratuits sans jeton ; aucun connecteur payant en V1 (B6 : pas d'appel payant sans enveloppe autorisée).

## 1. Contrat connecteur — `connectors/base.py` (B1 §3.2, T3.8)

- `ConnectorManifest` étendu (B7 §9.4) : `id`, `version`, `trust_level`, `provider`, `scope`, `categories`, `capabilities`, `access_methods`, `auth`, `domains`, `paid`, `cost_per_call_cents`, `quotas`, `conditions_url`, `last_checked` (date de vérification des conditions), `http_timeout_seconds`.
- `FetchRequest(query, params)` → `FetchResult(content, provenance, media_type, extracted_text)` ; `Provenance` porte `source_id`, `url`, `fetched_at`, `method`, `http_status` (T5.6 : la provenance est validée http/https à l'enregistrement de la preuve, CON-06).
- `Connector.validate_response(payload)` : contrôle sémantique de la réponse **normalisée** (B7 §9.1) — liste des problèmes de structure ; implémentation par défaut vide, surchargée par chaque connecteur réel.

## 2. Connecteur HTTP de base — `connectors/http.py` (B3, T5.4)

- `HttpConnector` : **toute requête sortante passe par `netguard.guarded_request`** (allowlist/denylist, anti-SSRF, redirections re-vérifiées, taille, rate limit — CON-06). Sans guard injecté (tests), appel direct.
- `fetch_fn` injectable : contrat `(url) -> (status, headers, body)` **sans suivre les redirections** (le guard les gère). Défaut `aiohttp_fetch` (aiohttp, UA `osia/0.1`, timeout 15 s, `allow_redirects=False`). En test, `fetch_fn` est remplacé par des fixtures JSON : **aucun appel réseau** (AGENTS.md).
- `_result()` construit le `FetchResult` avec provenance ; `validate_response()` hook sémantique.

## 3. Catalogue V1.2 — `connectors/real.py` (PERIMETRE-V1 §V1.2, B7 §9.4)

Quatre connecteurs officiels (`TrustLevel.OFFICIAL`, activés par défaut), gratuits, sans authentification :

| Connecteur | Fournisseur | Périmètre | Accès | Auth | Coût | `last_checked` |
| --- | --- | --- | --- | --- | --- | --- |
| `gouv.recherche-entreprises` | DINUM — api.gouv.fr | France, entreprises/établissements (SIREN/SIRET) | API ouverte HTTPS `…/search?q=&per_page=5` | aucune | gratuit | 2026-11-07 |
| `gouv.bodacc` | DILA — BODACC | France, annonces légales (procédures collectives, actes RCS) | API ouverte HTTPS (base configurable `OSIA_BODACC_API_BASE`) | aucune | gratuit | 2026-11-07 |
| `gleif.lei` | GLEIF | International, LEI et relations déclarées | API ouverte HTTPS `…/lei-records?filter[lei]=` ou `filter[entity.legalName]=` | aucune | gratuit | 2026-11-07 |
| `web.url` | OSIA | URL publiques fournies/découvertes (HTML, PDF textuels) | HTTP GET via NetworkGuard + extraction | aucune | gratuit | 2026-11-07 |

Fiches complètes (B7 §9.4) dans les manifestes : `scope`, `categories`, `access_methods`, `quotas` (ordre de grandeur, à vérifier à l'intégration), `conditions_url`, `last_checked`. **Conservation/réutilisation** : les réponses sont des données publiques ; elles sont stockées comme preuves (dédup SHA-256) avec leur provenance et période de validité (B7 §9.2), jamais redistribuées hors export supervisé (D5). En cas de doute sur un droit d'accès, le connecteur passe SUSPENDU jusqu'à vérification (B7 §9.4) — l'IA ne peut pas écarter cette restriction.

- **Normalisation** : chaque connecteur transforme la réponse brute en un JSON normalisé stable (ex. recherche-entreprises : `{query, total_results, results: [{siren, nom_complet, etat_administratif, nature_juridique, activite_principale, adresse}]}` ; GLEIF : `{query, results: [{lei, legal_name, country}]}`).
- **Web par URL** (`web.url`) : HTML → extraction texte par `HTMLParser` stdlib (**script/style filtrés, jamais exécutés**, T5.6) ; PDF textuel → `pypdf` (dépendance ajoutée). **Pas de navigateur avancé en V1.2** (T5.3 : Playwright isolé reste différé, nécessaire et autorisé) ; **aucun contournement de CAPTCHA/protection**. Le connecteur n'a aucun domaine pré-autorisé : chaque URL fournie est soumise au NetworkGuard (allowlist des settings + denylist + anti-SSRF).
- **BODACC** : l'URL exacte de l'API DILA est configurable (`OSIA_BODACC_API_BASE`) et **à confirmer à l'intégration** (B2 §4.2 : disponibilité et conditions vérifiées au moment de l'intégration) — documenté comme tel dans le manifeste.

## 4. Surveillance de santé — `connectors/health.py` (B7 §9.1, CON-07)

- `ConnectorHealthChecker` : états `operationnel | degrade | suspendu | obsolete | inconnu` (B7 §9.1).
  - **obsolète** : `last_checked` absent/illisible ou > 180 jours (conditions non revérifiées, B7 §9.4) ;
  - **suspendu** : connecteur inconnu/désactivé (retiré des recherches sans bloquer les autres, B-ACC-01/12), sonde refusée par le NetworkGuard, sonde indisponible (timeout/DNS), ou HTTP 401/403 (restriction bloquante) ;
  - **dégradé** : réponse reçue mais validation sémantique incomplète (HTTP ≥ 400 ou problèmes de structure) — certaines fonctions restent utilisables, les autres exclues ;
  - **opérationnel** : sonde 2xx + `validate_response` sans problème ;
  - **inconnu** : aucune sonde par défaut (ex. `web.url`) et aucun contrôle manuel effectué.
- **Sonde légère** (B7 §9.5) : `probe_query` par connecteur (ex. `EDF`, `ELECTRICITE DE FRANCE`), remplaçable manuellement. **V1 : contrôles manuels uniquement** (API), aucun sondage planifié — la fréquence des vérifications périodiques relève du calendrier de maintenance avancée (B7 §9.5, B-ACC-14).
- API : `GET /api/v1/connectors/{id}/health` (dernier état connu), `POST /api/v1/connectors/health-check` (`{connector_id?, probe_query?}`, tous les connecteurs si `connector_id` absent) — opération auditée (`op.connector.health_check`, T5.9).

## 5. Enregistrement dans le moteur — `engine.py`

- `build_real_connectors()` : les 4 connecteurs sont enregistrés au registre à `setup()`, leurs `domains` alimentent l'**allowlist du NetworkGuard** avant sa création, puis chaque connecteur reçoit le guard (`c.netguard = …`) et est autorisé par le PolicyEngine (`allow_target`).
- Le health checker est exposé via `engine.health`.

## 6. Limites connues (à lever à l'intégration, sans rouvrir les arbitrages)

- URL exacte de l'API BODACC et quotas effectifs (recherche-entreprises, GLEIF, BODACC) à vérifier à l'intégration (B2 §4.2) ; `last_checked` à rafraîchir après vérification.
- Risque DNS-rebinding TOCTOU noté à l'audit de CON-06 (résolution puis connexion non épinglée) — le guard re-vérifie à chaque redirection ; renforcement ultérieur possible (connexion par IP résolue).
- `web.url` n'a pas de sonde par défaut : état `inconnu` tant qu'aucun contrôle manuel avec URL explicite.
- Extraction PDF limitée aux PDF **textuels** (pypdf) ; les PDF scannés restent hors périmètre V1.2.

## 7. Vérifications réellement exécutées

- `pytest -q` : **117 tests passés** (pgserver embarqué), dont **18 dans `tests/test_con0708.py`** : normalisation des 3 API (fixtures JSON injectées, aucun réseau), filtre LEI/nom GLEIF, `validate_response` sur structure invalide, refus NetworkGuard sur domaine non autorisé, passage obligé par le guard, extraction HTML (script/style filtrés) et PDF textuel (PDF minimal fabriqué à la main), états de santé (opérationnel/dégradé/suspendu/obsolète/inconnu, check_all), enregistrement moteur (ids, allowlist, guard injecté), routes API health (GET état inconnu puis opérationnel, POST health-check unitaire et global, 404 connecteur inconnu).
- Aucun appel externe réel exécuté pendant les tests (AGENTS.md : connecteurs simulés/fixtures en CI).
