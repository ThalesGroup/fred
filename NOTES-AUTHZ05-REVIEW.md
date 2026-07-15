# AUTHZ-05 / AUTHZ-06 — Notes de suivi

Document de notes **unique** pour ce chantier (remplace `NOTES-TEAM-MULTIROLE.md` et
`HANDOFF-AUTHZ06-PROMPT.md`, fondus ici le 2026-07-12). Contrairement aux versions
précédentes, ce n'est **pas** un journal historique — l'historique complet (items 1-17
d'AUTHZ-05, implémentation d'AUTHZ-06) vit dans l'historique git et dans le RFC. Ce
fichier ne garde que ce qui reste réellement à faire ou à surveiller.

## Où lire le design (documentation officielle, à jour)

- **`docs/swift/platform/REBAC.md`** — le modèle produit d'autorisation, à jour au
  2026-07-12 : rôles plateforme, rôles d'équipe cumulables, gouvernance du registre,
  observabilité. C'est la référence à lire en premier, courte et volontairement sans
  historique daté.
- **`docs/swift/rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md`** — l'historique des
  décisions et leur justification (pourquoi, pas seulement quoi), Parts 1 à 7. À
  consulter pour comprendre le raisonnement derrière une règle, pas pour savoir ce qui
  est vrai aujourd'hui (c'est le rôle de REBAC.md).
- **`docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`** — pattern frontend, pyramide de
  tests. Toujours à jour, ne nécessite pas de fusion.
- **`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`** §14-15 — historique des
  changements de contrat gelé (`PermissionSummary`, `TeamMember.relations`).

## Règles à ne jamais relâcher sans confirmation explicite de Dimitri

- **Garde "zéro admin existant" de `can_rescue_team_admin`** (RFC §32) : ne s'active
  que si l'équipe a zéro `team_admin`. C'est exactement l'escalade essayée et revertée
  sur cette branche (RFC §24.7), sous un nom différent. Ne jamais l'assouplir.
- **Item 8b, toujours bloqué** : `groups_list_to_relations`'s boucle `for group in
  user.groups` (dérivation `team_member` depuis le claim Keycloak `groups`) ne peut pas
  être retirée avant que `fredlab-authz-migrate-swift.py` ait tourné contre les
  données réelles de production. Confirmation verbale déjà donnée par Dimitri
  (2026-07-09) que la migration est prévue avant déploiement — mais **reconfirmer
  explicitement au moment de l'exécution**, ne pas agir sur la seule confirmation
  passée.
- **Rôles d'équipe cumulables (AUTHZ-06)** : chaque octroi/retrait de rôle reste une
  action individuelle et vérifiée séparément — ne jamais introduire un endpoint de
  remplacement en bloc ("set roles to [...]"), et ne jamais plafonner le nombre de
  personnes par rôle sans demande explicite (hors scope RFC §38).
- **Aucun mécanisme de bascule/toggle** nulle part dans ce chantier — suppression
  pure à chaque changement de modèle, jamais de compromis intermédiaire gardant un
  ancien chemin vivant "au cas où".

## Points à consolider (ce qui reste réellement à faire)

- [ ] **Item 8b** — voir ci-dessus. Bloqué sur une action opérationnelle externe
      (migration de données réelles), pas une question de design.
- [ ] **Campagne de validation AUTHZ-06** (implémentation code-complete au
      2026-07-12, jamais encore validée en live) :
      1. `make clean` / `make test` / `make code-quality` dans chaque projet touché
         (`libs/fred-core`, `apps/control-plane-backend`, `apps/frontend`).
      2. Ajouter deux profils de test dans `fred-deployment-factory/config/configuration.yaml`
         (rôles cumulés dans `fredlab`) — assistant propose, Dimitri valide avant application.
      3. `fred-deployment-factory` : `make validation-report` contre le stack live.
      4. Passe manuelle UI persona par persona (les deux nouveaux profils en priorité),
         + auto-test d'autorisation (`/admin/self-test`, étape `team-write-access`).
      5. Consigner les résultats : `docs/swift/platform/authz-endpoint-matrix.yaml`
         (déjà à jour pour les nouvelles routes, à revalider en live) + un registre de
         campagne dédié (nom/emplacement à définir avec Dimitri à ce moment-là, ne pas
         improviser seul).
      6. Si tout est vert : première PR (sur #1957 existante ou une nouvelle — à
         confirmer avec Dimitri, ne pas décider seul), puis petits tickets ciblés pour
         les sujets restants trouvés pendant la validation.
- [ ] **`/monitoring/kpis` (page KPI legacy MUI)** — non liée dans la nav
      aujourd'hui, montre des métriques de conversation/token/latence qui n'ont de sens
      que pour un contexte d'équipe, pas pour admin/observer (clarifié avec Dimitri le
      2026-07-11). Reste accessible par URL directe. Nettoyage/suppression : chantier
      séparé, non planifié, à ouvrir seulement si Dimitri le demande.
- [ ] **Divergence connue non résolue** : `docs/swift/platform/authz-endpoint-matrix.yaml`
      garde ~201 routes en `pending_review` — la matrice garantit une couverture
      d'inventaire, pas une revue de chaque permission une par une. Pas bloquant pour
      la fusion de cette branche, mais à garder en tête pour une passe de revue
      ultérieure.
- [x] **`platform_admin_subjects`/`platform_observer_subjects`** — **superseded et
      supprimé (AUTHZ-07, RFC Part 8 §40-41).** Le champ de config et
      `OpenFgaRebacEngine._bootstrap_platform_roles` (le bootstrap au démarrage
      lisant ce champ) ont été retirés entièrement, sans remplacement ni alias — voir
      `libs/fred-core/fred_core/security/structure.py` et
      `libs/fred-core/fred_core/security/rebac/openfga_engine.py`. Le premier
      `platform_admin` est désormais obtenu par le root bootstrap
      (`POST /control-plane/v1/bootstrap/platform-admin`, self-promotion only) ; tous
      les autres rôles plateforme (et `platform_observer`) sont obtenus par l'import
      déclaratif (`PLATFORM-IMPORT-RFC.md` §10). Aucune tâche de peuplement de
      configuration ne reste : il n'existe plus de liste de sujets à peupler nulle
      part.
