# OSIA — Intégration du référentiel de remplacement

## Mandat

Le porteur a demandé le 06/11/2026 de ne pas tenir compte des travaux GitHub prématurés et de préparer leur remplacement complet. Le présent dossier conserve l'organisation de collaboration attendue (`AGENTS.md`, `PROJECT-INIT.md`, `CADRAGE/`, `COWORKAI/`) avec un contenu OSIA rédigé à neuf ou harmonisé depuis les cadrages ChatGPT.

Le cadrage v1.1 est soumis à revue sur la branche `docs/cadrage-consolide-v1-1`. Le dépôt a servi à inventorier les chemins à remplacer. Les sources et arbitrages du cadrage sont référencés dans [SOURCES.md](../CADRAGE/SOURCES.md).

## Procédure d'intégration

1. Vérifier le dépôt cible OSIA associé au projet et son état courant ; cela sert à préparer le remplacement, pas à réviser les décisions depuis le code prématuré.
2. Créer une branche de travail depuis l'état courant et inventorier les fichiers suivis. Préserver l'historique Git ; « tout écraser » porte sur le contenu actif, pas sur une réécriture irréversible de l'historique.
3. Remplacer les documents actifs par le contenu de ce dossier. Retirer les anciennes trames, consolidations et spécifications concurrentes. Les fichiers de code/configuration prématurés font partie du nettoyage demandé lors de cette intégration ; les suppressions doivent être visibles dans le diff de la PR.
4. Ne pas ajouter les scripts de génération de cette consolidation, les copies temporaires ou les sources historiques comme instructions actives. Les empreintes et références dans SOURCES suffisent à sa traçabilité.
5. Adapter l'état du projet au résultat réel. Contrôler liens, identifiants et absence de dépendances à des documents supprimés.
6. Faire un commit sur la branche, pousser et ouvrir une PR décrivant le remplacement, les suppressions et les contrôles réellement exécutés. La fusion reste une action du propriétaire.

L'intégration ne doit pas restaurer une hypothèse SQLite, un stockage métier navigateur, une interdiction générale d'authentification ou un statut T4–T8 « à arbitrer ». Elle ne doit pas non plus générer un début d'application ou un fichier de dépendances par anticipation.
