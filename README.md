# OSIA — Référentiel de cadrage consolidé

**Édition 1.1 — 6 novembre 2026.** Le cadrage fonctionnel, technique et le périmètre de livraison V1 sont validés. La conception détaillée a été produite (CON-01…CON-19, `CONCEPTION/01`–`16`) et la recette applicative exécutée (`COWORKAI/RECETTE-APPLICATIVE.md`).

OSIA est un moteur d'investigation sur sources publiques : il part d'indices et d'un objectif facultatif, conduit une recherche automatique bornée, conserve les preuves et restitue des conclusions vérifiables. L'utilisateur garde le contrôle des corrections, approfondissements, transmissions et budgets.

Ce dossier est le remplacement documentaire préparé à partir des cadrages produits dans ChatGPT. Aucun contenu du dépôt GitHub existant n'a été utilisé comme autorité. Les fichiers fournis sont destinés à devenir les références actives ; ils ne décrivent pas une application déjà développée.

## Commencer ici

| Besoin | Document |
| --- | --- |
| Règles pour un agent de développement | [AGENTS.md](AGENTS.md) |
| Démarrage de la conception et limites du mandat | [PROJECT-INIT.md](PROJECT-INIT.md) |
| Hiérarchie documentaire et index des douze lots | [CADRAGE/README.md](CADRAGE/README.md) |
| Vue fonctionnelle transversale | [CADRAGE/FONCTIONNEL.md](CADRAGE/FONCTIONNEL.md) |
| Architecture technique retenue | [CADRAGE/TECHNIQUE.md](CADRAGE/TECHNIQUE.md) |
| Décisions, options, sources et critères associés | [COWORKAI/DECISIONS.md](COWORKAI/DECISIONS.md) |
| Critères d'acceptation, sans prétention de tests exécutés | [CADRAGE/RECETTE.md](CADRAGE/RECETTE.md) |
| Écarts corrigés et limites de la vérification | [CADRAGE/AUDIT-COHERENCE.md](CADRAGE/AUDIT-COHERENCE.md) |
| Périmètre V1 validé et reports | [CADRAGE/PERIMETRE-V1.md](CADRAGE/PERIMETRE-V1.md) |
| Travail restant de conception | [CADRAGE/CONCEPTION-RESTANTE.md](CADRAGE/CONCEPTION-RESTANTE.md) — couvert (CON-01…CON-19) |
| Conception détaillée produite | `CONCEPTION/01`–`16` (index dans [CONCEPTION/README.md](CONCEPTION/README.md)) |
| Recette applicative exécutée (matrice de traçabilité) | [COWORKAI/RECETTE-APPLICATIVE.md](COWORKAI/RECETTE-APPLICATIVE.md) |
| Références exactes et empreintes des sources | [CADRAGE/SOURCES.md](CADRAGE/SOURCES.md) |
| Intégration du cadrage sur GitHub | [COWORKAI/INTEGRATION-GITHUB.md](COWORKAI/INTEGRATION-GITHUB.md) |

## Ce que signifie « définitif »

Les décisions de cadrage sont consolidées, sans rouvrir les arbitrages ni choisir à la place du porteur de projet des frameworks, des fournisseurs ou des valeurs par défaut. Les lots détaillés restent la référence ; les vues transversales facilitent leur utilisation. Les choix encore nécessaires à l'implémentation sont explicitement isolés.

Huit Markdown ont été retrouvés et examinés intégralement. Les 101 arbitrages numérotés A–D et T2–T8 sont tracés, ainsi que les 96 règles détaillées de C et les 69 critères de recette fonctionnelle d'origine. T1 est consolidé en sept thèmes `EXEC-01` à `EXEC-07`, sur la base des rappels présents dans les textes validés et des décisions de conversation retrouvées. Sa numérotation originale T1.1–T1.7 n'est pas présentée comme reconstituée à l'identique.

La consolidation provisoire antérieure est remplacée. Le texte complet T4–T8 a été retrouvé ; sa réserve de couverture n'est plus applicable. L'audit indique la limite documentaire propre à T1.
