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

## État

Tranche 1 (socle) en cours : CON-01 à CON-04 + contrats transversaux du socle. Les lots suivants (graphe T6, restitution T7, web C) suivront par tranches séparées.
