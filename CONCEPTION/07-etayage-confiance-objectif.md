# CON-10 — Confiance multidimensionnelle et critère d'objectif suffisamment étayé

**Exigences** : A5 (arrêt automatique + suggestions, option D), B5 (fiabilité multidimensionnelle explicable), C3-07/C3-08 (pas de score chiffré opaque ; les qualifications expriment l'étayage, pas une probabilité), T4.6 (arrêt multicritère supervisé par le moteur), T6.7 (confiance multidimensionnelle ; natures fait établi / information rapportée / indice / hypothèse / conclusion analytique), V1.4 (définition de l'objectif suffisamment étayé et règle d'arrêt).
**Choix d'implémentation** : évaluation côté moteur dans `osia.graph.GraphService` ; l'IA **propose** (rôle `synthesis`), le moteur **décide** (T4.6, B4) ; niveaux qualitatifs stockés en jsonb, aucun score agrégé chiffré.

## 1. Confiance multidimensionnelle (T6.7, B5, C3-07/C3-08)

Chaque assertion porte `confidence jsonb` avec six dimensions qualitatives, chacune `haute | moyenne | faible | inconnue` :

| Dimension | Règle de calcul (explicable) |
| --- | --- |
| `fiabilite_source` | niveau de confiance (`trust_level`) des connecteurs des preuves : `official` > `approved` > `experimental` |
| `qualite_extraction` | extraction directe de la source vs déduction IA (`data.derivation`) |
| `solidite_preuves` | nombre et diversité des `proof_ids` rattachés |
| `coherence_intersources` | concordance entre sources indépendantes (connecteurs distincts) |
| `fraicheur` | date de collecte des preuves vs date de référence (collecte conservée, A.12.3) |
| `validation_humaine` | `human_decision` de l'assertion et des relations dépendantes |

Aucun score unique agrégé (C3-07) ; les niveaux sont expliqués par les éléments de preuve listés (B5).

## 2. Natures et double statut (T6.7, C6-09/C6-10)

- `assertions.nature` : `fait_etabli | information_rapportee | indice | hypothese | conclusion_analytique` — une donnée présente dans une source vs une déduction IA reste distinguée (C5-09).
- Deux statuts indépendants : `support_level` (étayage documentaire) et `human_decision` (décision humaine). Valider ne transforme pas une proposition en preuve établie (C6-09) ; un fait documenté peut être rejeté dans l'analyse sans perdre la source (C6-10).

## 3. Objectif suffisamment étayé — décision du moteur (V1.4, T4.6, A5)

Le moteur évalue `objective_etaye(investigation_id, branch_id)` :

1. **Réponses décisives** : les assertions de nature `conclusion_analytique` (ou `fait_etabli`) marquées décisives pour l'objectif de la branche. Chacune doit reposer sur :
   - une **source primaire** qui l'établit directement (preuve d'un connecteur `trust_level = official`, ex. BODACC/API entreprises/GLEIF), **ou**
   - **deux sources indépendantes concordantes** (connecteurs distincts, `coherence_intersources = haute`) ;
2. **Aucune contradiction majeure irrésolue** : aucune assertion `support_level = 'contradictoire'` liée aux réponses décisives sans `human_decision = 'validated'` la résolvant (T6.6).

Quand le critère est rempli : arrêt automatique de l'investigation (`StopReason.OBJECTIVE`, A5 option D) + **suggestions** de pistes restantes **sans les exécuter** ; toute poursuite exige une branche avec validation explicite des limites/budget (V1.1, T4.3). Un indice (adresse/code APE partagé) ne suffit jamais (V1.4).

## 4. Contrats API

- `GET /api/v1/investigations/{id}/etayage?branch_id=` : par assertion — nature, six dimensions de confiance, `support_level`, `human_decision`, preuves, contradictions.
- `GET /api/v1/investigations/{id}/objectif?branch_id=` : `{etaye: bool, reponses_decisives: [...], contradictions_majeures: [...], detail: [...]}` — utilisé par le moteur pour l'arrêt et par la restitution.

## 5. Vérifications prévues

- Cas positif (source primaire directe), cas deux sources indépendantes concordantes, cas négatif (une seule source non officielle, ou indice seul), cas partiel (contradiction majeure irrésolue bloque l'arrêt), résolution humaine de la contradiction débloque.
- Aucun score chiffré exposé ; test de présence des six dimensions et des natures.
- L'arrêt `objective_suffisamment_etaye` ne se déclenche que si le critère moteur est rempli, même si l'IA le propose seule (T4.6).
