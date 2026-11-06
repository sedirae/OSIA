# OSIA — Audit de cohérence et rapport de consolidation

**Édition 1.1 — 6 novembre 2026.** Rapport documentaire accompagnant le référentiel de remplacement.

## 1. Conclusion de l’analyse

Les huit documents Markdown accessibles ont été examinés intégralement. Leurs décisions structurantes convergent. Les écarts repérés tiennent principalement aux évolutions chronologiques du stockage et de l’architecture, à des mots employés avec plusieurs sens (branche, sauvegarde, local, reprise) et à des renvois devenus obsolètes. Les harmonisations décrites ci-dessous sont intégrées aux documents actifs.

Le cadrage fonctionnel et technique est clos ; il reste à produire les spécifications détaillées et le périmètre exact de V1. Aucun nouvel arbitrage de fond n’a été inventé pour combler ces travaux. Le référentiel n’utilise pas le dépôt GitHub prématuré comme autorité.

Une limite de traçabilité demeure pour **T1** : ses principes sont corroborés par les textes techniques validés, mais aucun Markdown autonome et aucune correspondance complète de la numérotation originale n’ont été retrouvés. Les sept thèmes EXEC rendent cette limite explicite. La réserve antérieure sur **T4–T8 est levée** grâce au texte complet retrouvé.

## 2. Méthode et portée

Inventaire par titre et dossier, recherche complémentaire, lecture des huit fichiers, comparaison des décisions/contraintes/scénarios, harmonisation ciblée des formulations et vérification des identifiants/liens. Les sources et leurs empreintes sont dans [SOURCES.md](SOURCES.md). Les formulations validées priment sur les exemples ; une décision technique ultérieure précise ou remplace une hypothèse antérieure uniquement lorsque son périmètre le justifie.

Aucune recherche de technologies nouvelles, de prix ou de réglementation n’a été substituée aux décisions du projet. Les droits d’accès, tarifs, versions et politiques de chaque intégration seront vérifiés lors de sa conception. Ce rapport ne constitue ni une revue de code, ni un audit de sécurité exécuté sur une application.

## 3. Écarts et résolutions

Les identifiants COH-* qualifient des constatations et résolutions éditoriales, pas 30 nouveaux arbitrages. « Évolution actée » applique une décision ultérieure ; « précision » articule des exigences compatibles ; « limite » signale ce que la documentation accessible ne permet pas d’attester.

