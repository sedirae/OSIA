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
| [10-securite-autorisations.md](10-securite-autorisations.md) | CON-05 : identité/session serveur (jeton admin + sessions expirables/révocables), autorisations mono-utilisateur, TLS pour accès distants, garde-fous de démarrage, journal d'audit de sécurité distinct (T5.9), sécurité locale des fichiers | T1, T5.7, T5.9, D6, V1.1 |
| [11-isolation-reseau-contenus.md](11-isolation-reseau-contenus.md) | CON-06 : politique réseau centralisée anti-SSRF (NetworkGuard), niveaux de confiance des connecteurs (T5.1), coffre de secrets chiffré (T5.5), isolation par rlimits (T5.2), validation des provenances (T5.6) | T5.1–T5.6, T5.9, V1.4 |
| [12-connecteurs-catalogue.md](12-connecteurs-catalogue.md) | CON-07/CON-08 : connecteurs réels V1.2 (recherche-entreprises, BODACC, GLEIF, web par URL) via NetworkGuard, manifestes/fiches B7 §9.4, contrôles sémantiques, surveillance de santé manuelle (B7 §9.1) | B1/B2/B3/B7, T3.8, T5, V1.2 |
| [13-courtier-ia.md](13-courtier-ia.md) | CON-11 : adaptateurs IA réels (Mistral cloud Small 4 + local OpenAI-compatible) via NetworkGuard, modèles par rôle, sorties structurées validées (T8.6), repli local→cloud soumis à autorisation de transmission + budget (T8.8/T8.9, V1.3), API/CLI ai | D2, T8, V1.3 |
| [14-parametres-profils-quotas.md](14-parametres-profils-quotas.md) | CON-13 : surcharges de limites clampées (jamais au-dessus du profil/garde-fous V1.4), cache source TTL 24 h (B-ACC-06), paramètres globaux validés/audités (D7 §9), alertes de plafonds à 80 %, profils personnalisés, API/CLI settings+profiles | D3/D7, T4.8, V1.4, D4 §6 |

## État

Tranche 1 (socle) livrée : CON-01 à CON-04 + contrats transversaux du socle. Tranche 2 (graphe T6 + correction) livrée : CON-09 + CON-10. Tranche 3 (restitution T7 + sauvegarde T2.6) livrée : CON-14 + CON-15 + CON-16 + rapport HTML autonome. Tranche 4 (web C) livrée : CON-17 + complément client CON-12 ([09](09-interface-web.md)). Tranche 5 (sécurité) livrée : CON-05 ([10](10-securite-autorisations.md)). Tranche 6 (isolation réseau) livrée : CON-06 ([11](11-isolation-reseau-contenus.md)). Tranche 7 (connecteurs réels V1.2) livrée : CON-07/CON-08 ([12](12-connecteurs-catalogue.md)). Tranche 8 (courtier IA réel V1.3) livrée : CON-11 ([13](13-courtier-ia.md)). Tranche 9 (paramètres/profils/quotas V1.4) livrée : CON-13 ([14](14-parametres-profils-quotas.md)). Suivront par tranches séparées : CON-18–CON-19 selon CONCEPTION-RESTANTE.
