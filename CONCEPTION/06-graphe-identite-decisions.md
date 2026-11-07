# CON-09 — Graphe, assertions, identité et décisions humaines supervisées

**Exigences** : A9/A10/A11/A12 (partage interbranches, propagation des corrections, conclusions obsolètes, graphe multibranche), C5 (fiches traçables), C6 (validation supervisée, non destructive et réversible), T6.1–T6.8 (graphe PostgreSQL, entités typées, relations sourcées, rapprochement conservateur, fusions supervisées réversibles, contradictions préservées, graphe commun filtrable), T6.9 (performance), T3.7 (contrats typés).
**Choix d'implémentation** : graphe relationnel dans PostgreSQL (T6.1, pas de Neo4j) ; migration `0003_graphe_t6.sql` qui **complète** les tables `entities`/`relations`/`assertions`/`decisions` du schéma v1 par `ALTER TABLE` (jamais de réécriture destructive) ; service dédié `osia.graph.GraphService` ; contrats pydantic dans `osia.models`.

## 1. Entités et identifiants (T6.2)

- `entities(id, investigation_id, kind, data jsonb, merged_into NULL|entities.id, created_at)` : identifiant interne stable (`ent_*`), `kind` extensible (personne, organisation, adresse, domaine, identifiant numérique, document, événement, type connecteur — stocké en texte, pas d'enum fermé).
- `entity_identifiers(entity_id, investigation_id, scheme, value_normalisee)` avec `UNIQUE (investigation_id, scheme, value_normalisee)` : une entité peut porter plusieurs identifiants externes (ex. SIREN + LEI) ; l'identifiant interne reste distinct (T6.2). Normalisation : minuscules, trim, suppression des séparateurs usuels pour les identifiants alphanumériques (SIREN, LEI, SIRET).
- Une entité est **commune à l'investigation** (pas de fiche dupliquée par branche, A.10.3/A.12.2) ; les assertions/relations portent le `branch_id` de contexte.

## 2. Relations typées, contextualisées et sourcées (T6.3)

`relations(id, investigation_id, branch_id, src_id, dst_id, type, direction, valid_from, valid_to, proof_ids jsonb, support_level, human_decision, match_proposal_id NULL, data jsonb, created_at)` :

- Plusieurs relations possibles entre deux mêmes entités (pas d'unicité sur le couple) ; relations datées (`valid_from`/`valid_to`) et contradictoires autorisées.
- `support_level` (statut d'étayage documentaire, C6) : `documente | corrobore | a_confirmer | contradictoire | non_etabli`.
- `human_decision` (décision humaine, indépendante, C6-09/C6-10) : `unexamined | validated | rejected`.
- Chaque relation conserve sa provenance : `proof_ids` (références `proof_refs`) + `branch_id` ; **une corrélation n'est jamais assimilée à une preuve** (T6.3) : une relation déduite porte `data.derivation = "ia"`.

## 3. Assertions et contradictions (T6.6, A.8)

`assertions(id, investigation_id, branch_id, statement, nature, support_level, human_decision, proof_ids jsonb, confidence jsonb, superseded_by NULL, contradicted_by jsonb, created_at)` :

- `nature` (T6.7) : `fait_etabli | information_rapportee | indice | hypothese | conclusion_analytique`.
- Les affirmations concurrentes sont **conservées** (`contradicted_by` liste d'ids ; `support_level = 'contradictoire'`), jamais effacées (T6.6) ; une validation humaine marque `human_decision` sans effacer le matériau probant.
- Correction (C6-03) = nouvelle assertion avec `superseded_by` pointant l'ancienne ; l'original reste intact et traçable.

## 4. Rapprochement d'identité et fusions supervisées (T6.4, T6.5, C5-10/C5-11/C5-12)

- `match_proposals(id, investigation_id, entity_a, entity_b, basis, justification, confidence, status, decided_by NULL, created_at)` avec `status : proposed | validated | rejected` et `basis : exact_identifier | similarity | cross_reference`.
- **Règle explicite d'automatisation (T6.5)** : rattachement automatique **uniquement** sur identifiant externe exact (`basis = exact_identifier`, via l'unicité de `entity_identifiers`). Toute correspondance par nom/adresse/similarité (ex. adresse partagée = indice, V1.4) reste une **proposition** (`proposed`) ; aucune fusion automatique (T6.4, C5-10).
- Fusion = décision humaine `merge` : `entities.merged_into` est renseigné ; les entités initiales et leurs relations sont conservées (non destructif) ; les vues excluent les entités fusionnées mais les données restent requêtables. Séparation = `undo` de la décision merge (`merged_into` remis à NULL) — réversible (C6-06/C6-07, A.11.4).
- L'IA peut **proposer** une correspondance (rôle `matching` du courtier, T6.4) avec justification explicable et estimation de confiance qualitative ; la décision reste humaine.

## 5. Décisions historisées et réévaluation (C6, A10, A.11.4)

- `decisions(id, investigation_id, target_type, target_id, action, payload jsonb, reverts NULL, created_at)` : `action ∈ {validate, reject, correct, annotate, propose_match, merge, undo}`. Historique complet et compréhensible (A.13.3) ; `undo` référence la décision annulée (`reverts`) et déclenche une réévaluation avec les connaissances actuelles (sans rétablir aveuglément une ancienne conclusion).
- Propagation (A10, A.11.3) : le rejet/l'annulation d'un `match_proposal` dégrade le `support_level` des relations qui en dépendent (`match_proposal_id`) vers `a_confirmer` et les marque `human_decision = 'unexamined'` — **sans suppression et sans nouvel appel API systématique** ; les recherches complémentaires ne sont que suggérées (ou lancées dans une branche explicitement autorisée).
- Une correction sur une synthèse stabilisée la signale `synthesis.stale` (A11, C3-06) ; la regénération reste sur demande, sous budget.

## 6. Contrats API et événements (T3.7, T4.9)

- `GET /api/v1/investigations/{id}/graph?branch_id=` (entités + relations, filtre par branche A12, pagination `limit`/`offset`), `GET .../entities/{eid}` (fiche C5 : identifiants, alias, relations entrantes/sortantes, sources, dates, branches concernées), `GET .../relations`, `GET .../assertions`, `GET/POST .../matches` (proposition), `POST .../decisions` (action + cible), `GET .../decisions` (historique).
- Événements : `entity.created|merged|unmerged`, `relation.created|revaluated`, `assertion.created|corrected|contradicted`, `match.proposed|validated|rejected`, `decision.applied`, `synthesis.stale`.

## 7. Performance (T6.9)

Index sur `(investigation_id, kind)`, `(investigation_id, src_id)`, `(investigation_id, dst_id)`, `entity_identifiers (investigation_id, scheme)` ; chargement incrémental paginé (jamais de graphe entier en mémoire) ; limite d'exploration paramétrable pour les nœuds très connectés.

## 8. Vérifications prévues

- Identifiant exact partagé → rattachement automatique ; nom/adresse partagée → simple proposition, jamais de fusion auto (C5-10/C5-11).
- merge/undo réversible, originaux conservés ; rejet de correspondance dégrade les relations dépendantes sans les supprimer ni déclencher d'appel externe.
- Contradictions préservées et visibles ; décisions historisées et annulables.
- Filtre par branche sur le graphe commun (A12) ; API testée via httpx.
