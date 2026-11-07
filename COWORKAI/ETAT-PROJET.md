# OSIA — État du projet

**Date : 06/11/2026. Édition de cadrage : 1.1.** Périmètre V1 validé (six arbitrages V1.1–V1.6, PR #3).

| Élément | État |
| --- | --- |
| A–D | Arbitrages validés et clôturés ; textes harmonisés |
| T1 | Principes clôturés et corroborés ; regroupements EXEC, numérotation originale non certifiée |
| T2–T8 | Arbitrages validés et clôturés ; textes harmonisés |
| Consolidation générale | Produite ; audit documentaire et traçabilité dans CADRAGE |
| Périmètre V1 | Six arbitrages validés le 06/11/2026. Voir [PERIMETRE-V1.md](../CADRAGE/PERIMETRE-V1.md). |
| Conception détaillée | Socle produit (CON-01 à CON-04 + contrats transversaux) dans [CONCEPTION/](../CONCEPTION/README.md) ; lots suivants à produire selon CONCEPTION-RESTANTE |
| Réalisation du produit | Tranche 1 (socle) livrée sur branche `vibe/socle-moteur-v1-7b14b9` : moteur Python modulaire, persistance PostgreSQL+fichiers, politiques/budgets, ordonnanceur, orchestrateur, connecteurs/IA simulés, API REST/SSE, CLI |
| Recette applicative | 25 tests pytest exécutés et passés (branche de travail, PostgreSQL embarqué `pgserver`) ; recette applicative complète non exécutée |
| GitHub | Cadrage v1.1 fusionné sur `main` (PR #2) ; périmètre V1 fusionné (PR #3) ; tranche socle en PR draft |

Mettre à jour ce fichier au fil du travail en séparant décision, spécification, implémentation et vérification. Les agents ne doivent pas transformer l'existence d'un document de recette en validation du logiciel.
