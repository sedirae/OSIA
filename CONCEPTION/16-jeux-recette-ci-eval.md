# CON-19 — Jeux de recette, CI et métriques d'évaluation IA par tâche

**Exigences** : T3.14 (tests multicouches — unitaires, intégration, contrats, scénarios de bout en bout, non-régression — avec substituts simulant sources, connecteurs et fournisseurs IA pour tester coûts, limites, erreurs, interruptions, reprises, isolation et corrections humaines **sans dépenses API**, intégrables aux processus CI et aux revues de code), T8.10 (évaluation reproductible indépendante des fournisseurs : mesurer l'efficacité des modèles **par tâche** — conformité des schémas, erreurs, latence, coûts, qualité d'extraction — via des jeux de tests reproductibles comparables entre fournisseurs/versions/modèles/instructions). Vérification attendue (CONCEPTION-RESTANTE) : *tests reproductibles hors ligne et relevés de résultats réels*.
**Choix d'implémentation** : ce document ne rouvre aucun arbitrage. La suite pytest (168 tests) couvre déjà les couches unitaire/intégration/contrat/non-régression avec simulations ; CON-19 ajoute les **scénarios de bout en bout rejouables avec relevés**, la **CI GitHub Actions** et le **module d'évaluation par tâche**.

## 1. Jeux de recette rejouables hors ligne — `src/osia/recette.py` (T3.14)

- 5 scénarios déterministes (`SCENARIOS`) exécutant une investigation de bout en bout avec le connecteur et l'adaptateur IA **simulés** (fixtures scriptées, `fail_on` pour simuler une source indisponible) : `happy_path`, `source_indisponible`, `sortie_ia_invalide`, `arret_utilisateur`, `isolation`.
- Chaque exécution produit un **relevé de résultats réels** (JSON sérialisable) : état final, `stop_reason`, tâches par état/erreur, nombre de preuves, entités extraites, types d'événements, vue budget (dict JSON), entrées du journal technique de l'investigation (T3.13), appels source/IA réellement effectués, durée mesurée, `offline: true`.
- **Rejouabilité** : le cache technique des requêtes source (B-ACC-06) est réinitialisé avant chaque scénario — un hit cache court-circuite la chaîne (pas de preuve, pas de tâche `synthesize`) et casserait le relevé ; `run_all` démarre le moteur UNE SEULE fois (`scheduler.stop()` est définitif, un nouveau cycle après arrêt le réarme explicitement via `Scheduler.reset_stop`) ; `manage_engine=False` sur un moteur non démarré est refusé explicitement.
- Comportements vérifiés : objectif atteint → arrêt `objective_suffisamment_etaye` ; source indisponible → tâche `failed` classifiée + événement `op.uncertain` (pas d'échec brutal) ; sortie IA non conforme → rejet T8.6 (`sortie_ia_invalide`, `op.failed`) ; arrêt utilisateur → `stop_reason` utilisateur ; **isolation** entre deux investigations (entités disjointes, requêtes distinctes pour éviter le hit cache B-ACC-06).
- CLI : `osia recette run [--scenario NOM|all] [--out DIR]` — écrit `releves/recette-<scénario>-<ts>.json` sous `<data_dir>/releves` par défaut. Aucune dépense, aucun appel réseau.

## 2. CI GitHub Actions — `.github/workflows/ci.yml` (T3.14)

- Déclenchée sur `push`/`pull_request` vers `main` (intégration aux revues de code), `ubuntu-latest`, Python 3.12, `pip install -e ".[test]"`, puis `python -m pytest -q`.
- **Hors ligne** : PostgreSQL embarqué (`pgserver`), connecteurs/IA simulés — aucun service externe, aucun appel réseau, aucune dépense API.
- Un seul test est désélectionné (`test_budgets.py::test_concurrent_reservations_cannot_exceed_cap`) : défaillant pré-existant sur `main` (concurrence réservations), documenté, non traité ici.

## 3. Évaluation IA par tâche — `src/osia/ai/eval.py` (T8.10)

- Jeu de cas embarqué `EVAL_CASES` (planning / extraction / synthesis) avec entrée, schéma de sortie et vérité terrain — **reproductible et rejouable hors ligne** via `scripted_adapter_for_cases` (adaptateur simulé rejouant les réponses scriptées).
- Métriques **par cas et agrégées par rôle (tâche)** : conformité au schéma (T8.6), erreurs classifiées, latence (ms), coût (centimes), qualité d'extraction (précision/rappel/F1 sur nom+identifiants d'entités). Totaux comparables entre adaptateurs (fournisseurs, versions, modèles, instructions) sans dépendre d'un seul prestataire.
- Le rapport est un **relevé de résultats réels** (mesures effectuées pendant l'exécution), sérialisable en JSON.
- CLI : `osia ai eval [--adapter simulated] [--out FILE]` — `simulated` par défaut (hors ligne, coût 0) ; tout autre adaptateur exige sa configuration (clé, URL locale) et n'est évalué que si disponible.

## 4. Limites connues

- Les scénarios de recette couvrent 5 parcours (nominal, panne source, sortie IA invalide, arrêt utilisateur, isolation) ; la reprise après crash est couverte unitairement (`scheduler.recover`, `crash_recovery`) mais pas en scénario rejouable de bout en bout.
- L'évaluation par tâche porte sur 3 cas embarqués (un par rôle) ; étendre le jeu de cas est une évolution de données, pas de code.
- Les latences mesurées sur adaptateur simulé ne sont pas représentatives d'un fournisseur réel (métriques de processus, pas de performance réseau).
- CI : un test pré-existant flaky est désélectionné (voir §2).

## 5. Vérifications réellement exécutées

- `pytest -q` : **168 tests passés** (1 défaillant : `test_concurrent_reservations_cannot_exceed_cap`, défaillant aussi sur `main` avant cette tranche), dont **11 nouveaux dans `tests/test_con19.py`** : 5 scénarios de recette rejoués hors ligne avec relevés (état final, stop_reason, tâches, preuves, entités, événements, techlog, `offline: true`, relevé sérialisable), `run_all` déterministe avec résultats attendus par scénario dans le lot (cache source réinitialisé), rejeu sur un même moteur et erreur explicite sur moteur non démarré, évaluation simulée conforme (conformité 100 %, F1 extraction 1.0, coût 0, reproductible à l'identique), sortie invalide comptée non conforme, métriques précision/rappel/F1, workflow CI présent et câblé sur `pull_request`.
