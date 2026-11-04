# Index du cadrage

Ce dossier est la **source de vérité** des décisions durables applicables au projet une fois initialisé.

| Document | Responsabilité |
| --- | --- |
| [FONCTIONNEL.md](FONCTIONNEL.md) | Vision, périmètre, règles métier, utilisateurs et parcours |
| [TECHNIQUE.md](TECHNIQUE.md) | Architecture, sécurité, stockage, intégrations et exploitation |
| [DESIGN.md](DESIGN.md) | Expérience utilisateur, ergonomie, direction visuelle et accessibilité |

**État du template :** les documents sont des trames **à compléter**. Aucun choix produit, technique ou graphique n'est prévalidé.

## Règles de mise à jour

- Seules les décisions réellement actées doivent porter le statut `VALIDÉ`.
- Utiliser `PROPOSÉ`, `OUVERT`, `REPORTÉ`, `REMPLACÉ` lorsque nécessaire. Une décision remplacée n'est plus applicable.
- Ajouter un document supplémentaire (parcours, données, contraintes légales, API, etc.) **seulement si le projet le justifie** et le référencer ici.
- Lorsque la règle durable change, mettre à jour les documents concernés ; ne pas laisser des instructions incompatibles dans les fichiers actifs.
- Les nouvelles fonctionnalités détaillées vont dans [`roadmap/`](../roadmap/README.md), les travaux et décisions significatives dans [`COWORKAI/`](../COWORKAI/README.md).
- Les maquettes et visuels de conception peuvent être placés dans `assets/` et référencés depuis `DESIGN.md`. Les fichiers applicatifs finaux ne vivent pas nécessairement ici.

Voir [PROJECT-INIT.md](../PROJECT-INIT.md) pour la procédure d'initialisation et de révision.
