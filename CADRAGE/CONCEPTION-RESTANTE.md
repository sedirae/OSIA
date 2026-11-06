# OSIA — Conception restante et périmètre de livraison

**Édition 1.1 — 06/11/2026.** Le cadrage A–D et T1–T8 est clos. Les éléments suivants précisent la réalisation ; ils ne rouvrent pas ses décisions.

## 1. Engagements initiaux et reports explicites

| Sujet | Statut acquis | Conséquence pour le périmètre V1 |
| --- | --- | --- |
| Moteur Linux Python, monolithe modulaire, PostgreSQL | Décisions structurantes T1–T3 | Base de réalisation ; pas de prototype navigateur faisant autorité |
| Desktop/Server, distribution commune et web optionnel | Principes T1/T3 | Préserver les modes et le fonctionnement sans frontend |
| Première interface graphique web | T1 ; C | Client natif non requis |
| Noyau de connecteurs préintégrés | B1 explicitement première version | Déterminer la liste ; ne pas reporter tout accès aux sources |
| Socle de sources françaises et internationales | B2.3 | Choisir une couverture initiale cohérente ; catalogue non limité structurellement à un pays |
| Connecteurs officiels prioritaires | T3.8, T5.1 | Ne pas imposer un écosystème tiers complet avant une première version |
| Export portable manuel | D5.3 explicitement périmètre initial | Préserver cet engagement lors du découpage |
| Aucun compte cloud obligatoire ; absence de gestion collaborative imposée | A/D, précisés par T5.7 | Authentification serveur obligatoire, sans plateforme SaaS à inventer |
| Journalisation structurée | T3.13 | Observabilité avancée exhaustive différée |
| Client natif GNOME Rust/GTK4/libadwaita | T1 | Ultérieur, hors V1 |
| Surveillance automatisée des anciennes investigations | A §20 | Piste V2 ; distincte de la reprise après incident |
| Composants Rust du moteur | T3.1 | Éventuels plus tard sur besoin démontré |
| Microservices, Redis/RabbitMQ/Celery, Neo4j, Docker | T3–T6 | Aucune obligation V1 |
| Sauvegardes techniques planifiées | T2.5 validé, activation facultative ; D5 ne les impose pas initialement | Sauvegarde manuelle en V1. Programmation reportée (V1.1) |
| Signature des archives | T7.2 | Facultative, calendrier non fixé |
| Sauvegardes cloud et bibliothèques/corpus | T2 §4 | Pistes séparées à étudier, sans fournisseur ni calendrier validés |

Le découpage validé entre première livraison et évolutions figure dans [PERIMETRE-V1.md](PERIMETRE-V1.md). Les autres capacités font partie de la cible.

## 2. Détails à produire avant l'implémentation du domaine

