# Journal de reprise fonctionnelle

Document de travail interne à la branche de reconstruction Rust. Point de reprise
pour Dimi et les assistants entre les sessions. Il conserve les observations et
les décisions sans les présenter comme une architecture validée.

## Mode de collaboration

- Dimi parcourt les fonctions une par une et exécute les commandes de déploiement.
- Sur demande, réaliser un petit lot ciblé sur le problème rencontré.
- Garder le frontend aussi proche que possible de son état existant. Les écrans
  dont le backend manque peuvent échouer : ne pas les masquer, les simuler ou
  les adapter spontanément. Ils servent de guide à la reprise fonctionnelle.
- Garder un suivi des progrès utiles ; ne pas conserver les lots abandonnés ni
  les récits d’annulation.
- Actualiser ce journal à chaque étape significative, même si aucune correction
  n'est nécessaire. Ne pas attendre une demande distincte pour garder la trace.
- Mettre à jour les chapitres d'architecture à la demande de Dimi. En attendant,
  noter les éléments à reporter et les chapitres concernés.
- Ne lancer ni tests, ni builds, ni déploiements sans demande explicite. Un lot
  implémenté n'est pas une fonction validée. Une validation antérieure à un
  changement ne valide pas automatiquement la nouvelle version.
- Ne pas créer de tâche planifiée : ce suivi accompagne les échanges actifs.

## Comment reprendre

Lire ce journal avant de continuer la reprise fonctionnelle. Conserver les IDs
ci-dessous ; ajouter une fiche pour chaque nouvelle fonction rencontrée, sans
prédéfinir tout le produit. Dimi choisit l'ordre des étapes.

Chaque fiche garde : objectif/parcours, observation datée et version si connue,
petit lot éventuel, validation explicite de Dimi, limites restantes, liens vers
le code et les chapitres d'architecture, puis prochaine étape. Ne jamais stocker
de jeton, clé, mot de passe ou donnée personnelle de test dans ce journal.

Statuts fonctionnels : à parcourir, problème observé, correction à valider,
validé par Dimi, différé. Suivre séparément la documentation : à reporter ou
à jour pour le périmètre indiqué. Conserver une chronologie courte sous chaque
fiche plutôt que d'effacer les résultats précédents.

## Index

