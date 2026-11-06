# Index du cadrage OSIA

**Édition : 1.1 — 06/11/2026.** Les décisions restent celles validées les 5 et 6 novembre 2026.

## Autorité documentaire

1. Une nouvelle instruction explicite du porteur peut modifier le cadrage ; la consigner sans masquer l'évolution.
2. Les fichiers `LOTS/` sont les références détaillées actives. Les harmonisations consignées dans [AUDIT-COHERENCE.md](AUDIT-COHERENCE.md) y sont déjà intégrées.
3. [FONCTIONNEL.md](FONCTIONNEL.md) et [TECHNIQUE.md](TECHNIQUE.md) sont des vues transversales des mêmes décisions ; ils ne réduisent pas les exigences détaillées.
4. [DECISIONS.md](../COWORKAI/DECISIONS.md) est l'index de traçabilité ; [RECETTE.md](RECETTE.md) associe contrôles et exigences. Ils ne valent pas preuve d'exécution.
5. [DESIGN.md](DESIGN.md) reprend les obligations UX acquises. Les choix visuels ouverts et les autres détails figurent dans [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md).

Les sources anciennes servent à la provenance. Elles ne doivent pas être remises à côté des documents actifs comme instructions concurrentes. La consolidation provisoire et les travaux prématurés GitHub sont remplacés pour le cadrage actif. Une incohérence nouvelle doit être signalée, pas résolue en choisissant arbitrairement le fichier le plus récent.

## Lots de référence

| Lot | Fichier | Couverture |
| --- | --- | --- |
| A — Investigation | [A.md](LOTS/A.md) | 12 arbitrages A1–A12 ; 13 thèmes A.1–A.13 ; 15 scénarios S01–S15 |
| B — Sources et connecteurs | [B.md](LOTS/B.md) | B1–B7 ; 16 critères B-ACC |
| C — Interface et restitution | [C.md](LOTS/C.md) | C1–C7 ; 96 règles détaillées ; 19 critères REC-C |
| D — Paramètres et données | [D.md](LOTS/D.md) | D1–D7 ; 19 critères REC-D ; invariants renommés D-INV |
| T1 — Exécution et distribution | [T1.md](LOTS/T1.md) | 7 thèmes consolidés EXEC-01–07 ; pas de correspondance originale T1.x inventée |
| T2 — Stockage et sauvegarde | [T2.md](LOTS/T2.md) | T2.1–T2.8 |
| T3 — Langage et moteur | [T3.md](LOTS/T3.md) | T3.1–T3.14 |
| T4 — Orchestration | [T4.md](LOTS/T4.md) | T4.1–T4.9 |
| T5 — Sécurité | [T5.md](LOTS/T5.md) | T5.1–T5.9 |
| T6 — Graphe et identités | [T6.md](LOTS/T6.md) | T6.1–T6.9 |
| T7 — Archives et exports | [T7.md](LOTS/T7.md) | T7.1–T7.9 |
| T8 — IA et coûts | [T8.md](LOTS/T8.md) | T8.1–T8.10 |

## Convention de lecture

« Doit » indique une obligation issue du cadrage ; « peut » une possibilité ; « proposé », « indicatif », « exemple » ou « candidat » n'établissent pas une obligation de livraison ou une technologie choisie. Un critère de recette dérivé explicite comment vérifier une exigence ; il n'ajoute pas un arbitrage produit.

Les valeurs de profils, budgets, délais, quotas et seuils non explicitement validées ne sont pas fixées par ce corpus. La profondeur autorisée de 1 à 10 rebonds est, elle, acquise. Le choix des fournisseurs, versions logicielles et tarifs doit être vérifié à la conception/intégration, pas déduit d'un exemple.

`A5` (arbitrage d'arrêt) et `A.5` (thème de profondeur) sont deux références différentes. Les anciens `INV-01` de D et de T4–T8 n'avaient pas la même signification : utiliser `D-INV-*` pour D et les identifiants originaux des décisions techniques ; les invariants transversaux sont ici nommés `OSIA-I-*`.

## Périmètre et statut

Le cadre cible est clos ; le périmètre détaillé V1 n'est pas une liste déjà validée. Les fonctions explicitement initiales et les reports explicites sont conservés dans [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md). L'authentification serveur ne crée pas une exigence de plateforme SaaS collaborative. L'installation Desktop n'est pas le futur client GNOME.