| ID | Nature | Constat | Formulation retenue | Fondement |
| --- | --- | --- | --- | --- |
| COH-01 | Évolution actée | A §16 et D1 envisagent le navigateur comme stockage métier ; T2 retient PostgreSQL | État métier et budgets dans le backend/PostgreSQL ; fichiers de preuves séparés. Le stockage navigateur ne fait pas autorité. | T2.1–T2.4, T3.3, T3.11 |
| COH-02 | Évolution actée | D2.5 évoque un intermédiaire local facultatif | Moteur obligatoire, interfaces séparées ; appels modèles via courtier. Aucun cloud OSIA obligatoire. | T1, T3.3/3.9, T8.1 |
| COH-03 | Précision de portée | A annonce aucun compte ; T5.7 impose l’authentification serveur | Absence de compte cloud et de gestion collaborative imposée ; authentification/sessions/autorisations obligatoires en mode Server. | A §16, D6, T5.7 |
| COH-04 | Précision de portée | Local-first décrit d’abord un poste, puis un serveur est prévu | Local signifie sur l’hôte Linux choisi ; réseau et fournisseurs autorisés restent possibles ; mode serveur sans exposition distante implicite. | D1/D6, T1, T5.7 |
| COH-05 | Précision de terminologie | A/C emploient sauvegarde manuelle ; D1 enregistre automatiquement et T2 prévoit une programmation | Distinguer persistance automatique, export portable manuel, sauvegarde technique manuelle et programmation facultative. Aucun export automatique à la clôture. | C7-18, D1/D5, T2.5/2.6, T7.9 |
| COH-06 | Précision de portée | A §16 renvoie reprise/actualisation à V2 ; D7/T3/T4 prévoient la reprise | La surveillance automatisée de recherches anciennes est différée ; reprise après incident, consultation et restauration d’archives sont des capacités distinctes. | A §20, D5/D7, T3.6, T4.7 |
| COH-07 | Harmonisation fonctionnelle | C2 et son parcours peuvent laisser croire que l’objectif est obligatoire | Objectif facultatif ; indices suffisants pour l’investigation exploratoire. | A.1, C2-01 |
| COH-08 | Précision de vocabulaire | A autorise l’exploration automatique ; C7 et les invariants techniques exigent une action pour une branche | Tâches/pistes/rebonds internes sous autorisation existante ; branche d’approfondissement explicite avec objectif et limites propres. Pas d’approbation à chaque rebond. | A1/A3/A7, C7, T4.1/4.3 |
| COH-09 | Harmonisation fonctionnelle | C3/C6 parlent de mise à jour de synthèse ; A11 impose actualisation sur demande | Synthèse provisoire évolutive pendant l’exécution ; synthèse stabilisée signalée obsolète puis régénérée sur demande ; versions conservées. | A11, C3-04/06, C6-15, C7-20 |
| COH-10 | Précision de réversibilité | C6-07 parle de restaurer un état antérieur ; A demande de tenir compte des connaissances nouvelles | Annuler par opération inverse historisée et réévaluation actuelle, sans rétablir aveuglément une conclusion ancienne. | A.11.4, C6-07/14, T6.5 |
| COH-11 | Précision de confiance | A mentionne une jauge ; B/C/T6 refusent un score opaque | Indicateur explicable multidimensionnel ; aucun pourcentage de vérité non calibré. Nature, étayage, décision humaine et pertinence distincts. | A.4, B5, C3/C6, T6.7 |
| COH-12 | Précision des fusions | A permet un regroupement établi ; C exige supervision des rapprochements ambigus | Automatisation uniquement pour correspondances techniques certaines selon règles explicites ; cas ambigus supervisés, toutes fusions traçables et réversibles. | A.3, C5/C6, T6.4/6.5 |
| COH-13 | Extension compatible | A décrit un graphe interbranches ; D/T6 étendent le partage interinvestigations | Référentiel commun avec vues et décisions contextuelles ; préserver objectifs, conclusions, droits et provenance. Pas de propagation globale d’un rejet local de pertinence. | A9/A12, D4, T6.8 |
| COH-14 | Précision de conservation | Conserver les originaux pourrait être lu comme tout copier intégralement | Conserver les pièces/extraits permis et les références ; documenter les limites. La purge ne supprime pas une preuve requise par une conclusion conservée. | B5/B7, D4, T2.8 |
| COH-15 | Précision de sécurité | Sources activées par défaut et secrets non persistés pourraient être lus comme permission automatique | Seules les sources configurées, disponibles et autorisées sont admissibles ; activation ne signifie pas interrogation. Aucun appel sans politiques, permissions et budget. | A.2, B4/B6, D2, T5 |
| COH-16 | Précision des limites | D3 qualifie certains réglages de facultatifs ; A/T4 imposent des garde-fous | Surcharge utilisateur facultative, protections effectives obligatoires. Les valeurs par défaut restent à spécifier ; pas de plafonds silencieusement illimités. | A.9, D3/D7, T4.8 |
| COH-17 | Précision financière | REC-D3-02 pourrait promettre une facture externe jamais supérieure aux estimations | OSIA interdit tout nouvel engagement non autorisé ; coûts bornés/réservés/réconciliés ; écarts de facture externe explicitement distingués. | B6, T3.11, T8.4 |
| COH-18 | Précision de reprise | Une annulation ou un timeout pourrait être traité comme une absence de coût | Ne pas réémettre ni considérer l’enveloppe disponible sur cette seule base ; réconcilier le résultat externe incertain. | D7, T3.6/3.12, T4.7, T8.4 |
| COH-19 | Précision de restitution | Arrêt au budget/objectif et synthèse finale peuvent demander un dernier appel | Arrêter l’exploration ; restitution sur acquis. Une génération finale reste sous budget ; sinon conserver résultats et dernière synthèse qualifiée. Prévoir cette étape dans le budget initial. | A5, C3-05, D3, T8.4 |
| COH-20 | Précision de sécurité | T5.4 autorise des ressources locales/privées ; A fixe les sources publiques | Une autorisation technique légitime, par exemple service configuré, ne transforme pas OSIA en outil d’accès aux espaces privés ; pas d’ouverture réseau arbitraire depuis les contenus collectés. | A §0.2, B3, T5.4/5.8 |
| COH-21 | Précision cryptographique | La synthèse provisoire peut figer AES-256-GCM comme unique algorithme | T7.3 conserve un chiffrement authentifié, AES-256-GCM comme exemple, Argon2id pour dérivation ; profil/sérialisation à concevoir. Ne pas confondre intégrité, authentification du chiffrement et signature auteur. | D5.4, T7.2/7.3 |
| COH-22 | Précision des exports | HTML autonome pourrait interdire toute interactivité ou imposer un fichier sans exception | Scripts de restitution maîtrisés permis ; aucun contenu actif de source ni appel automatique. Fichier unique privilégié ; pièces associées possibles sur choix explicite pour gros volumes. | D5.1, T7.5 |
| COH-23 | Précision des sauvegardes | Archive logique complète et sauvegarde technique peuvent être confondues ; coffre éventuellement persistant | `.osia` exporte les dossiers/paramètres non sensibles, jamais les secrets ; sauvegarde d’installation distincte. Gestion du coffre dans la sauvegarde technique à spécifier sans exporter les secrets en clair. | D2/D5, T2.6/2.7, T5.5, T7.9 |
| COH-24 | Correction de statut | La consolidation provisoire manque du texte T4–T8 et laisse des réserves de couverture | Texte complet retrouvé et analysé : 46 décisions préservées et réparties en cinq fichiers. Réserve T4–T8 levée ; statut des lots clôturé. | SRC-T4T8, SRC-P |
| COH-25 | Correction documentaire | Renvois vers C/D à traiter, choix de base encore ouverts, prochaine étape obsolète | Renvois mis à jour ; principes clos distingués des schémas, paramètres, maquettes et intégrations encore à concevoir. | A–D, T2/T3, SRC-T4T8 §10 |
| COH-26 | Correction d’identifiants | INV-01… du lot D et du document technique ont des sens différents ; A5 ≠ A.5 | D-INV-* dans D ; OSIA-I-* pour synthèse transversale ; arbitrages A1–12 distingués des thèmes A.1–13. | SRC-A §19, SRC-D §10, SRC-T4T8 §7 |
| COH-27 | Précision de périmètre | Cible exhaustive et V1 non délimitée ; quelques engagements initiaux et reports sont déjà explicites | Table des engagements initiaux/reports conservée ; V1 détaillée à établir, sans transformer toutes les capacités en obligations immédiates ni reporter silencieusement les obligations initiales. | B1/B2, D5, T3.13, SRC-T4T8 §1.3/10 |
| COH-28 | Précision de distribution | Mode Desktop peut être confondu avec le client GTK ; paquet commun avec frontend obligatoire | Mode poste/serveur pilote modules et paramètres ; web installable facultativement ; client GNOME différé ; API et moteur fonctionnent sans frontend. | CTX-T1, SRC-T3 §1/3.3, T5.7 |
| COH-29 | Précision de maintenance | B7 autorise des corrections simples automatiques ; T1 prévoit mises à jour manuelles | Maintenance préautorisée et non sensible distincte de mise à jour applicative ; code exécutable, permissions, accès et tarifs demandent validation avant activation. | B7, T1 EXEC-06 |
| COH-30 | Limite de provenance | Aucun T1 autonome retrouvé ; la synthèse précédente citait une PR comme source | Principes repris des rappels des textes validés et du contexte retrouvé. Identifiants éditoriaux EXEC-01–07 ; correspondance originale T1.x non certifiée. Aucun contenu GitHub utilisé comme autorité. | SRC-T3, SRC-T4T8, CTX-T1 |

