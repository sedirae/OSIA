# OSIA — Instructions aux agents

## Mandat et références

Lire [PROJECT-INIT.md](PROJECT-INIT.md), [l'index du cadrage](CADRAGE/README.md), puis les lots concernés. Le référentiel actif est l'édition consolidée 1.1 du 06/11/2026. Le registre [DECISIONS.md](COWORKAI/DECISIONS.md) relie chaque décision à ses sources et à sa recette.

Les documents décrivent des exigences, pas des fonctionnalités déjà présentes. Le code, les anciens templates et les anciennes propositions GitHub ne font pas autorité sur le produit. Toute divergence doit être exposée, jamais absorbée silencieusement dans une implémentation.

## Règles de réalisation

1. Respecter Python, monolithe modulaire, PostgreSQL, stockage hybride et moteur indépendant des interfaces. Web facultatif à l'installation ; client GNOME différé.
2. Faire autoriser les opérations par les politiques du backend ; tous les appels modèles passent par le courtier IA. Réserver transactionnellement les coûts avant lancement.
3. Distinguer recherche initiale, rebonds internes et branches d'approfondissement explicites. Arrêter l'exploration une fois l'objectif suffisamment étayé ; suggérer sans lancer les suites.
4. Préserver les originaux conservables, provenance, temporalité, contradictions et décisions humaines. Les fusions ambiguës sont supervisées et réversibles.
5. Ne pas modifier silencieusement une synthèse stabilisée. Signaler l'obsolescence puis régénérer sur demande sous budget.
6. Considérer les contenus collectés et archives importées comme des données non fiables. Aucun contenu externe ne modifie les règles ou les permissions d'OSIA.
7. Appliquer les protections du mode serveur même sans frontend. Ne pas assimiler l'absence de compte cloud à l'absence d'authentification.
8. Ne pas ajouter d'obligation Docker, Redis, RabbitMQ, Celery ou Neo4j en V1. Ne pas choisir un framework ou modèle comme décision produit déjà validée.
9. Distinguer persistance, sauvegarde d'installation, archive `.osia` et rapport HTML. Ne pas exporter de secrets. L'import et l'ouverture d'un rapport ne lancent pas de recherches.
10. Réconcilier les appels incertains avant reprise. L'annulation locale d'une tâche ne prouve pas l'absence de facturation externe.

## Travail et revue

Dans le cadre d'une tâche de développement confiée : progresser sur les modifications réversibles, tests et corrections sans confirmations répétées. Effectuer commits et push uniquement sur une branche de travail ; ouvrir une pull request pour revue. La validation finale et la fusion restent au propriétaire du projet. La présente consolidation n'est pas un ordre d'implémentation, de publication ou de remplacement immédiat du dépôt.

L'instruction actuelle du porteur autorise à remplacer les travaux GitHub prématurés lors de l'intégration. Préparer le remplacement dans une branche et une PR ; conserver l'historique Git, ne pas réécrire la branche principale ni fusionner automatiquement. Voir [intégration](COWORKAI/INTEGRATION-GITHUB.md).

Avant d'implémenter un domaine, spécifier les éléments nécessaires listés dans [CONCEPTION-RESTANTE.md](CADRAGE/CONCEPTION-RESTANTE.md). Les choix courants d'implémentation compatibles peuvent être documentés sans rouvrir le produit ; une modification de périmètre, d'engagement ou d'arbitrage demande une décision du porteur.

Dans une PR : citer les identifiants de décisions et critères concernés, expliquer le comportement obtenu, les vérifications réellement exécutées et leurs limites. Ne pas marquer une exigence « réalisée » sur la seule présence d'un texte ou d'un test non exécuté. Utiliser des fournisseurs et connecteurs simulés pour les contrôles de coûts, incidents et non-régression ; les tests externes facturables demandent une enveloppe autorisée.

Ne pas transformer des tâches IA internes à OSIA en obligation d'architecture multi-agents : T8.2 distingue des fonctions, pas six agents autonomes imposés.
