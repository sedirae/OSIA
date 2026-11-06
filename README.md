# OSIA — Investigation OSINT assistée et supervisée

**État du projet : cadrage fonctionnel achevé (lots A–D, 05/11/2026) ; conception technique transversale en cours.**

OSIA vise à accélérer la recherche sur des sources publiques : découverte et rapprochement d'entités, exploration contrôlée de leurs liens, conservation des preuves et contradictions, restitution navigable, maîtrise des coûts API et données locales portables.

> **Important :** ce dépôt a été initialisé depuis le template **AI-first Project Template**. Les fichiers génériques issus du modèle ne sont pas, en eux-mêmes, des décisions produit validées. La structure de collaboration avec les IA est conservée et progressivement personnalisée.

## Où en est le cadrage ?

- **Lot A — Fonctionnement des investigations :** validé dans les conversations de cadrage ; Markdown consolidé v1.0 à importer.
- **Lot B — Sources et connecteurs :** B1–B7 validés ; Markdown consolidé v1.0 à importer.
- **Lot C — Interface et restitution :** C1–C7 validés ; Markdown consolidé v1.0 à importer.
- **Lot D — Paramètres et données locales :** D1–D7 validés ; Markdown consolidé v1.0 à importer.
- **Conception technique transversale :** document **PROPOSÉ v0.1** dans [CADRAGE/TECHNIQUE.md](CADRAGE/TECHNIQUE.md) ; le **lot T1 (exécution et distribution) est VALIDÉ v1.0** dans [CADRAGE/T1-EXECUTION-DISTRIBUTION.md](CADRAGE/T1-EXECUTION-DISTRIBUTION.md). Les autres choix restent à arbitrer.

## Références du dépôt

| Fichier | Rôle | État actuel |
| --- | --- | --- |
| [CADRAGE/README.md](CADRAGE/README.md) | Index du cadrage et suivi documentaire | Adapté à OSIA |
| [CADRAGE/TECHNIQUE.md](CADRAGE/TECHNIQUE.md) | Architecture et conception transversale | PROPOSÉ v0.1 (T1 validé) |
| [CADRAGE/T1-EXECUTION-DISTRIBUTION.md](CADRAGE/T1-EXECUTION-DISTRIBUTION.md) | Décisions d'exécution, installation et distribution Linux | **VALIDÉ v1.0** |
| [CADRAGE/FONCTIONNEL.md](CADRAGE/FONCTIONNEL.md) | Point d'entrée du fonctionnel | **Trame template non normative**, dans l'attente de l'import A–D |
| [CADRAGE/DESIGN.md](CADRAGE/DESIGN.md) | Design et expérience | **Trame template non normative**, dans l'attente de sa personnalisation |
| [AGENTS.md](AGENTS.md) | Règles stables de collaboration avec les agents | Template à personnaliser |
| [PROJECT-INIT.md](PROJECT-INIT.md) | Procédure INITIALISATION / ÉVOLUTION / RÉVISION | Template conservé |
| [roadmap/](roadmap/README.md) | Spécifications des fonctionnalités | Non initialisée |
| [COWORKAI/](COWORKAI/README.md) | Missions, décisions et rapports d'exécution | Non initialisé |

## Règles de travail

- Les arbitrages fonctionnels des lots A–D restent la référence ; toute proposition technique doit leur être confrontée.
- Statuts documentaires : **VALIDÉ**, **PROPOSÉ**, **OUVERT**, **REPORTÉ**, **REMPLACÉ**.
- Toute évolution sur branche de travail, tests réellement effectués et pull request ; la fusion dans main relève de l'utilisateur.
- Les secrets, données sensibles, dépenses API et opérations irréversibles font l'objet de garde-fous et d'autorisations explicites.

**Étape suivante :** importer fidèlement les quatre Markdown fonctionnels A–D v1.0, puis poursuivre les arbitrages techniques T2–T8 (T1 étant validé).