## 4. Contrôle de couverture

| Ensemble | Résultat documentaire |
| --- | --- |
| A | 12 arbitrages A1–A12, 13 thèmes A.1–A.13 et 15 scénarios conservés |
| B | 7 arbitrages et 16 critères conservés ; catalogue candidat maintenu comme tel |
| C | 7 arbitrages, 96 identifiants de règles détaillées et 19 critères conservés |
| D | 7 arbitrages, 19 critères et 10 invariants conservés ; invariants renommés D-INV |
| T2–T3 | 8 + 14 arbitrages conservés |
| T4–T8 | 46 arbitrages détaillés conservés, sans exception |
| T1 | 7 thèmes EXEC consolidés ; pas de numéro original inventé |
| Recette | 69 scénarios fonctionnels d’origine + 75 techniques dérivés + 12 transversaux |
| Sources | 8 Markdown, 226 389 octets, empreintes SHA-256 enregistrées |

## 5. Vérifications du livrable

Les contrôles automatisés de cette consolidation vérifient : présence de chaque identifiant de décision, conservation des 96 règles C et des 69 critères fonctionnels, conservation textuelle des 46 sections T4–T8 hors normalisation des titres, association des 108 lignes de registre à des critères existants, validité des liens locaux et cohérence du paquet/du document monofichier.
Les scénarios de recette sont des exigences de vérification futures. **Aucun résultat de test de l’application OSIA n’est revendiqué.** Le résultat des contrôles documentaires effectifs est consigné dans [CONTROLE-DOCUMENTAIRE.md](CONTROLE-DOCUMENTAIRE.md).

## 6. Limites et suite

L’exhaustivité porte sur les documents accessibles retrouvés, pas sur des contenus de conversation jamais enregistrés ou non accessibles. Le classement historique T1.x peut être complété si sa source autonome réapparaît, sans réouvrir les principes déjà corroborés.
Les schémas SQL/API/archives, paramètres cryptographiques, mécanismes d’authentification, seuils, catalogue initial, charte graphique et périmètre V1 restent volontairement distincts du cadrage clos. Voir [CONCEPTION-RESTANTE.md](CONCEPTION-RESTANTE.md).
Le remplacement est soumis à revue sur la branche `docs/cadrage-consolide-v1-1`. La procédure d’intégration se trouve dans [INTEGRATION-GITHUB.md](../COWORKAI/INTEGRATION-GITHUB.md).
