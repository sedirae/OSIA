# Journal des décisions significatives — COWORKAI

**Statut :** journal vivant des arbitrages significatifs du projet OSIA.

Ce fichier consigne le **contexte et la justification** des choix significatifs survenus pendant la collaboration. Ce n'est **pas** un doublon du cadrage : les décisions durables applicables doivent figurer dans `CADRAGE/` et les spécifications pertinentes.

## Entrées

### 06/11/2026 — Lot T1, exécution et distribution Linux native

- **Décision prise par :** utilisateur, au terme des arbitrages T1.1–T1.7 du cadrage OSIA.
- **Statut : VALIDÉ.** Linux exclusivement pour le moteur, architecture cœur/API indépendante des interfaces, web V1, client GNOME/Rust différé ; installation native unifiée, choix poste/serveur, API REST + SSE, mises à jour manuelles avec notification, accès distant modulable et sécurisé.
- **Conséquences :** aucun Docker officiel requis, aucun support moteur Windows/macOS, pas de client GTK livré en V1 ; API toujours active même sans frontend web ; déploiement distant sous contrôle explicite. Les détails de paquet, réseau, authentification et autres lots techniques restent à arbitrer.
- **Source de vérité :** [CADRAGE/T1-EXECUTION-DISTRIBUTION.md](../CADRAGE/T1-EXECUTION-DISTRIBUTION.md), lié depuis [CADRAGE/TECHNIQUE.md](../CADRAGE/TECHNIQUE.md).

Lorsqu'une décision significative est prise, ajouter une entrée concise selon cette structure :

- **Date :** date réelle du choix.
- **Sujet / contexte :** problème ou arbitrage traité.
- **Ancien choix :** si une décision antérieure est remplacée.
- **Nouveau choix :** description concrète et statut (`VALIDÉ`, `PROPOSÉ`, `OUVERT`, `REPORTÉ`, `REMPLACÉ`).
- **Décision prise par / preuve :** personne, validation ou référence accessible ; ne pas inventer d'accord.
- **Motif et conséquences :** raison, impact et risques.
- **Références actualisées :** cadrage, roadmap, mission, PR/commit si disponibles.

**Ne pas consigner** chaque commande, commit ou question mineure ; Git et les rapports d'exécution suffisent. Une décision sans validation utilisateur ne doit pas être notée comme `VALIDÉE`.