| ID | Fonction ou étape | État au 2026-10-21 | Architecture |
| --- | --- | --- | --- |
| [F14](#f14-ouverture-de-lespace-personnel-à-coût-constant) | Espace personnel trouvé en SQL, coût constant | Tests ciblés validés ; validation finale du lot | 04, 09, A2, A3 |
| [F06](#f06-clés-jwks-pendant-une-panne-du-fournisseur) | Clés JWKS connues servies 1 h au plus pendant une panne | Tests ciblés validés ; validation finale du lot | 03 |
| [F05](#f05-sujet-des-grants-et-erreurs-openfga) | Grants vers un sujet connu ; erreurs OpenFGA classées | Tests ciblés validés ; validation finale du lot | 03, 03a, A2, 09 (I27) |
| [F18](#f18-audit-des-révocations-effectives) | Audit des seules révocations effectives, sans doublon | Tests ciblés validés ; validation finale du lot | 09 (I16), A3 |
| [F15](#f15-une-seule-liste-de-routes) | Une seule liste de routes HTTP | Tests automatisés validés | A1, carte des sources |
| [F20](#f20-migration-sql-unique) | Une seule migration 0001, sans en-tête contradictoire | Tests automatisés validés ; réinstallation k3d par Dimi | A2, A3, AGENTS, README du composant |
| [F17](#f17-noms-despaces-et-de-dossiers-canoniques) | Noms d'espaces et de dossiers en NFC sans espaces de bord | Tests automatisés validés | 02, 04, 05 |
| [F10](#f10-import-zip-et-jeton-de-lopérateur) | Import ZIP sans borne par le jeton de l'opérateur | Tests automatisés validés | 04, A1, 09 |
| [F07](#f07-validation-jwt-toujours-stricte) | Issuer et audience JWT toujours vérifiés | Tests automatisés validés | 03, I10 (09), A3 |
| [F04](#f04-suppression-de-la-création-opérateur) | Création par HTTP ou ZIP | Accepté par Dimi | 03, 03a, 04, 09, A1/A3, carte des sources |
| [F19](#f19-formatage-rust-et-qualité) | Formatage Rust et qualité | Contrôle qualité réussi | Aucun changement de comportement |
| [F03](#f03-listing-resources-unique-et-rafraîchissement) | Listing Resources unique et rafraîchissement | Tests automatisés validés | 09, A1, A2, carte des sources |
| [F02](#f02-attente-du-verrou-des-écritures) | Attente bornée sans connexion retenue | Tests automatisés validés | 03, 09, A1 |
| [F01](#f01-coût-du-contexte-organisation) | Placement SQL immuable et contexte commun | Tests automatisés validés | 03, 04, A1/A2/A3, 09 |
| [F-001](#f-001-environnement-de-développement) | Déploiement secondaire, renommage control-plane | Correction à valider après renommage | [Opérations](architecture/08-operations.md), à reporter |
| [F-002](#f-002-bootstrap-administrateur) | Bootstrap administrateur plateforme et CGU | Validé par Dimi | [Parcours](architecture/02-user-journeys.md), [sécurité](architecture/03-security.md) |
| [F-003](#f-003-organisation-et-équipe) | Création d'organisation et d'équipe | À parcourir | [Organisations](architecture/04-organizations.md) |
| [F-004](#f-004-ingestion-dun-pdf) | Ingestion d'un PDF par un utilisateur d'organisation | À parcourir | [Parcours document](architecture/02a-document-journey.md), [documents](architecture/05-documents.md) |
| [F-005](#f-005-import-du-bundle-de-démonstration) | Import du bundle de démonstration | Prochaine étape de Dimi | [Organisations](architecture/04-organizations.md) |

| [F-006](#f-006-durée-dune-relance-identique) | Durée des relances identiques | Optimisation implémentée, durée à valider | Opérations, à reporter si optimisé |

| [F-007](#f-007-démarrage-du-worker-dingestion) | Worker : secret historique exigé à tort | Correction à valider | Documents / opérations |


| [F-009](#f-009-sélection-des-utilisateurs-à-la-création) | Autocomplétion owner/admin | Implémenté ; parcours manuel à valider | Organisations |

| [F-010](#f-010-périmètre-de-revue-et-préparation-du-commit) | Parcours, SQL, cartes et limites de livraison | Relu indépendamment, validation exécution non faite | À jour pour le périmètre décrit |

## Méthode de consolidation

- 2026-10-21 : méthode durable enregistrée dans
  `.agents/skills/fred-reconstruction-method/SKILL.md`, reliée depuis AGENTS,
  arc42 et le skill d'audit. Le skill est également accessible à Codex localement
  sous `$fred-reconstruction-method` par un lien vers sa version du dépôt.
- Objectif : parcours maîtrisés dans le périmètre accepté, références commitées,
  revues indépendantes, corpus arc42 suffisant avec plan de fonctions et décisions
  clés distincts de l'état implémenté. Retirer les anciens RFC/OpenSpec du corpus
  actif après consolidation de leur information utile et de leurs consommateurs.
- Un prompt de revue réutilisable accompagne le skill. Validation structurelle du
  skill passée ; aucune nouvelle campagne d'audit, suppression documentaire ou
  validation fonctionnelle n'a été lancée par cette création.

## F14 Ouverture de l'espace personnel à coût constant

- 2026-10-22 : vérification sur HEAD `460317562` : confirmé. L'ouverture lisait tous les
  liens `organization` de l'organisation puis leurs lignes SQL. Correction : recherche
  `db::personal_space` (organisation, `personal_owner`, actif), puis lecture du seul lien
  de cet espace ; un espace actif sans lien est refusé (409) plutôt que doublé. Migration
  `0002_personal_space_owner.sql` : index unique partiel des espaces personnels actifs.
  Un espace personnel n'est retiré qu'avec son organisation. Test de budget : création
  3 lectures, réutilisation 6, identiques avec 2 ou 5 autres espaces personnels ; doublon
  SQL refusé ; course à deux inchangée. Mutation (ancienne recherche) détectée. `make test`
  et intégration complète (111) réussis. Arc42 04, 09, A2, A3, README du composant.

## F06 Clés JWKS pendant une panne du fournisseur

- 2026-10-22 : vérification sur HEAD `f4e2708e9` : confirmé. Après 300 s, `Jwks::cached` ne
  rendait plus aucune clé ; un refetch en échec puis le cooldown refusaient tout jeton, même
  signé par une clé connue. Correction (borne choisie par Dimi) : `JWKS_STALE_LIMIT` = 3600 s ;
  un kid connu reste servi si le rafraîchissement échoue ou attend son cooldown ; un jeu
  récupéré remplace toujours le cache ; un kid inconnu suit le cooldown. Test unitaire
  `known_keys_survive_an_unreachable_provider_within_the_stale_limit` (cache antidaté),
  en échec avec l'ancienne borne. `make test` réussi. Arc42 03 (Key cache).

## F05 Sujet des grants et erreurs OpenFGA

- 2026-10-22 : vérification sur HEAD `086f24a99` : confirmé. Seul l'owner était vérifié dans
  Keycloak ; un admin d'organisation pouvait accorder member à n'importe quelle chaîne.
  `write_guarded` traduisait tout 400/409 en 409. OpenFGA v1.15.1 mesuré : garde consommé
  = 400 `write_failed_due_to_invalid_input`, tuple invalide = 400 `validation_error` ;
  sujet vide, avec blanc, `:` ou `#` refusé. Correction : `domain::valid_subject`,
  `users::Directory::exists` (Keycloak par sujet, local par `user_identity`) après
  autorisation pour tout grant, 422 sinon (décision de Dimi) ; `InvalidTuple` → 422,
  garde consommé ou 409 → `Conflict`. OpenAPI du grant : 422 et 503 ajoutés ; client RTK
  inchangé (réponses d'erreur non générées). Tests : annuaire de fixtures ouvert dans
  `Env`, test `grants_require_a_known_valid_subject_and_classify_openfga_errors` (I27),
  vérifié en échec par mutation (204 puis Conflict au lieu d'InvalidTuple) ; owner inconnu
  404 → 422. `make test` et intégration complète (111) réussis. Arc42 03, 03a, A2, 09.

## F18 Audit des révocations effectives

- 2026-10-22 : lot des défauts validé par Dimi (commits locaux, tests par l'assistant).
  Vérification sur HEAD `94c55fa1e` : confirmé. `spaces::revoke` auditait une révocation
  même sans rôle détenu ; `grant`/`revoke` émettaient aussi un `tracing::info!` non-audit
  du même nom. Audit seulement si un tuple est supprimé, guard toujours consommé ; doublons
  supprimés. Test `only_effective_role_changes_are_audited_once` (I16) : échoue sur l'ancien
  code (deux événements), passe ensuite ; capture de test étendue à la cible. Arc42 09 (I16)
  et A3. `make test` réussi ; tests d'intégration d'audit ciblés réussis. Le grant d'un rôle
  déjà détenu reste audité (hors fiche).

## F15 Une seule liste de routes

- 2026-10-22 : vérification sur HEAD `c017210be`, verdict confirmé : `governance_routes` et
  `content_routes` avaient le même état et la même couche, toujours fusionnés par `router`
  et `openapi` ; seul `governance_router` (sans préfixe ni couches) servait aux tests.
  Refactor sur go de Dimi : une liste `registrations`, `pub fn routes(state)` remplace
  `governance_router` (appels de tests renommés), `router` et `openapi` en dérivent.
  `openapi.json` régénéré : diff vide, client frontend inchangé. A1 et carte des sources
  mis à jour. `cargo check --all-targets` exécuté ; tests et qualité non exécutés ;
  aucun commit.
- 2026-10-22 : Dimi confirme que tout est bon et autorise le commit et le push de F15.
- 2026-10-22 : correction de preuve. `openapi.json` est ignoré par Git : le « diff vide »
  cité plus haut (`git diff`) ne prouvait rien. Contrats régénérés depuis `c017210be` et
  `94c55fa1e` dans des worktrees jetables : identiques octet pour octet (142 329 octets).
  La conclusion de F15 tient ; le contrat versionné est le client `controlPlaneOpenApi.ts`.

## F20 Migration SQL unique

- 2026-10-22 : vérification sur HEAD `ea8c0fb97`, verdict partiel : en-tête de 0001
  contradictoire, déjà déclaré caduc par AGENTS et A3. Les migrations n'existent que sur
  cette branche (aucun tag, absentes de swift) ; la seule installation connue
  (k3d-fred-secondary, deux migrations et des espaces) ne pouvait déjà pas appliquer 0003.
  Dimi choisit B : aucune installation à préserver, solution neuve, réinstallation complète
  de k3d par ses soins. 0002 et 0003 fusionnées dans une 0001 sans l'en-tête ni le garde de
  table vide. Schémas `pg_dump --schema-only` de l'ancienne chaîne et de la fusion
  identiques (PostgreSQL 15 jetable). Toute base issue de l'ancienne chaîne est refusée par
  l'API et `migrate` et doit être recréée explicitement. AGENTS, README du composant, A2
  (tableau, ER régénéré) et A3 mis à jour. `cargo check --all-targets` exécuté ; tests et
  qualité non exécutés ; aucun commit.
- 2026-10-22 : intention de Dimi, non planifiée : à la première vraie release, documenter
  précisément la conception et les critères de PR de tout changement de base ; plus tard,
  prévoir une migration des données Swift vers le modèle organisation/équipe/projet/ReBAC.
  Piste discutée : commande ou import explicite et rejouable, dans le prolongement du bundle
  `source_platform: swift`, distinct de la chaîne SQLx (qui ne crée pas de tuples OpenFGA).
- 2026-10-22 : Dimi confirme que tout est bon et autorise le commit et le push de F20.

## F17 Noms d'espaces et de dossiers canoniques

- 2026-10-22 : vérification sur HEAD `64fb174c9`, verdict confirmé : noms d'espaces stockés
  tels quels (« ␠Acme » à côté de « Acme », NFC à côté de NFD), dossiers trimés sans NFC,
  récupération d'upload après 409 comparant le segment brut. Dimi choisit A. Règle unique
  `domain::canonical_name` (NFC, trim, longueur, contrôles) : espaces 180 avec slashes,
  dossiers 255 sans séparateurs ; API organisation/équipe/projet, ZIP et dossiers stockent
  et comparent cette forme. Aucune migration ni réécriture : un ancien nom non canonique
  reste distinct. Frontend : `ensureManagerFolderPath` normalise les segments. Tests :
  blueprint (forme canonique, NFC avant longueur, frères en collision), intégration
  `space_and_folder_names_are_unique_in_canonical_form` (I1), DocumentWorkspace
  (récupération NFD). Arc42 02, 04, 05 alignés. Documents hors périmètre (NFC sans trim).
  `cargo check --all-targets` et `cargo fmt` exécutés ; tests et qualité non exécutés ;
  aucun commit.
- 2026-10-22 : Dimi signale deux échecs d'intégration. `space_names_match_organization_and_child_http_creation_contracts`
  figeait l'ancien nom non trimé : attente alignée sur la forme canonique. Le nouveau test
  créait un dossier avec un simple member : création confiée à un editor d'organisation.
  Tests non relancés.
- 2026-10-22 : Dimi confirme que tout est vert et autorise le commit et le push de F17
  (et le push de F10).

## F10 Import ZIP et jeton de l'opérateur

- 2026-10-21 : vérification sur HEAD `e84826c50`, verdict confirmé. La réconciliation
  tenait la durée restante du bearer (30 à 300 s en local) comme borne, ce qui empêchait un
  gros import de jamais aboutir ; verrous plateforme/organisations tenus jusqu'au commit ;
  tuples des espaces annulés jamais collectés, sans effet de droits. Dimi choisit B.
  `Importer` reçoit l'uid de l'opérateur authentifié une fois à l'admission (HTTP ou CLI) ;
  chaque étape revérifie seulement `platform_owner` dans OpenFGA. Erreur `Unauthorized`
  interne supprimée. Test d'attente réécrit : retrait du rôle refusé, bearer expiré pendant
  l'attente accepté par HTTP (I5, I18). Arc42 04, A1 (séquence, effet 503 des verrous,
  orphelins) et 09 (I18, verrous) mis à jour, blocs régénérés. A, C et D non retenus.
  `cargo check --all-targets` et `cargo fmt` exécutés ; tests et qualité non exécutés ;
  aucun commit.
- 2026-10-21 : Dimi confirme que tests, intégration, qualité et contrôle arc42 sont bons
  et autorise le commit de F10.

## F07 Validation JWT toujours stricte

- 2026-10-21 : vérification sur HEAD `f73960529`, verdict confirmé (latent : toutes les
  configurations livrées déclarent `profile: c3`). Dimi choisit A. `FRED_STRICT_ISSUER` /
  `FRED_STRICT_AUDIENCE` supprimés : `Verifier::decode` exige toujours `iss` parmi les realms
  configurés et `aud` = `audience` ou `client_id`. `profile: c3` ne fait plus que refuser
  `security.user.enabled: false` ; ligne redondante du processing retirée. Test
  `issuer_and_audience_are_always_checked` (I10) sans profil, remplaçant l'assertion du mode
  souple. Arc42 03, I10 et A3 (réglages `FRED_JWT_*` hors secrets) mis à jour ; blocs générés
  et schéma de configuration régénérés, schéma inchangé. `FRED_JWT_*` restent dans
  l'environnement, à traiter avec F08. Aucun contrat HTTP ni SQL modifié. Tests et qualité
  non exécutés ; aucun commit.
- 2026-10-21 : Dimi signale l'échec de `api_starts_without_temporal_and_keeps_storage_optional`.
  Sa config sans profil déclarait `client_id: control-plane` avec des jetons `aud: app`,
  accepté seulement par l'ancien mode souple. Fixture alignée sur `client_id: app` ;
  aucun autre test ne s'authentifie avec une config écrite à la main. Tests non relancés.
- 2026-10-21 : Dimi rapporte `make test-integration` réussi (108 tests) ; Clippy réussi,
  rustfmt en échec sur le nouveau test d'auth.rs, formatage appliqué. `make code-quality`
  relancé par l'assistant : réussi (Clippy, rustfmt, modèle OpenFGA).
  Dimi confirme `make test` et `make test-integration` réussis ; `make -C docs/architecture
  check` réussi. Index F07 : tests automatisés validés.
- 2026-10-21 : Dimi autorise le commit et le push de F07.

## F04 Suppression de la création opérateur

- 2026-10-21 : après vérification sur `0829c5de4178ff85be47b8b16fc0bd9b017df53c`,
  Dimi autorise la suppression de `create-org`. Correction sur le HEAD courant
  `0fbc90239a21f06b1ec858ba18d1c1e367b670b7` : commande, cible Make et fonction
  `spaces::create_organization` retirées ; création HTTP consolidée sans chemin
  interne non authentifié. Les fixtures passent par HTTP avec un owner distinct
  de l'admin métier, puis un grant member explicite. Les tests du CLI vérifient
  son absence de l'aide et son refus sans création, même avec des credentials valides.
  Arc42 et la carte des sources décrivent HTTP/ZIP ; la ligne de coûts opérateur
  est retirée. La mention historique de F-009 décrit l'ancien état.
  D3 (exclusivité des owners sur tous les chemins) reste hors périmètre ; aucun
  droit déjà attribué n'est révoqué. Aucun contrat HTTP ni migration SQL modifié.
  Relecture indépendante en lecture seule : dépendance au cinquième rôle dans le
  test de pagination corrigée et relue (éligibilité personnelle explicite de
  l'admin métier), reliquat documentaire CLI retiré. Aucun autre défaut concret
  relevé dans ce périmètre. `make -C docs/architecture generate` exécuté avec succès.
  Tests, build et qualité non exécutés par cet assistant.
- 2026-10-21 : Dimi confirme « tout est bon » et autorise le commit et le push
  de F04. Aucun résultat de test supplémentaire n'est fourni dans cet accord.

## F19 Formatage Rust et qualité

- 2026-10-21 : Dimi demande de corriger tous les échecs de `make code-quality`.
  Après reproduction, `cargo fmt` corrige le formatage Rust préexistant (retours
  à la ligne et ordre des imports/modules), sans changement de comportement.
  `make code-quality` réussit ensuite intégralement : Clippy tous targets avec
  warnings interdits, rustfmt --check et contrôle DSL/JSON OpenFGA.
  Suites de tests non relancées pour ce formatage seul. Modifications préexistantes
  de Cargo.lock et du journal préservées. Dimi autorise ensuite le commit et le push
  de F19.

## F03 Listing Resources unique et rafraîchissement

- 2026-10-21 : Dimi confirme que tout passe et autorise commit/push. Tests Rust
  (45 unitaires, 10 contrats), intégration (108) et DocumentWorkspace (195) réussis.
  Clippy et contrôle arc42 réussis. Formatage des ajouts corrigé ; rustfmt global
  reste en échec sur le formatage préexistant, hors F02/F03 (F19).

- 2026-10-21 : sur demande explicite de Dimi après signalement de tests en échec,
  exécution locale réussie de `make test` (45 unitaires et 10 contrats OpenAPI),
  `make test-integration` (108 tests, dont F02/F03 et folder_scaling) et des
  28 fichiers de tests DocumentWorkspace (195 tests). Le fichier manager ciblé
  passe aussi séparément (15 tests). Aucun échec reproduit, aucun correctif
  supplémentaire nécessaire. Qualité et contrôle arc42 non exécutés pendant
  cette validation ; aucun commit ni push.

- 2026-10-21 : après vérification sur `ef8f27dc936a8c938300b52cc1acea0b98c8c8a0`,
  Dimi autorise F03. `/entries` devient le listing unique de Resources et de la
  récupération d'un dossier existant après conflit d'upload. Route `/folders` de
  listing, types associés et SQL dupliqué supprimés ; mutations conservées.
  Count/page partagent des prédicats racine/enfant explicites et une recherche
  littérale limitée à 255 caractères. Rafraîchissement au focus, invalidations
  existantes et polling uniquement pour les traitements actifs affichés.
  Fixture folder_scaling retargetée sur le chemin réel ; anciens EXPLAIN de
  requêtes dossiers isolées retirés. Tests de contrat, recherche, pagination,
  rafraîchissement et récupération d'upload ajoutés/adaptés.
  OpenAPI/client et blocs arc42 régénérés ; relecture indépendante, oublis de
  route dans un test et dans la matrice 03a corrigés puis relus. Aucun test ni
  outil qualité exécuté ; génération OpenAPI implique une compilation Rust.
  Aucun commit ni push.

## F02 Attente du verrou des écritures

- 2026-10-21 : Dimi confirme que tout passe et autorise commit/push. Tests Rust
  (45 unitaires, 10 contrats), intégration (108) et DocumentWorkspace (195) réussis.
  Clippy et contrôle arc42 réussis. Formatage des ajouts corrigé ; rustfmt global
  reste en échec sur le formatage préexistant, hors F02/F03 (F19).

- 2026-10-21 : Dimi choisit C après vérification sur HEAD
  `bc5a89cfeffb5d998d25994eaa175c4b994be4a1` et modifications locales.
  `authorized_write` tente le verrou transactionnel sans attente SQL, termine le
  rollback avant chaque pause de 50 ms et borne l'acquisition à cinq secondes.
  Guard, fence, contrôles après acquisition et verrou jusqu'au commit conservent
  I5/I22, y compris pour les publications documentaires et le processing.
  Tests ajoutés pour dix écritures concurrentes sur un pool d'une connexion,
  progression d'une autre organisation, délai borné et annulation ; tests
  d'entrelacement dossier/révocation/suppression/publication adaptés aux retries.
  Arc42 03, 09 et A1 décrivent le comportement et ses coûts au présent.
  Génération arc42 réussie ; relecture indépendante du correctif et des tests sans
  défaut identifié. Le HEAD a avancé extérieurement à `ef8f27dc936a8c938300b52cc1acea0b98c8c8a0`
  pendant ce travail ; les changements F02 restent non committés.
  Aucun test, build ou contrôle qualité exécuté ; validation à faire par Dimi.
  Aucun commit ni push.

## F01 Coût du contexte organisation

- 2026-10-21 : sur accord de Dimi pour corriger et exécuter les tests,
  `make test` réussit (45 unitaires, 10 contrats OpenAPI), ainsi que
  `make test-integration` (106 tests). Deux attentes obsolètes corrigées :
  un rôle projet isolé résout le même contexte dans organization et memberships
  sans réparer les rôles parents ; le worker Temporal se connecte en arrière-plan
  pendant que HTTP reste disponible même sans handshake Temporal. Arc42 précise
  la première règle. Suites navigateur et Temporal dédiées, contrôles qualité et
  contrôle arc42 non exécutés ; aucun commit ni push.

- 2026-10-21 : sur HEAD `bc5a89cfeffb5d998d25994eaa175c4b994be4a1`,
  Dimi approuve l'option A, cible installation neuve. Migration additive 0003,
  `space.organization_id`/`parent_id` immuables, écrits par toutes les créations
  avant publication FGA et commit SQL. La migration refuse les espaces existants ;
  aucun effacement, remplissage FGA ou changement de l'installation courante.
  Contexte commun aux contrôles et à memberships : pages de rôles FGA + une requête
  SQL, espaces retirés inclus. Placement de la cible sans Read FGA. Tests ciblés
  ajoutés/adaptés pour équivalence hiérarchique, immutabilité, ambiguïté après
  retrait et budgets (41 rôles paginés par 10 : 5 Reads, au lieu de 45).
  Arc42 décrit le comportement et les budgets attendus au présent. Les anciennes
  mesures folder_scaling du 2026-10-18 (41 rôles, concurrence 50 : 81 req/s,
  p95 611 ms) restent la référence pré-correction du commit ci-dessus, pas une
  mesure du nouveau code. Relecture indépendante Rust/SQL/tests sans défaut
  bloquant identifié ; corrections documentaires relues. Générations arc42 et
  OpenAPI/client réussies (compilation Rust pour OpenAPI ; client identique,
  aucune forme HTTP changée). Arc42 applique la chaîne SQL uniquement dans son
  PostgreSQL jetable. Aucun test, contrôle qualité, build image, migration de
  l'installation, commit ou push exécuté. Validation et commit restent à la main
  de Dimi.

## F-010 Périmètre de revue et préparation du commit

Revue du 2026-10-21 : branche `chore/rust-rebac`, HEAD
`8d3b66e7dd721beab2a46a29afc336188a458984`, avec index et arbre de travail locaux.
Comparaison d'orientation : merge-base avec la référence locale `swift`
`c32c3069db80c4590af730b93ff4b9c2eb04c2d5`, sans cible de PR supposée.

Trois assistants indépendants ont lu respectivement le parcours UI/Rust jusqu'au
premier dossier, les migrations/catalogue SQL et les dépendances de livraison.
Les blocs documentaires générés ont été régénérés ; les liens de fichiers du
dossier et des README control-plane ont été vérifiés et se résolvent.
Aucun test, build, navigateur, déploiement ni accès à la base vivante n'a été exécuté.
Cette revue ne certifie ni l'ingestion PDF ni la totalité de la branche.

### Résultats et dispositions

- Parcours arc42 recentré sur connexion, CGU, bootstrap, organisation, provisioning,
  entrée métier et création de dossier. L'autocomplétion, le même owner/admin,
  l'annuaire local observé, les prérequis de droits et les limites de dossiers sont
  explicités. La carte arc42 pointe vers une carte des propriétaires de code dans
  `apps/control-plane/src/README.md`, référencée par AGENTS.
- Catalogue SQL : onze tables applicatives et historique SQLx identifiés. Les
  contraintes SQL sont distinguées des garanties applicatives. Les identifiants
  OIDC normalisés et la nullabilité des relations du diagramme sont explicités.
- Les nouvelles valeurs OpenFGA/Temporal ne conservent pas automatiquement les
  ressources de l'ancienne installation. Le redémarrage sur une installation
  fraîche est accepté par Dimi ; aucune donnée n'a été effacée. Documentation
  opérateur et journal corrigés pour ne pas promettre une migration automatique.
- Point de contrat restant : le guard frontend interdit l'accès métier à un
  propriétaire plateforme, même avec des rôles métier. L'entrée distincte demandée
  par AGENTS n'existe pas. Le parcours décrit le comportement actuel avec un compte
  métier séparé ; l'implémentation de cette entrée n'est pas ajoutée par cet audit.
- Frontière actuelle : création équipes/projets disponible par API et import,
  sans formulaire raccordé. Le ZIP requiert Keycloak compatible ; ne pas confondre
  avec l'annuaire local OIDC de l'autocomplétion. La recherche Keycloak ne fait pas
  le filtrage service/délégation propre aux snapshots locaux.

### Point de départ commité

Dimi demande explicitement de conserver tout l'état courant dans un seul commit
local de référence, intégration Swift et reconstruction comprises. La séparation
de l'historique n'est pas un objectif. Le commit constitue la base des revues et
corrections suivantes, pas une déclaration de validation fonctionnelle.

Le snapshot inclut le control-plane Rust, ses migrations, les clients frontend et
leurs consommateurs, le profil local, les adaptations Knowledge Flow, le retrait
du reset Rust, les tests présents, les schémas et la documentation. Les fichiers
locaux ignorés, notamment les secrets `.env`, restent hors Git.

Les observations de revue ci-dessus restent applicables. Aucun test, build,
déploiement ou effacement de données n'accompagne ce commit. Aucun push demandé.
Prochaine étape : relire ce point de départ commité, corriger les écarts dans des
commits suivants et valider les parcours jusqu'à satisfaction de Dimi.

## F-001 Environnement de développement

- 2026-10-21 : préparation OpenSearch alimentée par les noms d'index de la
  configuration effective du worker ; motifs génériques refusés avant écriture.
  Index documentaire du profil : `document-vectors`. Support de reset Rust retiré,
  sans suppression de données. Topologie arc42 alignée sur les trois déploiements.
  Implémentation à valider par Dimi ; aucun test ni déploiement exécuté pour ce lot.

- Objectif : travailler dans `~/Rebac/fred` sur `chore/rust-rebac`, avec le
  cluster `fred-secondary`, sans perturber l'environnement Swift.
- Composition souhaitée : control-plane Rust, Knowledge Flow worker et frontend.
  Pas de Knowledge Flow API ni de satellites dans ce parcours.
- 2026-10-21 : Dimi a confirmé le succès du déploiement avant le renommage.
  Cela ne constitue pas une validation des parcours fonctionnels ni du nouveau build.
- Lot suivant réalisé : ancien backend Python retiré, Rust regroupé dans
  `apps/control-plane`, binaire `control-plane`. Image : `control-plane-backend`.
  Les valeurs actuelles renomment les identifiants OpenFGA/Temporal ; elles ne
  migrent pas les ressources persistantes. Dimi accepte une installation fraîche.
- Frontend : ancien client déplacé vers `legacyControlPlane`, client Rust renommé
  `controlPlane`, imports/Redux adaptés et préfixe Rust `/control-plane/v1`.
  Aucun portage des fonctions historiques vers les nouveaux endpoints dans ce lot.
- Aucun test, build ou déploiement exécuté par l'assistant pour ce renommage.
- Sauvegarde locale du Python et des diffs avant retrait :
  `/home/dimi/Rebac/backups/control-plane-python-20261021-101355`.
- Commande transmise à Dimi, depuis `~/Rebac/fred-deployment-factory` :
  `make k3d-app ENV=secondary APP=fred DIR=../fred`.
- Prochaine étape : attendre le résultat du build/déploiement exécuté par Dimi.
- Architecture à reporter sur demande : nom du composant, API active, coexistence
  des clients frontend historiques et Rust, composition du déploiement secondaire.

### F-001 : doublon du volume temporaire après renommage

- 2026-10-21 : upgrade refusé par Kubernetes : volume `manager-document-spool`
  et montage `/tmp/control-plane-uploads` déclarés deux fois.
- Cause : le nom `control-plane-backend` active la déclaration automatique du
  chart ; l'overlay k3d conservait la déclaration explicite de l'ancien nom.
- Petit lot : retirer uniquement le volume et le montage redondants de
  `deploy/k3d/values.yaml.gotmpl`. Le chart fournit le volume ; sa limite reste
  400 MiB via `storage.content.limits.temp_bytes: 419430400`.
- État : correction à valider au prochain déploiement de Dimi. Aucun test,
  build ou déploiement lancé par l'assistant.
- Observation distincte : le worker Knowledge Flow redémarre en erreur dans
  la sortie transmise. Cause non diagnostiquée ; ne pas attribuer cette erreur
  au doublon de volume sans logs.
- Le bootstrap/CGU reste validé pour le parcours précédemment effectué (F-002),
  pas pour la nouvelle version dont l'upgrade vient d'échouer.

- Retour suivant de Dimi : upgrade réussi, release `fred-app` révision 4,
  Helm `deployed`, durée totale 2 min 18 s dont 7 s pour Helm. Le doublon ne
  bloque plus ce déploiement. Pas de logs worker disponibles pour conclure sur
  la cause de ses redémarrages précédents.

## F-002 Bootstrap administrateur

- Parcours : bootstrap administrateur plateforme et CGU depuis le frontend.
- 2026-10-21 : **validé par Dimi**, qui demande explicitement de marquer ce
  parcours comme validé avant de reprendre à l'import du bundle de démonstration.
- Cette validation concerne le parcours effectué ; elle ne prouve pas les cas
  d'erreur, la répétition du bootstrap ou tous les contrôles d'autorisation.
- Version exacte non communiquée. Aucun test supplémentaire lancé par l'assistant.
- Architecture : résultat à reporter sur demande dans les parcours et la sécurité.

## F-003 Organisation et équipe

- Parcours souhaité : créer une organisation puis une équipe avec l'administrateur.
- État : à parcourir ; résultats et limites à consigner au fil des étapes de Dimi.
- Les rôles, rattachements et droits observés alimenteront les chapitres
  organisations et sécurité lorsque Dimi demandera leur mise à jour.

## F-004 Ingestion d'un PDF

- Parcours souhaité : se connecter comme utilisateur d'organisation et ingérer
  un PDF, avec le control-plane et le Knowledge Flow worker.
- État : à parcourir ; ne pas considérer l'ingestion comme validée parce que
  les conteneurs ont démarré.
- Consigner les étapes réellement parcourues : accès au bon espace/dossier,
  dépôt, progression, résultat et accès au document. Dimi fixe l'ordre et le lot.

## F-005 Import du bundle de démonstration

- 2026-10-21 : prochaine étape choisie par Dimi après validation du bootstrap/CGU.
- État : à parcourir. Attendre ses observations avant de proposer un petit lot.
- Consigner le résultat de l'import, les objets effectivement créés et les
  éventuels problèmes. Ne pas déduire de l'import une validation de la création
  manuelle d'organisation/équipe (F-003).

## F-006 Durée d’une relance identique

- 2026-10-21 : Dimi observe 2 min 18 s pour une relance annoncée identique.
- Lecture des scripts : trois builds systématiques, double lint/rendu,
  import des références absentes des noeuds, identités, prepare, puis Helm sync.
- La sortie montre trois images importées dans les deux noeuds ; « host cache »
  signifie disponibles dans Docker sur le laptop, pas déjà présentes dans k3d.
- Les logs BuildKit montrent des attestations et un index de manifests ; le tag
  k3d est dérivé de `docker inspect .Id`. Un changement de cet index malgré des
  couches identiques est une piste, pas une cause démontrée par comparaison.
- Pas de chronométrage par étape : impossible d’attribuer précisément les
  2 min 11 s hors upgrade Helm. Aucune optimisation implémentée dans cette étape.

### F-006 : relance courte commune Swift/secondary

- Dimi demande une relance identique en quelques secondes, également pour Swift.
- Lot implémenté dans `fred-deployment-factory/bin/k3d-app.sh` avec le helper
  `bin/k3d-app-cache.py` : après succès, conserver une empreinte des sources,
  de la configuration, des fichiers générés et des métadonnées Kubernetes.
- Si les entrées et ressources suivies sont identiques et prêtes, sauter build,
  copie des images, identités, prepare et sync. Le même moteur sert Swift et secondary.
- Le premier lancement reste complet pour enregistrer le succès. `FORCE=1`
  rejoue tout, notamment après modification manuelle dans Keycloak/OpenSearch
  ou changement de fichiers ignorés non suivis par l'empreinte.
- Un échec invalide le succès mémorisé. Les appels deploy du même checkout et de
  la même application sont verrouillés pour protéger les fichiers générés.
- Modifications préparées dans `~/Rebac/fred-deployment-factory` ; l'autre copie
  de la factory devra recevoir ces modifications pour bénéficier du même mécanisme.
- Aucun test, build ou déploiement exécuté ; durée réelle à mesurer par Dimi
  sur une seconde invocation identique. Aucun gain chiffré encore démontré.

### F-006 : identité stable des images par contenu exécutable

- Dimi précise que les images inchangées ne doivent pas être reprises lors des
  itérations Rust et propose de comparer simplement les images.
- Petit lot appliqué dans `deploy/k3d/build` des copies Rebac et Prism (Swift) :
  tag calculé à partir des couches RootFS, de Config et de la plateforme, sans
  dépendre de l'index BuildKit qui peut contenir de nouvelles attestations.
- Le mécanisme existant de prefetch ignore les références déjà présentes sur
  les noeuds. Une image frontend/worker au contenu identique conserve donc son
  tag ; un changement Rust seul ne demande que la copie de l'image control-plane.
- Précision : les commandes Docker build restent invoquées lors d'un déploiement
  complet. Docker réutilise les couches inchangées. Aucun cache supplémentaire
  de dépendances source par image n'a été introduit.
- La première exécution adopte les nouveaux tags et peut recopier toutes les
  images. Aucun build ni test exécuté ; comportement et gain à confirmer par Dimi.

## F-007 Démarrage du worker d'ingestion

- 2026-10-21 : Helm révision 7 affiche `deployed` après 1 min 42 s, mais la
  lecture Kubernetes suivante montre le worker `0/1 Error`, six redémarrages.
  Le succès Helm ne constitue donc pas une preuve de fonctionnement durable.
- Logs collectés via `ENV=secondary bin/k3d-observe` : démarrage interrompu par
  `ValueError: Missing required environment variable: KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET`
  dans `ApplicationContext._log_config_summary`.
- Cause : contrôle de l'identité de l'ancienne API KF aussi appliqué au worker
  manager-processing, qui utilise `MANAGER_WORKER_CLIENT_SECRET` et son client dédié.
- Petit lot : ne pas exiger le secret API historique dans ce mode. Le contrôle
  existant est conservé pour le mode historique ; aucune configuration de
  sécurité ni validation du client dédié n'est désactivée.
- Correction dans `apps/knowledge-flow-backend/knowledge_flow_backend/application_context.py`.
  Aucun test/build/déploiement lancé. À valider par Dimi au prochain déploiement.

## Dernière décision de travail

2026-10-21 : avancer pendant plusieurs jours par petits lots, guidés par les
parcours manuels de Dimi. Le journal conserve la couverture et les décisions ;
le dossier arc42 reçoit les explications stabilisées sur demande. La prochaine
fonction n'est jamais réputée couverte par analogie avec la précédente.

2026-10-21 : bootstrap et CGU validés explicitement par Dimi (F-002).
Reprise à l’import du bundle de démonstration (F-005).

Prochaine étape immédiate : relancer le déploiement après correction F-001,
puis reprendre F-005. Le worker en erreur reste à diagnostiquer si le problème persiste.

### F-006 : mini PR Swift

- À la demande de Dimi, correction des tags commitée et poussée depuis Prism :
  `42752dbb0`, branche `codex/k3d-stable-image-tags`, cible `swift`.
- PR draft : https://github.com/ThalesGroup/fred/pull/3207 ; suivi #3206.
- Périmètre : build hook, tests ciblés, note opérateur. Aucun cache factory inclus.
- Trois tests unitaires ciblés réussis, diff sans erreurs d'espacement. Aucun
  build Docker ni déploiement. Modifications satellites locales laissées hors commit.

### F-006/F-007 : deux déploiements mesurés par l'assistant

- 2026-10-21, sur demande explicite de Dimi : deux exécutions successives de
  `make k3d-app ENV=secondary APP=fred DIR=../fred`, sans modification entre elles.
- Premier passage : 26,05 s. Second : 36,30 s, dont 20 s pour Helm. Les deux
  réussissent ; aucune copie d'image. Ce n'est pas encore une relance en quelques secondes.
- Worker après le second : même pod `knowledge-flow-worker-6bc9f697b5-zvghh`,
  `1/1 Running`, zéro redémarrage, âge 2 min 3 s. Le défaut F-007 n'est plus
  observé sur ces passages ; cela ne valide pas encore une ingestion PDF.
- Cache global de la factory retiré du moteur par Dimi ; fichier helper encore
  présent non suivi, mais non utilisé. Les étapes prepare/Helm restent exécutées.
- PR #3207 : sections Prerequisites et Configuration ajoutées à la note, commit
  `e17652171`. Validateur CI `migration_guides.py check-pr --base origin/swift`
  réussi sur les commits de la PR. Le contrôle initial --worktree incluait à tort
  les fichiers satellites non suivis, laissés hors PR.

Prochaine étape choisie par Dimi : création d’une nouvelle équipe (F-003),
parcours manuel dans l’UI Rebac. Résultat encore à observer.

## F-009 Sélection des utilisateurs à la création

- 2026-10-21 : après l'échec signalé par Dimi, inventaire du test OpenAPI
  complété avec `GET /admin/organizations/candidates`, déjà implémenté et documenté
  au commit de référence. Sur son accord pour corriger les tests, `make test`
  réussit : 45 tests unitaires et 10 tests de contrat. Aucun contrat HTTP modifié
  par cette correction, aucun commit.

- Vérification demandée par Dimi : Swift dispose déjà d'une autocomplétion
  des administrateurs initiaux dans TeamFormDialog, en création et édition.
  Recherche dès deux caractères ; affichage prénom, nom et username ; sélection
  multiple sans doublons via GET /control-plane/v1/teams/candidate-admins,
  autorisée par le même droit que la création d'équipe.
- Le formulaire Rebac de création d'organisation utilise actuellement deux
  champs texte (owner/admin) et vérifie les usernames exacts à la soumission.
  L'autocomplétion reste à porter pour ce parcours ; aucune implémentation
  effectuée dans cette étape de comparaison. Composant Autocomplete existant réutilisable.

### F-009 : portage de la sélection owner/admin

- Reprise de TeamFormDialog : Autocomplete et Chip existants, deux caractères
  minimum, currentData pour éviter les résultats d'une ancienne recherche,
  sélection indépendante pour les deux rôles. La même personne peut être choisie
  deux fois. Aucun autre écran modifié.
- GET /admin/organizations/candidates : authentification et CGU, puis le même
  contrôle platform_owner que la création, avant toute recherche. Un Check
  OpenFGA ; aucune liste de tuples ni verrou SQL pendant la recherche.
- Reprise de users.service.search_users : recherche Keycloak ou annuaire local,
  au plus 20 résultats. L'annuaire local est configuré par security.user_directory:
  local, requis avec provider: oidc comme en Python. Il contient les profils
  observés après authentification, sans droits. Snapshot limité à un par dix
  minutes, cache borné à 2048 entrées ; comptes service_agent, comptes de service
  et callers de délégation exclus (claim configurable existant côté Python).
- Création : résolution exacte des comptes dans l'annuaire choisi, refus de
  l'ambiguïté, mêmes validations de rôles et de contexte, puis contrôle owner
  répété sous verrou existant. Les identifiants OIDC ne sont pas recalculés.
- Déploiement : user_identity et son index sont ajoutés par la migration additive
  0002_user_identity.sql. La migration 0001 reste identique à celle déjà appliquée.
  Aucune réinitialisation nécessaire pour cette évolution.
- Contrats OpenAPI/client RTK et schéma de configuration régénérés. Génération
  impliquant une compilation Rust ; aucun test, build d'image ou déploiement.
  Fixtures existantes adaptées aux sélections. Le parcours Keycloak/OIDC et
  l'équivalence fonctionnelle restent à valider avec Dimi avant la passe arc42.

### F-009 : migrations SQL incrémentales

- À la demande de Dimi, remplacement de la règle SQL "baseline réécrite/reset"
  par des migrations SQLx numérotées et immuables, sans nouvel outil.
- Inspection en lecture seule de fred sur k3d-fred-secondary : seule version 1
  appliquée avec succès ; user_identity absente. SHA-384 de 0001 restauré égal
  au checksum enregistré (46871cda...fb1c3aa5). Aucun checksum SQL modifié.
- Ajout de 0002_user_identity.sql ; consignes AGENTS et README du composant
  ajustées. Aucun changement de politique OpenFGA.
- Migration non appliquée par l'assistant ; pas de test, build ou déploiement.
  Le prochain déploiement reconstruira l'image Rust et son Job appliquera 0002.

### F-009 : catalogue SQL intégré au dossier arc42

- Catalogue ajouté dans A2-manager-contracts : onze tables applicatives, historique
  SQLx, responsabilités, cycle de vie, clés étrangères, contraintes et index.
  Distinction explicite entre profils SQL, rôles OpenFGA et fichiers objet.
- A3-manager-operations décrit la chaîne SQLx, son exécution actuelle (Job et
  démarrage API), les requêtes d'inspection et la différence entre checksum et
  dérive du schéma. README du dossier et du composant reliés au catalogue.
- Générateur ER corrigé pour apps/control-plane ; diagramme régénéré par tbls
  depuis 0001 et 0002 dans un PostgreSQL temporaire, puis intégré au bloc SQL A2.
  Ancien fichier généré control-plane.er.mmd remplacé par control-plane.er.mmd.
- Génération documentaire réussie ; aucun test applicatif, aucune migration
  de la base utilisateur, aucun déploiement. L'audit de dérive SQL complet et
  les validations CI de mise à niveau ne sont pas présentés comme effectués.

### F-009 : vérification SQL au démarrage API

- À la demande de Dimi, pool() n'applique plus les migrations : il réutilise
  db::require_initialized en lecture seule. API et create-org refusent une base
  vide ou un historique incompatible ; le message indique Job/commande migrate
  et inspection des checksums. La commande migrate conserve seule le moteur SQLx
  d'application dans le binaire principal. Le Job de déploiement reste inchangé.
- README et A3 ajustés, y compris le démarrage hors Kubernetes. La vérification
  reste stricte : une ancienne image ne redémarre pas sur un historique plus récent.
  Ce lot ne modifie pas les privilèges PostgreSQL.
- Aucun test, build, migration ou déploiement lancé ; validation au prochain
  déploiement manuel de Dimi.