| ID | Domaine et livrable | Décisions déjà closes à respecter | Vérification attendue |
| --- | --- | --- | --- |
| CON-01 | Distribution Linux, versions supportées, installation PostgreSQL, modes et modules | T1, T2.1/2.3, T3.3 | Installation propre, migration de mode maîtrisée, backend sans web |
| CON-02 | Schémas, identifiants, migrations et protocole base/fichiers | T2.2/2.4, T3.7, T6 | Coupures aux points d'écriture, intégrité, références partagées |
| CON-03 | Machine à états, ordonnanceur, concurrence, reprise et arrêt | T3.6/3.12, T4 | Concurrence, expiration, crash et appels incertains |
| CON-04 | Registre financier, devises/unités, période mensuelle/fuseau, réservations et rapprochement | A.9, B6, D3/D7, T8.4 | Aucune double réservation ; coût inconnu bloqué ; reprise sûre |
| CON-05 | Autorisations, identité/session serveur, TLS et sécurité locale | T5.7, D6 | Refus d'accès non autorisé même sans frontend |
| CON-06 | Isolation Linux et contrôle central réseau/destinations | T5.1–T5.6 | Restrictions fichiers/réseau, redirections et contenus adverses |
| CON-07 | Manifestes, SDK/contrats connecteurs, tests sémantiques et maintenance | B1/B7, T3.8, T5 | Connecteur défaillant isolé ; changements sensibles non activés implicitement |
| CON-08 | Catalogue initial, conditions d'accès, coûts et conservation par source | B2/B3/B7 | Capacités réellement vérifiées et date de contrôle |
| CON-09 | Schémas d'assertions, preuves, graphes et contextes ; identité et propagation | A9–A12, C5/C6, T6 | Homonymes, fusion/annulation, contradictions, décisions locales |
| CON-10 | Critères d'objectif suffisamment étayé et confiance multidimensionnelle | A5, B5, C3, T4.6, T6.7 | Cas positifs/négatifs/partiels, pas de score opaque imposé |
| CON-11 | Courtier, adaptateurs, modèles/rôles, schémas de réponses, tests et repli | D2, T8 | Sorties invalides rejetées ; aucun repli hors permission/budget |
| CON-12 | API REST, événements SSE, resynchronisation, versions et erreurs | T1, T3.7, T4.9 | Client déconnecté retrouve l'état sans déclencher des tâches en double |
| CON-13 | Paramètres, profils, valeurs par défaut, TTL, quotas et seuils | D3/D7, T4.8 | Defaults non permissifs par accident ; restrictions supérieures appliquées |
| CON-14 | Spécification `.osia`, manifestes, migrations, exclusions, collisions et import | D5, T7 | Aller-retour hors ligne, export partiel qualifié, corruption refusée |
| CON-15 | Profil cryptographique, enveloppe, Argon2id, clés, verrouillage et récupération | D2/D6, T2.7, T7.3 | Confidentialité des métadonnées et échec contrôlé au déverrouillage |
| CON-16 | Sauvegarde cohérente à chaud, rétention, restauration et coffre | T2.5–T2.8, T7.9 | Base/fichiers d'un même état, reprise sur installation de test |
| CON-17 | Maquettes, charte, accessibilité, performances graphe et HTML | C, D5, T6.9/T7.5 | Parcours utilisables, consultation hors ligne sans réseau automatique |
| CON-18 | Journal technique, audit sécurité et historique métier, rétentions | C6, D4, T3.13, T5.9 | Finalités distinctes ; secrets absents ; historique métier conservé |
| CON-19 | Jeux de recette, CI et métriques d'évaluation par tâche | T3.14, T8.10 | Tests reproductibles hors ligne et relevés de résultats réels |

Les choix de schéma, de nommage, de bibliothèques et de versions compatibles peuvent être documentés comme décisions de conception. Le porteur arbitre les changements de produit, de périmètre, de coût autorisé ou de garantie ; aucune approbation répétitive n'est nécessaire pour appliquer une décision déjà acquise dans le cadre d'un mandat.

## 3. Ordre de travail conseillé, non calendrier validé

Commencer par modes d'installation, persistance, contrats métier, politiques et budgets, puis une investigation verticale avec connecteurs et IA simulés. Ajouter les intégrations réelles autorisées, le graphe et la correction, puis les parcours de restitution, sauvegarde et import/export selon le périmètre validé. Les propriétés transversales de sécurité, provenance et reprise sont conçues dès le socle et vérifiées à chaque tranche.

Ce séquencement est une aide de conception, pas un nouvel arbitrage de roadmap ni un ordre de démarrer le développement.

## 4. Questions réellement encore ouvertes

Les fonctions V1, le catalogue de départ, les modèles initiaux, les valeurs par défaut, les conventions d’interopérabilité et la charte sont actés dans [PERIMETRE-V1.md](PERIMETRE-V1.md). Il reste à qualifier les intégrations, spécifier les schémas et protocoles détaillés, compléter les paramètres de conception non chiffrés, produire les maquettes et découper la réalisation en tranches. Le détail historique de la numérotation T1.x n'est pas récupéré ; les sept thèmes EXEC documentent les principes corroborés sans changer leur fond. Il n'y a pas lieu de rouvrir Python, PostgreSQL ou les 46 décisions T4–T8.
