# CADRAGE — Références du projet OSIA

**Mise à jour :** 05/11/2026  
**Situation :** quatre lots de cadrage fonctionnel **validés**, import de leurs originaux **en attente** ; **lot technique T1 validé** le 06/11/2026 ; conception technique transversale toujours **PROPOSÉE v0.1**.

## Ordre de priorité des sources

1. Les quatre documents fonctionnels consolidés et validés **A, B, C, D v1.0** (à verser dans ce dossier, sans les réécrire par déduction).
2. Les nouvelles décisions techniques **explicitement validées**, après mise à jour de TECHNIQUE.md.
3. Les propositions techniques non validées, à lire comme hypothèses d'étude et non comme règles applicables.
4. Les fichiers génériques du template, simples aides de rédaction, **jamais** sources de choix OSIA.

## Documents

| Document | Description | Statut |
| --- | --- | --- |
| [TECHNIQUE.md](TECHNIQUE.md) | Architecture transversale et synthèse des arbitrages T1–T8 | **PROPOSÉ v0.1** sauf décisions T1 validées |
| [T1-EXECUTION-DISTRIBUTION.md](T1-EXECUTION-DISTRIBUTION.md) | Distribution native Linux, postes/serveurs, interfaces web/GTK, API et accès | **VALIDÉ v1.0 — T1.1–T1.7** |
| [FONCTIONNEL.md](FONCTIONNEL.md) | Trame issue du template, en attente de remplacement/consolidation fidèle des lots A–D | **NON NORMATIF** |
| [DESIGN.md](DESIGN.md) | Trame du template à adapter après exploitation de C et des décisions graphiques | **NON NORMATIF** |

### Documents de référence à importer

Les fichiers ci-dessous ont été générés dans les conversations de cadrage mais n'étaient pas présents dans le dépôt le 05/11/2026. **Les noms sont donnés pour faciliter leur rapprochement ; ils ne constituent pas des liens tant que les fichiers ne sont pas effectivement importés.**

| Lot | Nom attendu | État du lot |
| --- | --- | --- |
| A — Fonctionnement des investigations | OSIA_Cadrage_Fonctionnel_Lot_A_v1.0.md | VALIDÉ |
| B — Sources et connecteurs | OSIA-CADRAGE-FONCTIONNEL-LOT-B-v1.0.md | VALIDÉ |
| C — Interface et restitution | OSIA-CADRAGE-LOT-C-v1.0.md | VALIDÉ |
| D — Paramètres et données locales | OSIA-CADRAGE-LOT-D-v1.0.md | VALIDÉ |

Dès leur import, compléter les renvois de [TECHNIQUE.md](TECHNIQUE.md) et ses matrices de recette, sans présenter une synthèse ou une mémoire conversationnelle comme reproduction exacte du Markdown validé.

## Gouvernance

Les règles permanentes de collaboration se trouvent dans [AGENTS.md](../AGENTS.md), la procédure de consolidation dans [PROJECT-INIT.md](../PROJECT-INIT.md), les évolutions dans [roadmap/](../roadmap/README.md) et les missions dans [COWORKAI/](../COWORKAI/README.md).

Les choix techniques restent marqués **OUVERT** ou **PROPOSÉ** tant qu'un arbitrage n'est pas validé. Une PR n'équivaut pas à un accord produit.
