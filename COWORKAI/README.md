# COWORKAI — espace de collaboration entre agents

Ce dossier contient les éléments **vivants** de l'exécution : missions, passations, revues, événements significatifs et décisions prises pendant les travaux. Il ne remplace ni le cadrage applicable, ni l'historique Git/CI.

L'utilisation de ce dossier doit rester proportionnée aux tâches réelles.

## Emplacements

| Chemin | Utilité |
| --- | --- |
| [DECISIONS.md](DECISIONS.md) | Décisions significatives, motifs et liens avec les références |
| [missions/](missions/) | Missions réelles : périmètre, responsable, statut, dépendances, critères et références |
| [rapports/](rapports/) | Résultats de tests, revues, passations, audits et limites documentées |

## Tableau de bord des missions

*Aucune mission créée dans le template. Ajouter seulement les tâches réellement décidées.*

| Mission | Statut | Références | Blocage / prochaine action |
| --- | --- | --- | --- |
| — | — | — | — |

## Règles opérationnelles

- Toute mission doit indiquer son **périmètre, son état et ses critères de fin** ; la procédure détaillée des statuts se trouve dans [PROJECT-INIT.md](../PROJECT-INIT.md).
- Les statuts reposent sur des **preuves** (SHA du code testé, commandes/résultats, PR, déploiement constaté).
- Une régression justifiée peut rouvrir une tâche ; conserver la trace de ce qui avait été validé auparavant.
- Éviter d'écrire des journaux de chaque ligne de code et ne jamais recopier des secrets, données personnelles inutiles ou jetons.
- Lorsque l'équipe tranche un changement durable de règle métier/technique/design, corriger le document de [`CADRAGE/`](../CADRAGE/README.md) qui fait autorité et, si nécessaire, les spécifications affectées.
- Les règles permanentes d'autonomie et d'escalade se trouvent dans [AGENTS.md](../AGENTS.md), pas ici.

**Livraison :** les agents préparent branches, tests et PR ; la fusion en branche principale reste sous contrôle utilisateur.
