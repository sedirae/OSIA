# OSIA — Conception détaillée (travail en cours)

Ces documents sont les **choix d'implémentation** du moteur, produits tranche par tranche selon `CADRAGE/CONCEPTION-RESTANTE.md` (CON-01…CON-19) et `PROJECT-INIT.md`. Ils ne rouvrent aucun arbitrage validé (lots A–D, T1–T8, périmètre V1.1–V1.6) ; toute divergence avec un arbitrage doit être signalée, pas absorbée.

Chaque document cite les décisions respectées et distingue *exigence* (cadrage), *choix d'implémentation* (ce document) et *vérification réellement exécutée* (tests, PR).

## Index

| Document | Couvre | Décisions principales |
| --- | --- | --- |
| [01-installation-modes.md](01-installation-modes.md) | CON-01 : emplacements, modes Desktop/Server, PostgreSQL, CLI/API sans web | T1 EXEC-01/02/03, T2.1/T2.3, T3.3, T5.7 |
| [02-persistance-base-fichiers.md](02-persistance-base-fichiers.md) | CON-02 : schéma SQL v1, migrations, protocole de cohérence base/fichiers, déduplication SHA-256 | T2.2/T2.4, D1, OSIA-I-10, OSIA-I-14 |
| [03-etats-ordonnanceur-reprise.md](03-etats-ordonnanceur-reprise.md) | CON-03 : machine à états, ordonnanceur persistant PostgreSQL, concurrence, reprise et réconciliation | T3.5/T3.6/T3.12, T4.2/T4.7/T4.8, OSIA-I-09 |
| [04-protocole-financier.md](04-protocole-financier.md) | CON-04 : devise/période, plafonds hiérarchiques, réservations transactionnelles, réconciliation | B6, T8.4, D3/D7, V1.4, OSIA-I-02 |
| [05-contrats-transversaux.md](05-contrats-transversaux.md) | Contrats internes typés, événements/SSE, API REST `/api/v1`, contrat connecteur, contrat courtier IA, sécurité des modes | T3.7/T3.9/T3.13, T4.9, T5.7, V1.3/V1.5, CON-07/CON-11/CON-12 |
| [06-graphe-identite-decisions.md](06-graphe-identite-decisions.md) | CON-09 : entités/identifiants, relations sourcées, assertions, rapprochement d'identité, fusions supervisées réversibles, décisions historisées | A9–A12, C5/C6, T6.1–T6.9 |
| [07-etayage-confiance-objectif.md](07-etayage-confiance-objectif.md) | CON-10 : confiance multidimensionnelle qualitative, natures, critère d'objectif suffisamment étayé décidé par le moteur | A5, B5, C3, T4.6, T6.7, V1.4 |
| [08-restitution-sauvegarde.md](08-restitution-sauvegarde.md) | CON-14 (archive `.osia` v1.0), CON-15 (AES-256-GCM + Argon2id facultatif), CON-16 (sauvegarde à chaud manuelle), restitution HTML autonome T7.5 | D5, T7.1–T7.9, T2.5/T2.6, V1.1/V1.5/V1.6 |
| [09-interface-web.md](09-interface-web.md) | CON-17 + complément client de CON-12 : interface web statique vanilla servie par le moteur (`/` + `/static/*`), page unique C1, graphe SVG 3 modes, SSE par curseur, auth mode serveur sur toutes les routes | C1–C7, REC-C-01…19, V1.1/V1.5/V1.6, T4.9, T5.7, T6.9/T7.5, D5 |

## État

Tranche 1 (socle) livrée : CON-01 à CON-04 + contrats transversaux du socle. Tranche 2 (graphe T6 + correction) livrée : CON-09 + CON-10. Tranche 3 (restitution T7 + sauvegarde T2.6) livrée : CON-14 + CON-15 + CON-16 + rapport HTML autonome. Tranche 4 (web C) livrée : CON-17 + complément client CON-12 ([09](09-interface-web.md)). Suivront par tranches séparées : CON-05–CON-08/CON-11–CON-13/CON-18–CON-19 selon CONCEPTION-RESTANTE.
