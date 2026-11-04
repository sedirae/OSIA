# AI-first Project Template

Modèle documentaire et organisationnel **agnostique des technologies et des fournisseurs d'IA** pour lancer et faire évoluer des projets GitHub avec plusieurs agents.

> **Ce dépôt est un template, pas une application.** Les cadrages sont volontairement non remplis. Ne pas interpréter les exemples, rubriques ou champs à compléter comme des décisions validées.

## Démarrer un nouveau projet

1. Créer le dépôt du projet à partir de ce modèle (fonction **Use this template** si ce dépôt est configuré comme template GitHub), ou reprendre son contenu de manière contrôlée.
2. Discuter librement du projet avec un agent, éventuellement dans plusieurs conversations.
3. Lorsqu'il est temps de formaliser le projet, demander à l'agent d'appliquer [PROJECT-INIT.md](PROJECT-INIT.md) en mode **INITIALISATION**, avec les sources auxquelles il a réellement accès.
4. Valider les arbitrages importants. L'agent complète le cadrage, prépare les premières missions et propose une **PR**.
5. Une fois le cadrage validé et intégré par l'utilisateur, commencer le développement selon [AGENTS.md](AGENTS.md).

Pour une fonctionnalité nouvelle, demander le mode **ÉVOLUTION** ; pour un changement de décision existante, le mode **RÉVISION**.

## Où sont les informations ?

| Chemin | Fonction |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Règles stables de collaboration, autonomie et escalade |
| [PROJECT-INIT.md](PROJECT-INIT.md) | Procédure INITIALISATION / ÉVOLUTION / RÉVISION |
| [CADRAGE/](CADRAGE/README.md) | Références fonctionnelles, techniques et design |
| [roadmap/](roadmap/README.md) | Spécifications des évolutions fonctionnelles |
| [COWORKAI/](COWORKAI/README.md) | Missions, rapports et décisions vivantes |
| [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) | Support des revues et des validations |

Les dossiers `COWORKAI/missions/`, `COWORKAI/rapports/` et `CADRAGE/assets/` sont disponibles comme emplacements facultatifs. Les workflows CI et le code applicatif sont ajoutés **selon le projet**, pas imposés par ce template.

## Principes

- Une IA peut **proposer**, mais ne doit pas inventer de décisions validées.
- Les informations durables vivent dans le cadrage, les tâches dans `COWORKAI/`, les spécifications dans `roadmap/`.
- Chaque travail significatif doit être **vérifiable** : tests réels, limites et liens Git.
- **Aucun merge dans `main`, déploiement ou opération sensible par défaut** : l'autorisation de l'utilisateur reste nécessaire.
- Une modification du template **ne synchronise pas automatiquement** ses copies dans les projets créés. Les futures mises à jour seront à étudier séparément, idéalement via PR.

## État du modèle

Première proposition à relire ; elle contient la procédure `PROJECT-INIT.md` **v0.3** et des fichiers de cadrage génériques. Aucune stack applicative, CI ou infrastructure de production n'est prévue dans cette version.
