# CON-04 — Protocole financier : devise, période, plafonds, réservations transactionnelles, réconciliation

**Exigences** : B6, B7, D2/D3/D7, T8.4, V1.4 (profils et plafonds), OSIA-I-02, OSIA-I-09, OSIA-I-15, REC-D3-02.
**Choix d'implémentation** : montants en **centimes d'euro (entier)**, période mensuelle calendaire **UTC** par défaut (fuseau configurable en settings), plafonds hiérarchiques global → profil → investigation → branche → fournisseur/modèle → opération.

## 1. Valeurs actées (V1.4)

| Profil | Rebonds max | Requêtes source max | Appels IA max | Durée max | Plafond par investigation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rapide (défaut) | 2 | 12 | 4 | 2 min | 0,05 € (5 c) |
| Standard | 4 | 40 | 12 | 10 min | 0,20 € (20 c) |
| Approfondi | 8 | 100 | 30 | 30 min | 1,00 € (100 c) |

- Budget autorisé au premier démarrage : **0 €** → aucun appel payant autorisé tant que l'utilisateur n'active pas les appels payants.
- À l'activation des payants : plafond **global 5 €/mois** (500 c) en plus du plafond par investigation. Profondeur réglable 1–10.
- Timeouts 15 s HTTP / 60 s IA ; cache 24 h minimum (V1.4).

## 2. Portées et plafonds (T8.4)

Contrôle simultané aux niveaux : **global mensuel**, **profil effectif**, **investigation**, **branche**, **fournisseur**, **modèle**, **opération**, ressources de l'hôte. Une limite inférieure ne lève jamais un plafond supérieur (D3.5). L'augmentation d'un plafond exige une validation explicite (D3.5) ; elle n'autorise pas implicitement une nouvelle branche.

Disponible(operation) = min(plafond applicable à chaque portée) − (réservé + consommé) sur ces portées. Si le coût ne peut pas être borné (estimation indisponible pour une opération payante) → **opération bloquée** (T8.4, OSIA-I-02).

## 3. Cycle obligatoire d'une opération payante (T8.4)

1. Estimer une borne de coût admissible (`cost_estimated_cents`).
2. Vérifier toutes les limites applicables (PolicyEngine).
3. **Réserver transactionnellement** : dans la même transaction que le passage de l'opération à `reserved` et (pour une tâche) le claim, insérer `reservations` (clé d'idempotence **unique** → retour de la réservation existante sans double compte) et l'écriture `ledger` `reserved`. Toute violation de plafond annule la transaction (refus).
4. Autoriser/refuser selon le résultat.
5. Récupérer la consommation réelle du fournisseur quand disponible.
6. Réconcilier : `consume(reservation, réel)` ou `release(reservation)` ; écritures `ledger` `consumed`/`released`/`reconciled` ; écarts de facturation externe visibles (T8.4, REC-D3-02).

Deux tâches ne peuvent jamais consommer la même enveloppe : réservation + claim dans la même transaction, clé d'idempotence unique, lignes verrouillées (row-level).

## 4. États financiers

`reservations.state` : `reserved → consumed | released`. `external_ops.state` : voir CON-03 §1. Période : `ledger.period` = `YYYY-MM` (UTC par défaut). Clôture mensuelle : le total consommé+récurrent du mois calendaire est comparé au plafond global ; au-delà → appels payants bloqués jusqu'à la période suivante ou augmentation explicite validée.

## 5. Repli et alternatives (T8.9, OSIA-I-15, V1.3)

Un repli (ex. local → cloud `mistral-small-2603`) exige : alternative **préalablement autorisée** en configuration (transmission + budget) **et** une enveloppe suffisante ; sinon la tâche passe en attente/échec explicite. Aucun fournisseur de secours payant sans autorisation budgétaire (T8.9).

## 6. Secrets (D2.4, T5.5, OSIA-I-12)

Clés API : jamais persistées en clair par défaut (mémoire de session) ; stockage persistant facultatif chiffré (coffre, tranche ultérieure) ; **absentes des journaux, diagnostics, archives `.osia`, exports de configuration et prompts** (filtrage + tests).

## 7. Vérifications prévues (tests exécutés, voir PR)

- Réservation idempotente (même clé → une seule enveloppe).
- Refus au-delà du plafond profil / global mensuel / branche ; aucune double réservation sous concurrence.
- Coût inconnu sur opération payante → bloqué avant tout appel.
- Annulation locale d'un appel `in_flight` → op `uncertain`, enveloppe non libérée aveuglément, pas de rejoue.
- Repli vers alternative non autorisée → refusé.
