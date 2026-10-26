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
| [SEC-1](#sec-1-invariants-de-sécurité-weaver) | Sécurité Swift et simplification ReBAC Weaver | Direction explicite consignée ; contrats détaillés à cadrer | Consignes, sans validation fonctionnelle nouvelle |
| [REL-1](#rel-1-génération-weaver-500) | Alignement des versions Weaver | Préparé localement, non publié | Sans changement architectural |
| [F-013](#f-013-synthese-organisationnelle-en-lecture) | Synthèse organisationnelle et détail équipe | Backend et UI implémentés ; validation des parcours attendue | A2/A7/A8, chapitres 04/09 |
| [F23](#f23-stockage-des-instances-dagents) | Stockage Rust des instances d'agents | Tests ciblés passants ; jalon global bloqué | Hors périmètre arc42 validé |
| [F25](#f25-création-et-relecture-dune-instance-custom) | Instances et administration des agents | Création UI confirmée ; M1-M5c implémentés et contrôlés techniquement, parcours chat non validé | 00 et 02.3 : principes/parcours spécifiés, pas de validation runtime |
| [F24](#f24-catalogue-des-templates-par-espace) | Catalogue des templates par espace | Tests ciblés passants ; parcours UI non validé | Hors périmètre arc42 validé |
| [F22](#f22-agent-rust-embarqué-hello-world) | Agent Rust embarqué, hello-world SSE | Implémenté, à valider | Hors périmètre arc42 validé |
| [DOC-3](#doc-3-vue-densemble-de-weaver) | Vue d'ensemble de Weaver | Texte et schémas rédigés | 01 |
| [DOC-2](#doc-2-contrat-de-lespace-personnel-à-sa-place) | Contrat de l'espace personnel déplacé hors du catalogue SQL | À jour | A2 |
| [DOC-1](#doc-1-carte-des-sources-exacte) | Carte des sources exacte pour Resources et l'autorisation | À jour | Carte des sources, README d'arc42 |
| [F16](#f16-noms-et-usage-cli-exacts) | Noms, commentaires et usage CLI exacts | Tests ciblés validés ; validation finale | README du composant, 09 (bloc généré) |
| [F09](#f09-lectures-openfga-bornées) | Lectures OpenFGA concurrentes bornées | Tests ciblés validés ; validation finale | 09 |
| [F11](#f11-une-seule-réponse-dautorisation) | Une seule réponse d'autorisation métier | Tests ciblés validés ; validation finale du lot | 03, 03a, A2 |
| [F12](#f12-un-seul-format-derreur) | Un seul module d'extracteurs, erreurs toujours en JSON | Tests ciblés validés ; validation finale du lot | A2, carte des sources |
| [F13](#f13-recherche-locale-par-préfixe-littéral) | Recherche de candidats locale par préfixe littéral indexé | Tests ciblés validés ; validation finale du lot | 02, 04, 09, A2, A3 |
| [F08](#f08-configuration-stricte) | Clés de configuration inconnues refusées | Tests ciblés validés ; validation finale du lot | A3, schémas |
| [F21](#f21-profil-k3d-propriétaire-de-la-configuration-du-control-plane) | Profil k3d propriétaire de la configuration du control-plane | Tests ciblés validés ; validation finale du lot | 08, README k3d |
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
| [F-002](#f-002-bootstrap-administrateur) | Bootstrap administrateur plateforme et CGU | Validé par Dimi | [Parcours](architecture/02.1-user-journeys.md), [sécurité](architecture/03-security.md) |
| [F-003](#f-003-organisation-et-équipe) | Création d'organisation et d'équipe | À parcourir | [Organisations](architecture/04-organizations.md) |
| [F-004](#f-004-ingestion-dun-pdf) | Ingestion d'un PDF par un utilisateur d'organisation | À parcourir | [Parcours document](architecture/02.2-document-journey.md), [documents](architecture/05-documents.md) |
| [F-005](#f-005-import-du-bundle-de-démonstration) | Import du bundle de démonstration | Prochaine étape de Dimi | [Organisations](architecture/04-organizations.md) |

| [F-006](#f-006-durée-dune-relance-identique) | Durée des relances identiques | Optimisation implémentée, durée à valider | Opérations, à reporter si optimisé |

| [F-007](#f-007-démarrage-du-worker-dingestion) | Worker : secret historique exigé à tort | Correction à valider | Documents / opérations |


| [F-009](#f-009-sélection-des-utilisateurs-à-la-création) | Autocomplétion owner/admin | Implémenté ; parcours manuel à valider | Organisations |

| [F-010](#f-010-périmètre-de-revue-et-préparation-du-commit) | Parcours, SQL, cartes et limites de livraison | Relu indépendamment, validation exécution non faite | À jour pour le périmètre décrit |

| [F-011](#f-011-découverte-des-définitions-dagents) | Découverte des définitions d'agents | Découverte CLI implémentée ; exécution à valider | 06 à jour |

| [F-012](#f-012-suppression-unifiée) | Suppression unifiée : retrait immédiat, purge différée | Conception validée par Dimi ; rien d'implémenté | 03, 04, 05, 08, A2, A3, A9 au fil des lots |

| [F26](#f26-fusion-swift-et-préférences-utilisateur) | Fusion Swift : préférences personnelles en Rust | Implémenté ; validation fonctionnelle à faire | 02.1, A1, carte des sources |
| [F27](#f27-primitive-de-visibilité-des-chunks) | Primitive Python de périmètre et de vérification des chunks | Implémentée, non branchée ; SQL non exécuté | Hors périmètre arc42 validé |
| [F28](#f28-requêtes-opensearch-de-la-capacité-document-access) | Requêtes OpenSearch pures de Document Access | Implémentées, non branchées ; rien d'exécuté contre OpenSearch | Hors périmètre arc42 validé |
| [F29](#f29-liste-sql-des-documents-visibles-dun-périmètre) | Liste SQL des documents visibles d'un périmètre | Implémentée, non branchée ; SQL non exécuté | Hors périmètre arc42 validé |

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

## DOC-1 Carte des sources exacte

- 2026-10-22 : vérification de chaque chemin et symbole de `apps/control-plane/src/README.md` :
  tous résolus (frontend et Rust). F03 avait déjà corrigé l'attribution du listage à
  `documents/`. Reste corrigé : chemin complet de `CreateFolderModal`, propriétaires exacts
  (`entries`/`summary`, `create_folder`, `rename_folder`/`delete_folder`), test frontend du
  workspace, et nouvelle ligne de l'autorisation métier (`spaces::authorize`, F11) reprise
  dans le tableau « Find a function ». `make -C docs/architecture check` réussi.

## DOC-2 Contrat de l'espace personnel à sa place

- 2026-10-22 : les deux paragraphes en fin de catalogue SQL d'A2 vérifiés contre `spaces.rs`,
  `api.rs` et `domain.rs`. Le premier (« Manager enforces… ») répétait le paragraphe
  précédent et était inexact depuis F14 (unicité de l'espace personnel garantie par l'index
  `space_personal_owner`, déjà dans le tableau) : supprimé. Le second, contrat HTTP écrit en
  deltas, réécrit au présent dans la section HTTP d'A2 avec les statuts réels (200, 201, 403,
  404, 409) ; les rôles, déjà décrits dans 03, retirés. `make -C docs/architecture check` réussi.

## F16 Noms et usage CLI exacts

- 2026-10-22 : six points vérifiés et corrigés : `require_directory_actor` renommé
  `require_real_authentication` (il ne vérifie que l'authentification active) ; doc de
  `Fga::check` (« one space permission Check ») ; commentaire de `CreateFolderModal` aligné sur
  `maxDepth` (15) de la variante control-plane ; doc du module `lib.rs` ; `processing-schema`
  ajouté à `USAGE` et section Commands du README du composant ; le worker lifecycle journalise
  son étape d'arrêt (`temporal_connect`, `schedule_reconcile`, `worker_setup`, `worker_run`)
  sans jamais le message de la dépendance. Test `a_stopped_lifecycle_worker_reports_only_its_stage`
  (I11). `make test` réussi. Aucun comportement documenté d'arc42 ne change.

## F09 Lectures OpenFGA bornées

- 2026-10-22 : vérification sur HEAD `e527531f0` : partiel. La borne de 32 de
  `spaces::organization` et `links_of` ont disparu avec F01 ; reste `Fga::concurrently`, appelé
  par `children_of` dans `memberships` : un analyste ou editor d'organisation lisait toutes
  ses équipes en parallèle, sans limite. Correction : borne nommée unique
  `fga::READ_CONCURRENCY` = 8, appliquée par la `JoinSet` elle-même, sans dépendance.
  Test `tree_walk_reads_stay_within_the_concurrency_bound` (20 équipes, 50 ms par Read, proxy
  OpenFGA) : pic entre 2 et 8 ; pic 20 sans la borne. Les contrôles Keycloak de l'import
  gardent leur propre limite de 8. `make test` réussi. Arc42 09.

## F11 Une seule réponse d'autorisation

- 2026-10-22 : vérification sur HEAD `29c0d4737` : confirmé. Organisation étrangère : 404 pour
  documents, 403 pour dossiers, scope, équipes et espace personnel ; `spaces::load` renvoyait
  409 « pending deletion » à tout appelant authentifié, avant tout contrôle, y compris dans
  grant/revoke et les sondes. Correction : `spaces::authorize` (et sa variante sous verrou)
  avec un ordre unique : inexistant ou étranger → 404, puis retiré → 409
  `space_pending_deletion`, puis sans permission → 403 (un espace retiré refuse déjà la
  permission dans OpenFGA, d'où cet ordre). `documents::authorized` supprimé ; dossiers,
  documents, processing, scope, création d'équipe/projet et espace personnel migrés ;
  grant/revoke gardent `may_change` et signalent le retrait après autorisation ; sondes :
  `allowed:false` pour chaque refus et document inexistant, 409 d'ambiguïté conservé.
  OpenAPI : 409 ajouté aux lectures processing ; client inchangé. Test
  `business_routes_share_one_authorization_answer` (table de vérité dossiers, documents,
  sonde), en échec sur HEAD ; sept attentes existantes 403 → 404 ou Conflict → code dédié.
  `make test` et intégration complète (114) réussis. Arc42 03, 03a, A2.

## F12 Un seul format d'erreur

- 2026-10-22 : vérification sur HEAD `07c094c10` : confirmé, sur trois modules : `api.rs` et
  `processing/http.rs` avec `Path`/`Query` d'axum (400 text/plain) et `ApiJson` (tout en 422,
  message serde pouvant reprendre l'entrée) ; `documents/http.rs` avec ses `Id`/`Params`/`Input`.
  Correction : module `extract.rs` (`ApiPath`, `ApiQuery`, `ApiJson`) avec la convention déjà
  testée par documents : JSON illisible → 400 `invalid_json`, valeurs de chemin, requête ou
  corps invalides → 422 `invalid_fields`, corps trop gros → 413 ; messages fixes. Anciens
  extracteurs supprimés. OpenAPI : plus de text/plain, 400/422 `ErrorBody` déclarés une fois
  pour toute route à paramètres ou corps ; schémas inchangés ; client RTK inchangé. Test
  `every_module_rejects_malformed_input_with_one_json_error_format`, en échec sur HEAD (400
  text/plain) ; test de contrat étendu. `make test` et intégration complète (112) réussis.
  Arc42 A2, carte des sources. Coquille du journal F13 corrigée.

## F13 Recherche locale par préfixe littéral

- 2026-10-22 : vérification sur HEAD `9d0d25d15` : confirmé. `ilike '%q%'` sur quatre
  colonnes, jokers non échappés (« %% » listait 20 profils), parcours complet de
  `user_identity`. Décision de Dimi : préfixe indexé. Correction : `like lower($1) escape`
  avec `%`, `_` et `\` échappés, préfixe insensible à la casse sur username, prénom, nom,
  e-mail ; requête non persistante pour un plan construit avec le motif ; migration
  `0003_user_identity_prefix_search.sql` (quatre index `lower(...) text_pattern_ops`).
  EXPLAIN sur 20 000 profils : BitmapOr des quatre index. Tests : unitaire de l'échappement,
  intégration `local_candidate_search_matches_a_literal_prefix_in_order_with_a_limit`
  (champs, casse, jokers littéraux, préfixe, ordre, limite 20), en échec avec l'ancienne
  requête. La recherche Keycloak est inchangée. Arc42 02, 04, 09, A2, A3.

## F08 Configuration stricte

- 2026-10-22 : vérification sur HEAD `6744e8f9b` : confirmé ; sous-modules déjà stricts,
  `config.rs` et `DirectoryDelegation` non. Clés étrangères inventoriées : YAML livré
  (`app.name`, `rebac.type`), exemple Entra (`scope`, `provider`, délégation Python),
  `values-gcp.yaml` (stockage GCS de bannières), `scheduler.temporal` laissé par le gabarit,
  profil k3d (corrigé par F21). Correction : `deny_unknown_fields` partout, clés retirées,
  gabarit qui retire `scheduler.temporal` après recopie, générateur du schéma de chart qui
  accepte cette seule entrée ; schémas de configuration et de chart régénérés. Tests :
  toutes les configurations livrées (YAML, chart, Entra, GCP, exemples) sans clé inconnue ;
  clé inconnue refusée par son nom à chaque niveau (mutation détectée) ; rendu k3d réel
  accepté par Helm ; binaire lancé sur la configuration k3d rendue : passe la lecture,
  refuse une clé fautive en la nommant. `make test` réussi. Le `serviceAccount` GCS de
  `values-gcp.yaml` reste à revoir (hors fiche). Arc42 A3.

## F21 Profil k3d propriétaire de la configuration du control-plane

- 2026-10-22 : révélé par F08, sur demande de Dimi (la factory reste agnostique ; tout est
  corrigé dans ce dépôt). Le profil k3d importait de `fred-deployment-factory` une
  configuration du control-plane écrite pour le Python (`observability`, `platform`,
  `knowledge_bases`, `storage.opensearch`/`log_store`/`content_storage`, `pool_*`, tailles
  de stockage, délégation), ignorée par Rust. `base-values.yaml.gotmpl` et le nouveau
  `secondary-values.yaml.gotmpl` (rendu par `tpl`) retirent toute configuration factory du
  control-plane ; `values.yaml.gotmpl` déclare les adresses k3d (realm, origine, OpenFGA
  9080, Temporal). Rendu helmfile comparé à HEAD : seules les clés Python disparaissent,
  aucune valeur lue par Rust ne change, seul le checksum de ConfigMap varie. Test du chart
  remplacé par un rendu du vrai profil (`test_k3d_profile_owns_manager_configuration_with_unchanged_factory_values`),
  en échec sur les fichiers de HEAD. Trois tests du chart échouaient déjà sur HEAD (topologie
  par défaut, spool, rollout du worker) : hors fiche. Arc42 08, README k3d.

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

- 2026-10-25 : Dimi choisit de conserver le verrou par organisation pour le moment
  et demande une explication arc42 de sa garantie et de sa portée. Vue générale
  1.3 et parcours documentaire complétés ; annexe [Open Issues](architecture/A10-open-issues.md)
  ajoutée pour distinguer durée de détention, attente, effet de plusieurs réplicas
  et alternatives éventuelles. Aucun problème de performance établi par cet
  échange ; décision à réexaminer sur des mesures représentatives. Documentation
  uniquement, sans changement de code, test, benchmark ni validation fonctionnelle.

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

Revue du 2026-10-21 : branche `weaver`, HEAD
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

- Objectif : travailler dans `~/Rebac/fred` sur `weaver`, avec le
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

- 2026-10-21 : Dimi confirme avoir créé `ArxivAi` avec Priya dans Demo/fredlab.
  Inspection en lecture seule du cluster secondaire : les 11 tables applicatives
  de `fred` ont été examinées (effectifs et données du parcours), les deux
  migrations SQLx correspondent aux checksums locaux ; aucun index invalide,
  contrainte non validée, trigger désactivé ou incohérence de parent/chemin de dossier.
  Un dossier racine ArxivAi dans fredlab ; cinq espaces (Demo, trois équipes et le
  personnel de Priya). Priya est identifiée via Keycloak ; les tuples du store actif
  OpenFGA rattachent fredlab à Demo et donnent editor à Priya. Bootstrap terminé,
  deux consentements v1 ; user_identity vide en mode annuaire Keycloak.
  Tables document/upload/processing/deletion vides. Quatre buckets S3 listés
  récursivement, tous vides, notamment app-content-documents ; compteurs SQL à zéro.
  Versioning absent, lifecycle absent, Object Lock non configuré sur ce bucket.
  Pas de test d'écriture ni de preuve du créateur historique : folder ne conserve
  pas created_by. Les bases internes des services ne sont pas auditées intégralement.
  Ce constat valide la cohérence de l'état observé, pas tous les cas de sécurité.


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

### F-004 : contrat d'inclusion dans la recherche

- 2026-10-23 : diagnostic en lecture seule puis proposition acceptée explicitement
  par Dimi, y compris le contenu/effet UI, les actions individuelles et groupées,
  et la reprise séparément autorisée des documents déjà publiés. Demande de code
  minimal et de réutilisation de l'UI Swift.
- Cause : présentation manager forcée à `retrievable: false`, aucun état Rust
  correspondant ; le worker écrit déjà true dans les vecteurs. Inclusion,
  indexation et autorisation de lecture restent trois notions distinctes.
- Lot local : migration additive 0004 (état et commande dans `document`, aucune
  nouvelle table), publication depuis metadata.json vérifié, mutation authentifiée
  via Temporal/KF, projection sur les seuls chunks publiés et confirmation après
  relecture. Aucun filtre de recherche ni tuple OpenFGA modifié. Pas de nouvelle
  dépendance ni service. Les échecs incertains restent explicitement en attente,
  sans relance automatique concurrente ni succès anticipé.
- UI : composants, icône, libellés et toasts Swift conservés ; adapter alimenté par
  Rust, menus d'inclusion réactivés, sélection/dossiers reliés au même transport.
  Client RTK régénéré depuis OpenAPI ; compilation Rust liée à cette génération.
- Reprise préparée via PUT retrievable avec null : vérifie l'artefact publié et
  les chunks, ne modifie pas les vecteurs. Ne pas annoncer le PDF existant corrigé
  avant migration/déploiement et cette reprise, à autoriser séparément.
- Lors du lot initial, tests ciblés préparés (publication/rejeu, contrat, projection
  partielle, restauration et menus UI), non exécutés à cette étape. Aucun build d'image, déploiement,
  modification du cluster, réingestion, commit ou push. Validation UI et recherche
  réelle non effectuées ; le parcours recherche/chat manager reste distinct.
- Architecture à reporter sur demande : 05, 02a, A1/A2/A3. Modifications locales
  préexistantes du journal et des chapitres 00/01 conservées.

- 2026-10-23, correction backend de la reprise (demande explicite, périmètre F-004) :
  séparation mutation unique, enregistrement de sa fin, puis vérification/confirmation.
  La commande JSON SQL porte `ready -> writing -> applied` et conserve `confirmed`.
  Le claim atomique interdit un deuxième writer, même après expiration de l'historique
  Temporal ; les callbacks anciens sont rejetés par l'identifiant de commande.
  Une demande déjà confirmée retrouve son résultat sans relivraison. Une reprise de
  workflow fermé en échec relit SQL et ne réécrit pas une projection appliquée.
  `AlreadyExists` n'est plus assimilé sans inspection à une exécution vivante.
- L'enregistrement de fin de mutation est répétable séparément ; aucune échéance
  globale du workflow ne supprime cette reprise pendant une panne temporaire de
  confirmation. La vérification/confirmation a cinq tentatives par exécution et
  peut être reprise par le même PUT après échec. Une mutation partielle, un thread
  encore actif ou une ancienne commande sans phase restent protégés. Pas d'endpoint
  de réparation opérateur : le README décrit le diagnostic et cette limite, sans
  promettre une réconciliation inexistante.
- Vérification OpenSearch : `_mget` séquentiel par lots de 500, uniquement les champs
  d'appartenance et d'inclusion ; identifiants exacts et erreurs par élément contrôlés.
  Coût par passage : `ceil(N/500)` requêtes pour N chunks, aucune mesure de performance
  revendiquée. Restauration `null` toujours sans écriture OpenSearch.
- Aucun changement UI supplémentaire, ni modification des permissions, migrations
  existantes ou données du cluster. Aucun déploiement, réingestion, commit ou push.
- Validation ciblée exécutée pour cette correction (2026-10-23) :
  - Depuis `apps/knowledge-flow-backend`, avec `CONTROL_PLANE_IT_TEMPORAL` pointant
    vers un conteneur jetable `mirror.gcr.io/temporalio/admin-tools:1.28` démarré
    avec `temporal server start-dev --ip 0.0.0.0 --headless` :
    `.venv/bin/python -m pytest tests/features/manager_processing/test_retrievable.py tests/features/manager_processing/test_persistence.py -q --tb=short --show-capture=no`
    : **58 passed**, dont cinq scénarios Temporal réels (panne temporaire,
    workflow échoué repris, réponse perdue, écriture incertaine, terminaison avec
    thread d'écriture toujours actif). Trois avertissements de dépendances
    préexistants (LangChain, Pydantic, ffmpeg absent).
  - Depuis `apps/control-plane` :
    `cargo test --lib processing::retrievable -- --nocapture` : **2 passed**.
    `cargo test --test openapi all_registered_routes_have_a_unique_operation_and_auth_contract -- --exact`
    : **1 passed**.
  - Avec PostgreSQL 15.12 et OpenFGA 1.15.1 jetables, les variables
    `CONTROL_PLANE_IT_POSTGRES`, `CONTROL_PLANE_IT_OPENFGA` et le jeton bootstrap
    fixe de fixture du Makefile ; les fixtures existantes démarrent SeaweedFS 4.29
    et Temporal jetables :
    `cargo test --test integration processing_admission_fences_publication_and_original_survival -- --ignored --nocapture`
    : **1 passed** ; admission réelle, commande conservée après livraison impossible,
    reprise par une autre instance de service, claim unique, confirmation conditionnée
    à la fin de mutation, demande inverse bloquée, confirmation répétée, ancien
    callback rejeté et publication initiale/rejeu.
    `cargo test --test integration retrieval_delivery_restarts_closed_failure_and_preserves_running_execution -- --ignored --nocapture`
    : **1 passed** ; le client Rust conserve le run actif et crée un autre run après
    terminaison, avec sa véritable politique Temporal et ses identifiants de requête.
  - Les premiers essais ont révélé des fixtures à adapter (ancien mock OpenSearch
    assignant une propriété en lecture seule et nom du champ protobuf de terminaison) ;
    corrigées avant les résultats ci-dessus. Les conteneurs de test sont supprimés.
- Limites des preuves : OpenSearch est simulé pour la vérification et les pannes ;
  les tests Temporal Python simulent le client HTTP manager, les transitions SQL et
  l'admission sont vérifiées séparément par les tests Rust avec PostgreSQL réel.
  Pas de parcours intégré complet Rust + KF + OpenSearch réel, ni de validation UI
  ou recherche réelle. Pas de campagne générale. Le PDF déjà ingéré reste inchangé :
  déploiement/migration puis restauration explicite `retrievable: null` restent des
  actions ultérieures soumises à autorisation distincte.


## 2026-10-23 — Merge Swift : registre des suppressions du control plane Python

Merge de `swift` (`09dda98e2`) dans `weaver` (`bbbf41afa`),
base commune `19709b017f7bff35e254df3242f38f6e5b0edd02`.
Les 12 conflits « supprimé ici, modifié dans Swift » sont résolus en conservant
la suppression de l'ancien service. Cela ne signifie pas que ses fonctionnalités
entrantes sont déjà couvertes par le Rust. Inventaire demandé par Dimi, chemins
relatifs à `apps/control-plane-backend/` :

| Fichier supprimé | Origine / nature | Sujet entrant | Décision et suivi Rust |
| --- | --- | --- | --- |
| `Makefile` | `bd155eb52` (#3253), fix build | Transmission du secret Docker CA pour les proxys TLS | Conserver la suppression ; besoin CA potentiellement pertinent, non porté au Makefile Rust. |
| `control_plane_backend/platform_access/api.py` | `624faf234` (#3235/#3236), feature | Permission dédiée `CAN_MANAGE_PLATFORM_ACCESS` sur les routes d'accès plateforme | À porter avec Platform Access ; aucun équivalent identifié dans Rust. |
| `control_plane_backend/platform_access/service.py` | `624faf234`, feature | Admission admin et aperçu d'activation via `access_manager_uid` | À porter avec admission, whitelist et Free links ; ne pas considérer comme couvert. |
| `control_plane_backend/product/service.py` | `624faf234`, feature | Bootstrap du rôle effectif `platform_access_manager` via OpenFGA | À porter dans le modèle Rust, son bootstrap et son contrat `/me`. |
| `control_plane_backend/users/schemas.py` | `624faf234`, feature | Nouveau rôle assignable `PLATFORM_ACCESS_MANAGER` | À porter avec permissions et API ; ne pas ajouter uniquement un rôle UI. |
| `dockerfiles/Dockerfile-prod` | `bd155eb52`, fix build ; `9c03ceab6` (#3243/#3259), outillage | Secret `ca-bundle`/`SSL_CERT_FILE`, uv 0.13.5 | uv sans objet pour Rust ; besoin CA à traiter avec le Makefile, pas de preuve d'échec actuel. |
| `pyrightconfig.json` | `9c03ceab6`, outillage | `enableExperimentalFeatures` | Sans objet pour Rust. |
| `tests/test_main.py` | `624faf234`, couverture feature | Nouveau rôle dérivé des checks OpenFGA plutôt que de Keycloak | Exigence à reprendre avec le portage ; Rust utilise déjà FGA mais ne connaît pas ce rôle. |
| `tests/test_platform_access.py` | `624faf234`, couverture feature | Vérifier la nouvelle permission sur les endpoints | À reprendre avec les endpoints Platform Access. |
| `tests/test_platform_roles.py` | `624faf234`, documentation de tests | Commentaires des quatre rôles délégués | Aucun nouveau comportement testé ; ne pas recopier la politique Python de bootstrap root. |
| `tests/test_team_registry_edit.py` | `624faf234`, régression autorisation | `team_manager` seul ne peut pas renommer une équipe | Garder l'invariant « rôle global seul sans droits métier ». Rust rejette ce rôle historique et utilise des rôles locaux ; aucune route registry-edit équivalente identifiée. |
| `uv.lock` | `60e5b1b65`, `b13bf8f5c`, `9c03ceab6`, `09dda98e2`, releases / dépendances | Versions 3.9.0/3.9.1, MCP v2, dépendances Python, format lock | Sans objet pour CP Rust/Cargo. Les locks entrants des autres services Python restent dans le merge. |

Points d'appui : `apps/control-plane/src/roles.rs` (quatre rôles, sans access
manager), `src/fga.rs`, `src/api.rs`, `src/platform.rs`, `openfga/model.fga`,
`tests/openapi.rs` (refus des rôles historiques), `Makefile` et
`dockerfiles/Dockerfile-prod` (pas de secret CA Cargo).
La note `docs/swift/ops/migrations/delegate-platform-access-and-team-management.md`
conserve les cas utilisateur Swift ; elle ne prouve pas leur implémentation Rust.

Autres résolutions du merge :

- Contrat API généré Rust conservé intact ; contrat Swift entrant relocalisé dans
  `legacyControlPlaneOpenApi.ts` avec uniquement l'adaptation du nom du transport.
  Le routeur conserve l'entrée manager `/admin/organizations` et les gardes Swift.
- Helm conserve la configuration manager Rust, le worker et le DNS frontend
  qualifié. Pas d'injection des champs de configuration Python dans le Rust.
- **Feature à porter #3211** (`4d8f1d285`) : composition par identifiant des
  inscriptions d'applications et de publishers KB. Dimi a validé explicitement
  de la tracer et de refuser les inscriptions non supportées. Les deux maps
  `registrations` restent vides ; leur contenu non vide est refusé par le schéma
  et par les templates, même sans validation du schéma. L'ancien paramétrage
  manuel frontend reste refusé pour éviter un contournement incohérent.
  Les scénarios de composition Swift restent récupérables dans le commit source ;
  le contrôle chart entrant est adapté au refus actuel, sans l'exécuter.
- Les tests k3d fusionnent les nouveaux contenus runtime Swift avec le nom de
  composant Rust `control-plane` et son image `control-plane-backend`.

Aucun test, build ou déploiement exécuté pour cette résolution. Le schéma Helm
est régénéré à partir des schémas de configuration existants. Cette résolution
n'est pas une validation fonctionnelle de l'ensemble des changements Swift.



## 2026-10-24 - Merge Swift dans Weaver

Intégration demandée par Dimi de `origin/swift` (`6348ad2cf`) dans `weaver`
(`3eecfd82f`), base commune `fb61751ee`. Onze commits entrants, 284 fichiers
modifiés côté Swift. Checkout initial propre ; point de retour local
`backup/weaver-before-swift-20261024` sur `3eecfd82f`.

### Résolutions

- Suppression de `apps/control-plane-backend` conservée, nouveaux fichiers
  inclus. Les quatre tests Python que Git proposait de déplacer dans
  `apps/control-plane/tests` sont également écartés. Aucun changement du code
  Rust, de ses migrations SQLx ou de son client généré.
- UI Swift conservée : auto-tests par familles, campagne de rôles, découverte
  et présentation des modèles, aperçus Mermaid thémés et export SVG.
  Leurs appels Python restent dans `legacyControlPlane`, comme les autres
  écrans non encore raccordés au Rust ; les nouveaux imports et mocks suivent
  cette séparation. Le client généré Swift est repris du commit entrant avec
  seulement la relocalisation du transport `controlPlaneApi` vers
  `legacyControlPlaneApi`, sans modification de contrat ni régénération.
- Fonctionnalités conserve la découverte Rust des agents par organisation,
  l'onglet Agents initial, les gardes et les commandes legacy désactivées dans
  ce contexte. Les ajouts Swift sur les modèles sont fusionnés dans la même page.
- `KeycloakService` conserve l'identité de session Weaver et ajoute la lecture
  du type de fournisseur Swift. PgVector conserve les opérations de chunk
  Weaver et ajoute la synchronisation des dossiers Swift.
- Les corrections Knowledge Flow, les évolutions SDK/runtime, les dépendances
  frontend, la configuration de découverte fred-agents et la documentation Swift
  sont intégrées. Leur présence ne prouve pas un parcours Weaver fonctionnel.

### Fonctionnalités du backend supprimé à réévaluer

Chemins ci-dessous relatifs à `apps/control-plane-backend/` dans le commit Swift.
Le code et les tests restent consultables par `git show 6348ad2cf:<chemin>`.

| Apport Swift | Sources et contrats conservés dans l'historique | Réévaluation Weaver |
| --- | --- | --- |
| Découverte de modèles sur endpoints compatibles, rafraîchissement, URL administrable, détails et modèles retirés (`484d7439c`, #3230/#3231) | `control_plane_backend/model_discovery/{api,service,schemas,store}.py`, `models/model_discovery_models.py`, tests `test_live_model_discovery.py`, `test_model_discovery_projection.py` | Reprendre le besoin avec le catalogue Rust ; définir les droits d'administration des URL et les garanties de transport des credentials. Non porté par ce merge. |
| Défauts et fallbacks chat par pod, projection des profils et révisions de découverte vers le runtime (même commit) | `product/{service,schemas,dependencies}.py`, `routing_policy/{service,schemas}.py`, `app/context.py`, `main.py`, `models/table_ownership.py`, migrations `7e0d93f21c6a_repair_applied_pod_defaults.py` et `b42e9f19d4ca_model_display_name_overrides.py` | Réévaluer avec l'exécution et le routage Rust. Les migrations Alembic ne sont pas transférées dans SQLx. Voir aussi `test_model_discovery_migration.py`, `test_platform_model_binding.py`, `test_routing_policy.py`. |
| Noms de modèles éditables, métadonnées de capacités et limites de tokens (même commit) | `capabilities/{api,catalog,schemas,service,display_name_store}.py`, `models/model_display_name_models.py`, tests `test_model_display_name_override.py`, `test_model_capability_projection.py` | UI et contrat legacy conservés ; persistance et projection Rust à évaluer. Les écritures de binding/URL ont une autorité plateforme dédiée dans `organization_authz.py`, à conserver lors du portage. |
| Mise à jour d'instances d'agents exemptées du contrôle de capacité pour les auto-tests (`3273bad7f`, #3244) | `product/service.py`, `tests/test_capability_selection_1974.py` ; note `fix-self-test-agent-updates` | À revoir lors du portage des instances et auto-tests ; ne pas introduire une exemption globale dans le Rust. |
| Liste des sessions d'une équipe publique exigeant `CAN_READ_CONVERSATIONS` (`882454069`, #3210) | `product/api.py`, `tests/test_product_api_authz.py` ; note `team-sessions-membership.md` | À reprendre avec les conversations ; accès à une équipe publique ne vaut pas accès à ses sessions. La campagne UI reste fondée sur les rôles Swift et ne valide pas les nouveaux comptes O1/O2/E1. |

Couverture associée également écartée avec le backend :
`test_capability_enablement_1980.py`, `test_main.py`, `tests/conftest.py`.
`pyrightconfig.json` est un changement d'outillage Python, sans portage Rust.

Autres apports intégrés à vérifier dans les parcours correspondants :
synchronisation des dossiers dans les vecteurs (#3245), isolation des aperçus
bruts (#3246), exclusion des vecteurs de sessions de l'audit corpus (#3247),
rafraîchissement OpenSearch après suppression (#3248), retrievability PgVector
(#3249), découverte SDK/runtime (#3231), Mermaid (#3256), publication frontend
(#3276) et runbook de rollback Compose (#3113).

Validation de résolution : lecture des conflits et comparaison des versions,
absence de marqueurs et d'entrées Git non fusionnées vérifiée avant commit.
Aucun test, compilation, contrôle qualité, déploiement ni push exécuté.
Les tests existants sont conservés et les mocks de Fonctionnalités adaptés ;
la compilation frontend et les validations fonctionnelles restent à effectuer
par Dimi. Pas de nouvelle proposition OpenSpec : intégration de changements
Swift existants, sans nouvelle fonctionnalité Rust.



### Evaluation du prochain lot : activation des templates d'agents

2026-10-24, demande de Dimi après le merge `b0baa57ec`. Evaluation seulement,
aucune implémentation. Invariant réaffirmé : conserver TOUTE l'UI Swift, ses
onglets et ses commandes ; raccorder progressivement une fonctionnalité sans
supprimer ou masquer les autres. La proposition de limiter les onglets est
abandonnée. Le natif Rust doit exercer le même parcours que fred-agents.

**Référence Swift :** `6348ad2cf`,
`control_plane_backend/product/service.py::{template_capability_id,_agent_capabilities_for_source}`
et `capabilities/{api,service,enablement,schemas}.py` dans l'ancien backend.
Le Control Plane projette les templates des runtimes dans le catalogue commun
comme `kind="agent"`, avec provenance runtime/template et `ADMIN_GATED`.
L'activation est une autorisation d'utiliser le template, pas un démarrage du
runtime ni une création d'instance. Le défaut `default_on` est complété par les
choix équipe `enabled/disabled/default`, où le refus explicite prévaut, et par
la portée des espaces personnels. Retirer un défaut ne retire pas un grant
explicite. Les dépendances par défaut sont vérifiées à l'activation. Les
instances existantes sont suspendues/réactivées selon leurs droits effectifs.

**Ecarts constatés :**

| Contrat | Swift / UI conservée | Weaver actuel | Travail à évaluer |
| --- | --- | --- | --- |
| Catalogue administrable | `CapabilityEnablementItem`, identité runtime/template, activation et portée | `agents.rs` retourne seulement `RuntimeCatalog`/`RuntimeTemplate` ; ligne UI de découverte spécifique | Projection commune natif/externe vers un contrat d'activation généré, réutilisé par la table existante. |
| Activation | Switch `default_on`, confirmations et retour serveur | Cellules d'activation vides, commandes désactivées | Droits canoniques OpenFGA, mutation et lecture organisationnelles, rechargement et erreurs. Aucun booléen parallèle d'autorisation dans SQL. |
| Portée | Défaut, exceptions équipe et classe personnelle | Modèle FGA sans ressource de template activable | Isoler O1/O2 ; préciser le remplacement de la portée singleton Swift par l'organisation Weaver. Ne pas appliquer un défaut à toute la plateforme. |
| Equipes | Matrice existante, états explicites/hérités et compteurs | Aucun branchement de la matrice sur les espaces Rust | Roster limité à l'organisation, tri-state et compteurs calculés côté serveur ; O2 sans équipe reste un cas valide. |
| Runtime natif | Contrat SDK de templates et exécution gérée | `kind="static"` hors enum SDK (`graph/react/deep/proxy`), absence de `default_tuning` et `max_chat_input_chars`, rejet d'`agent_instance_id` | Ne pas annoncer une équivalence complète. Aligner la partie template utile au lot sans inventer une catégorie d'exécution ; l'exécution gérée est un lot distinct. |
| Autorisation effective | `can_use` consommé par listing/enrollment/exécution | Démo directe hello-world après admission seulement | Tester le droit effectif du template ; ne pas utiliser l'endpoint direct comme preuve d'activation respectée. Raccordement instance/chat ultérieur. |

**Découpage proposé, à confirmer avant implémentation :**

1. Lot A, bouton existant "Activé pour tous" de l'onglet Agents : projection
   commune, lecture + mutation du défaut au niveau de l'organisation,
   confirmation de retrait, persistance FGA et retour serveur. Natif sans
   dépendances comme premier cas. Même projection pour une source externe.
   Les autres commandes restent présentes ; leur raccordement n'est pas
   annoncé comme réalisé. Les dépendances non satisfaites d'un template externe
   doivent être refusées explicitement, jamais ignorées pour faciliter le test.
2. Lot B, bouton existant "Gérer par équipe" : roster de l'organisation,
   trois positions, priorité des refus, héritage du défaut, compteurs et
   portée personnelle à traiter sans lui substituer la liste des équipes.
3. Lot C, instance puis usage : enrollment, états enabled/suspended,
   exécution gérée et contrôle d'autorisation, même contrat natif/fred-agents.
   Un défaut enregistré au lot A ne constitue pas ce parcours complet.

Si l'exigence est de finir dès maintenant toute l'activation Swift, A et B
forment le lot minimal cohérent ; un simple booléen serait insuffisant.
Les outils/capabilities, modèles, applications et KB restent visibles et hors
implémentation. Le mécanisme partagé d'activation des templates ne doit pas
être confondu avec le portage fonctionnel de l'onglet Capabilities.

**Matrice de validation proposée (non exécutée) :**

- `o1admin` découvre le natif, active le défaut O1, recharge et retrouve l'état ;
  une équipe sans exception, E1, hérite de l'accès. Désactivation et annulation
  de la confirmation donnent chacune le résultat attendu.
- `o2admin` voit le même catalogue disponible mais son défaut O2 reste inchangé,
  même sans équipe ; aucun identifiant d'E1 n'est divulgué dans les compteurs
  ou la matrice d'O2. Les mutations croisées sont rejetées.
- `o1owner`, `o2owner`, root plateforme seul et les quatre comptes E1 ne peuvent
  pas administrer cette activation organisationnelle, y compris par appel direct.
- Pour B : E1 explicitement désactivée reste refusée quand le défaut O1 est actif ;
  retour "par défaut" rétablit l'héritage ; grant explicite reste actif quand
  le défaut O1 est retiré. Les lectures après reconnexion reflètent OpenFGA.
- Même fixture de template annoncée par un runtime HTTP : identité/provenance
  distinctes mais même projection, mêmes droits et mêmes opérations d'activation.
  Vérifier une dépendance non disponible et un identifiant inconnu.
- Inventaire UI inchangé ; ni onglet ni commande supprimé ; les autres fonctions
  ne sont pas prétendues portées. Aucune activation présentée comme succès si
  le serveur refuse l'écriture.

Avant A : formaliser le contrat et les critères dans OpenSpec, vérifier la
réutilisation des tables existantes avant tout ajout, et détailler les requêtes
OpenFGA (types, pagination, volumes et coût selon organisations/templates/équipes).
La gestion d'indisponibilité des runtimes diffère déjà entre Swift (agrégation
partielle) et Weaver (échec global) ; décision explicite nécessaire avant de
changer cette politique, sans ajouter de cache/retry pour ce lot.
Aucun test, build, commit ou push effectué pour cette évaluation.

#### Contrat du lot A - précisions validées avec Dimi le 2026-10-24

Contrat préparé uniquement, sans implémentation. Les précisions ci-dessous
actualisent l'évaluation précédente sans effacer sa trace. Référence reproductible :
Swift `6348ad2cfd0b5b96292f51c79bba3461be555133`, second parent du merge
`b0baa57ec00d47eb7c57a7ffa1a22f765a7ece9b` (HEAD Weaver lors de la lecture).
Les modifications locales préexistantes, notamment ce journal et les fichiers
frontend/tests, sont conservées. Les constats suivants viennent de lectures de
code et de tests, pas d'une validation fonctionnelle.

**Bouton Swift réellement implémenté.** La page lit `GET /admin/capabilities`
et le registre global des équipes. Les templates publics sont projetés en
`kind="agent"`, `ADMIN_GATED`, avec identité `agent__{runtime_id}__{agent_id}`,
provenance séparée et `default_capability_ids`. `ADMIN_GATED` n'est pas la valeur
du switch : celle-ci vient du marqueur OpenFGA `default_on`.

- Activation sans dépendance manquante : `PUT /admin/capabilities/{id}/default-on`
  avec `{default_on: true}`. Le serveur vérifie `can_manage`, retrouve le template,
  refuse les réglages d'équipe obligatoires et les dépendances non `default_on`,
  puis assure l'ancrage et écrit le marqueur sur le singleton `organization:fred`.
- Si des dépendances connues manquent, l'UI demande confirmation, les active
  une par une, puis active le template en dernier. Ce groupe n'est pas atomique :
  un échec peut laisser des dépendances activées. Une dépendance absente du
  catalogue est ignorée par l'aide UI, mais pas par le contrôle des droits serveur.
- Désactivation : confirmation et lecture de `/revoke-impact` sans équipe cible ;
  annuler n'écrit rien. Confirmer envoie `{default_on: false}` : seul ce marqueur
  est retiré, les exceptions ne sont pas effacées. Les dépendances ne bloquent
  pas ce retrait. L'aperçu en chargement ne bloque pas la confirmation.
- Le switch reflète la lecture serveur ; la mutation invalide les lectures RTK
  du catalogue, des instances et des autres consommateurs. Succès/erreur et
  nombre de suspensions éventuelles alimentent les notifications.

| Point | Swift vérifié | Weaver lu / contrat A |
| --- | --- | --- |
| Portée | Singleton `organization:fred` ; défaut, choix équipe et classe personnelle | O1 et O2 totalement isolées. Le même template a des droits propres à chaque organisation. Aucun marqueur global ni booléen SQL de substitution. |
| Priorités | `disabled` explicite prévaut ; `enabled` explicite survit au retrait du défaut ; la classe personnelle module l'héritage | Conserver ce mécanisme OpenFGA. Le défaut couvre les équipes et espaces personnels de l'organisation, présents/futurs. L'admin pourra aussi autoriser tous ses espaces personnels indépendamment d'E1 ; édition de ces exceptions au lot B. |
| Etat initial | Projection `ADMIN_GATED`, sans activation automatique du template | Validé : Ralph désactivé dans O1 et O2 tant qu'aucun droit n'est accordé, sans exception pour le natif. |
| Catalogue et UI | Projection administrable et composants existants | Aujourd'hui découverte seule, cellules d'activation vides. Réutiliser table, Switch, confirmations, notifications et contrats générés ; adapter seulement branchement et textes de portée/impact nécessaires. |
| Runtime absent | Agrégation partielle : source omise ; pas de substitut de révocation pour un template agent absent (contrairement aux modèles/apps) | Ralph embarqué ne dépend pas d'un runtime HTTP. Weaver échoue actuellement globalement si une source active échoue. Dimi demande le comportement Swift pour les futurs fred-agents ; ce raccordement ultérieur devra résoudre cet écart, sans annoncer qu'il est déjà corrigé. |
| Dépendances | Activation refusée si un outil requis n'est pas lui-même `default_on` ; grants aux seules équipes existantes insuffisants | Hors lot A validé : Ralph est hello-world sans outils. Aucun portage de gestion des outils ni assouplissement silencieux du contrôle pour accepter un futur template dépendant. |
| Effet du retrait | Retrait du défaut puis traitement des instances | A retire seulement le droit hérité, conserve les exceptions et ne promet ni suppression d'instance ni interruption d'exécution. Enrollment, instances et exécution gérée restent au lot C. |

**Réutilisation et limites.** Weaver possède déjà l'admission, l'autorisation
`can_manage` sur une organisation, son contrôle de cycle de vie et la découverte
commune natif/externe (`src/agents.rs`). Les espaces personnels sont rattachés
à une organisation, sans héritage de ses droits de contenu. Le lot A ne doit
pas modifier cette confidentialité. Le modèle FGA actuel n'a aucun droit de
template : la persistance et l'évaluation organisationnelles restent à implémenter.
Les identités runtime/template restent communes ; aucune branche UI ou permission
par nom d'agent. Les calculs locaux de permissions Swift en Python/TypeScript et
ses exemptions par nom de templates internes ne sont pas des éléments à porter.

**Instances : réserve sur la synthèse précédente.** Swift filtre le catalogue
équipe par `can_use`, recontrôle l'enrollment et l'édition, et refuse la préparation
d'une exécution pour une instance désactivée ou suspendue. Cependant,
`set_capability_default_on(false)` préserve les grants explicites d'équipe sans
recontrôler `personal_on` avant suspension ; le droit personnel peut donc rester
accordé alors que l'instance est suspendue. La réactivation directe d'une instance
du template vérifie son droit mais ne repasse pas par la vérification des outils
utilisée pour les autres dépendants. Il serait inexact de résumer tout cela comme
une suspension/réactivation toujours conforme à tous les droits et disponibilités.
Dimi accepte de laisser la sémantique des instances hors A et de reprendre ces
trous plus tard, sur le Control Plane consolidé. L'endpoint direct hello-world,
admis sans contexte d'organisation et refusant `agent_instance_id`, n'est jamais
un consommateur ni une preuve de cette activation.

**Scénarios d'acceptation proposés, non exécutés.** O1 possède E1 et l'espace
personnel d'Alice ; O2 peut ne posséder aucune équipe.

1. Sans grant, Ralph apparaît désactivé dans O1 et O2. `o1admin` active le défaut
   O1 ; rechargement/reconnexion conserve l'état lu dans OpenFGA. E1 et l'espace
   personnel d'Alice héritent du droit ; une nouvelle équipe O1 l'hérite aussi.
2. Le catalogue de Ralph reste découvrable par `o2admin`, mais son défaut O2 ne
   change pas. Aucun identifiant ni compteur d'O1 ne fuit vers O2. Une lecture ou
   mutation administrative O2 par un admin d'O1 seul est refusée, et inversement.
   Un owner seul, un rôle plateforme seul ou un rôle E1 seul ne suffit pas.
3. Annuler le retrait laisse le défaut intact. Confirmer le retire uniquement
   dans O1 ; E1 sans exception perd le droit hérité. Aucun arrêt, enrollment ou
   changement de l'endpoint direct hello-world n'est annoncé.
4. Avec des exceptions préparées comme fixture du modèle, E1 explicitement
   refusée reste refusée malgré le défaut ; E1 explicitement autorisée le reste
   après retrait du défaut. Une classe personnelle autorisée garde son droit
   après ce retrait. L'édition UI de ces exceptions n'est pas une livraison A.
5. Refus serveur/OpenFGA : aucune notification de succès ni activation locale
   présentée comme enregistrée. Identité inconnue refusée. Tous les onglets,
   colonnes et commandes sont conservés ; les textes disent "cette organisation"
   et ne promettent pas de suspension d'instances inexistantes.

Décisions de périmètre ci-dessus validées par Dimi ; aucune autorisation
d'implémenter déduite de cette préparation. Les dépendances et le runtime externe
sortent des critères A ; leurs scénarios Swift restent à reprendre lors de leur
raccordement. Aucune nouvelle question fonctionnelle bloquante pour ce contrat.
Les formes exactes des tuples/routes et leurs coûts seront exposées avant le code,
sans matrice de permissions Rust/TypeScript ni nouvelle architecture hypothétique.
Sources Swift : `product/service.py`, `capabilities/{api,service,enablement,impact}.py`,
`libs/fred-core/fred_core/security/rebac/schema.fga`, `FeaturesPage.tsx`,
`capabilityEnablement.ts`, `controlPlaneApiEnhancements.ts` et
`test_capability_enablement_1980.py`, à lire au parent indiqué ci-dessus.
Aucun test, compilation, lint, génération, déploiement, délégation, commit ou push
effectué pour ce contrat. Aucun changement du code ou des contrats générés.

#### Lot A - raccordement local à valider, après le "go" de Dimi

2026-10-24 : Dimi valide le lancement, l'extension ciblée du générateur FGA
pour `but not`, le nettoyage des références de templates, et la convention
existante de transaction/verrou SQL pendant OpenFGA. Aucun appel runtime sous
transaction. Aucun changement d'instance ni application du nouveau modèle.

- `agents.rs` projette les définitions natives/externes dans le même contrat de
  ligne et lit le défaut de l'organisation. Identité UUIDv5 dérivée de
  l'organisation, du runtime et du template. Nouvelle mutation organisationnelle
  du défaut : admission, contexte, `can_manage`, découverte hors transaction,
  recontrôle sous les verrous/guards existants puis écriture atomique FGA.
- `agent_template` conserve défaut, exceptions et classe personnelle. La lecture
  effective utilise un Check OpenFGA avec le contexte de placement de l'espace,
  sans matrice Rust/TypeScript. La purge conserve l'ancrage jusqu'au drainage des
  pages d'exceptions. Le modèle JSON a été régénéré par le générateur Python
  existant, sans compilation ni validation exécutée.
- `FeaturesPage` réutilise le switch, les cellules d'identité/actions et la
  confirmation existants. Mutation/relecture RTK limitée à l'organisation,
  erreurs serveur conservées, aucune requête legacy d'impact sur les instances.
  Textes FR/EN limités à la portée organisationnelle et à l'absence d'effet sur
  les instances. Les autres cellules et commandes gardent leur état précédent.
- Régressions préparées (non exécutées) : héritage/exception/classe personnelle,
  isolation des défauts, purge de plus d'une page de grants, clic/annulation/refus
  côté UI. Inventaire OpenAPI des routes actualisé en préservant les corrections
  de tests présentes avant ce travail.
- README, carte des sources et annexes existantes actualisés ; coûts OpenFGA
  dérivés du code, sans mesure. Blocs documentaires régénérés par
  `python3 docs/architecture/tools/docs.py generate`, sans campagne de contrôle.

Après autorisation explicite de Dimi, `make -C apps/control-plane generate-openapi`
a réussi, compilation Rust comprise, puis
`npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`
depuis `apps/frontend` a réussi. Types et hooks générés relus avec leurs callers ;
aucun contrat généré édité manuellement. La compilation de génération ne constitue
ni une validation TypeScript du frontend ni une validation fonctionnelle du lot.
Le démarrage vérifie strictement le modèle FGA publié : une installation sur
l'ancien modèle ne prendra pas ce changement automatiquement. Aucune migration
ou réinitialisation d'instance n'est réalisée ni autorisée par ce lot.
Tests, lint, build frontend, déploiement et validation manuelle non exécutés.
Les modifications des autres travaux sont conservées.


## F-011 Découverte des définitions d'agents

- 2026-10-23 : demande d'un lot minimal Rust pour interroger fred-agents, sans
  inscription d'agent dans une organisation, équipe ou projet ; frontend exclu.
- Audit du code Swift (`fb61751ee`) : `product/service.py`,
  `_fetch_runtime_templates_uncached`, lit `GET /agents/templates` depuis
  `platform.runtime_catalog_sources` ; `list_agent_templates` agrège les résultats
  en mémoire. Aucune persistance SQL des définitions dans ce flux.
- `models/agent_instance_models.py` définit `agent_instance`, avec `team_id`
  obligatoire ; `enroll_agent_instance` appelle le store pour créer une instance
  lors de son inscription dans une équipe. Cette table ne constitue pas un
  catalogue de définitions indépendant des équipes.
- Choix soumis à Dimi : reproduire la découverte en direct Swift ou introduire
  explicitement un catalogue persistant distinct. Aucun code ni migration ajoutés
  avant cette clarification ; mise à jour arc42 en attente du comportement retenu.
- Préparation du démarrage : le profil fred-agents sélectionné par `config/.env`
  est `configuration_prod.yaml`. Aucun listener local sur les ports configurés
  5432 (PostgreSQL), 8080 (Keycloak), 9080 (OpenFGA). `make run` applique aussi
  les migrations runtime/capabilities ; non lancé. Aucun test, build, changement
  d'infrastructure, commit ou publication effectué.

- Décision explicite de Dimi : reproduire la découverte en direct Swift, sans
  catalogue persistant. Lot local : `agents.rs`, configuration facultative
  `platform.runtime_catalog_sources`, commande opérateur `discover-agents`.
  GET public `/agents/templates`, 10 secondes par source, métadonnées conservées
  et regroupées par runtime. Aucun endpoint HTTP, frontend, SQL ou enrollment.
  La commande échoue explicitement si une source échoue ; cette différence avec
  l'agrégation métier Swift best-effort est décrite dans le README et arc42 06.
- Schéma de configuration aligné manuellement sur les nouveaux types Rust, puis
  schéma Helm régénéré depuis les schémas des composants. Génération Rust du
  schéma et compilation non exécutées ; équivalence générateur à valider.
  Aucun test ni démarrage effectué ; dépendances locales toujours à préparer.
- 2026-10-23, audit et corrections : schémas de configuration et Helm identiques
  à leur génération. Tests unitaires ajoutés dans `agents.rs` (validation,
  regroupement, source désactivée non appelée, échec global sur 500, JSON invalide
  ou redirection, cause conservée si injoignable). Messages de validation nommant
  la source, `runtime_id` sans espaces de bord, validation unique au chargement,
  `yes()` réutilisé. Clippy, fmt et `cargo test` verts ; tests d'intégration non
  lancés. arc42 (bloc généré A3, matrice 03a, décision D23) reporté à un lot séparé.


- 2026-10-25 : préparation k3d sur `weaver`, après validation de l'ingestion et
  de la suppression documentaire par Dimi. Build local étendu à `apps/fred-agents`,
  consommateur `fred-agents` dans `images.yaml` et référence dans `images.txt`,
  avec le mécanisme de tags de contenu existant. Aucune sortie générée ici.
- Service confirmé par lecture : `fred-agents:80` vers 8000, préfixe
  `/fred/agents/v2`, catalogue public `GET /agents/templates`. UI organisation
  déjà consommatrice du catalogue Rust ; aucun changement UI nécessaire.
- Activation bloquée par le contrat de démarrage : le runtime Python exige
  `organization.suspended` dans OpenFGA, absent du modèle Weaver, puis les tables
  d'admission `platform_access_*`, `users` et `teammetadata` de l'ancien manager.
  Les valeurs héritées autorisent en outre la création du store `fred` et la
  synchronisation du modèle Swift. Aucun modèle remplacé, migration legacy
  ajoutée ou contrôle de sécurité désactivé pour contourner ces exigences.
- `applications.fred-agents.enabled` reste false ; source Rust non activée pour
  ne pas faire échouer aussi la découverte de Ralph. Les changements demandés
  d'activation restent donc à réaliser après adaptation explicite du contrat
  runtime/autorisation, hors de ce lot. README k3d : dépendances héritées,
  configuration cible et blocage documentés. Profil conservé dans Fred, factory
  inchangée ; aucun élargissement du dossier arc42 aux agents non validés.
- Validation restant à Dimi après résolution et déploiement : avec `o1admin`,
  administration de son organisation -> Agents, Ralph et templates publics
  fred-agents visibles, liste retrouvée après rechargement. Cela ne prouve ni
  création ni exécution d'instance. Échec global et refus d'activation des
  templates à dépendances indisponibles conservés. Aucune validation dynamique,
  aucun test, build, déploiement, commit ou push exécuté ; relecture seule.


- 2026-10-25 : sous-incrément Python de 1.4, lecture seule du singleton
  `authorization_store` dans `fred_core.security.rebac.authorization_binding`.
  Résultat immuable typé (`configured_store`, `active_store`, `model_id`) ; champs
  textuels non vides et comparaison exacte avec le `store_name` configuré, sans
  résolution par nom. Erreurs explicites sans valeurs ni détails du pilote SQL.
  Le lecteur emprunte l'AsyncEngine fourni et libère sa connexion après le SELECT.
  Aucun appel OpenFGA, écriture SQL, pool supplémentaire ou branchement du lifespan.
  Relecture statique uniquement ; vérifications proposées à Dimi : binding valide,
  absent, identité configurée différente, données invalides et erreur SQL, avec
  restitution de la connexion et moteur réutilisable. Aucun test, lint, build,
  déploiement, génération, commit ou push exécuté. La tâche 1.4 reste ouverte :
  modèle exact, distribution dans l'image et raccordement du démarrage restent
  aux lots suivants ; aucun parcours agent intégré ou validé dans arc42.


- 2026-10-25 : sous-incrément suivant de 1.4, consommateur asynchrone
  `authorization_model.validate_authorization_binding(binding, config, *, token=None)`.
  GET du store/modèle publié uniquement ; même binding rendu après comparaison
  JSON brute avec `Fga::bind` et les seuls défauts de `normalized_model` Rust.
  Erreurs distinctes : ressource canonique absente/invalide, distant absent,
  réponse invalide, incompatibilité, communication ; messages sans données sensibles.
  Client HTTP possédé/fermé par la primitive, sans SQL, retry ni initialisation FGA.
- Distribution préparée depuis `apps/control-plane/openfga/model.json` : hooks
  setuptools wheel/sdist/editable et package-data ; COPY explicite dans l'image
  finale fred-agents. Copie générée ignorée par Git, provenance et commandes dans
  le README fred-core. Aucune copie générée ni installation/build vérifié ici.
- Relecture statique seule. Vérifications proposées à Dimi : modèle exact et
  défauts autorisés acceptés ; ID/schéma/relation/condition/champ inconnu non vide
  ou ordre de tableau différent refusés ; 404/JSON invalide/réseau distingués ;
  unique GET exact sans mutation ; ressource dans wheel/sdist/install/image hors
  checkout ; fermeture HTTP sur succès/échec/annulation et moteur SQL réutilisable.
  Aucun test, lint, build, génération, déploiement, commit, push ou autre assistant.
  Lot 1 et travaux étrangers conservés. Tâche 1.4 ouverte : raccordement du
  démarrage et admission Weaver restent à faire ; aucun parcours agent validé
  ni extension du dossier arc42 au-delà de son périmètre accepté.

- 2026-10-25 : complément de distribution du modèle du lot 2 : COPY canonique
  ajouté à Knowledge Flow prod (y compris ses variantes) et dev, après fred-core
  et avant installation ; fred-agents avait déjà cette copie. Les builders prod
  excluent les paquets locaux. La ressource générée est exclue du contexte Docker,
  sans exclure la source Rust suivie par Git : aucune dépendance à une copie locale
  absente ou périmée. Relecture statique seule, aucun test, build, génération ou
  déploiement ; packaging non validé dynamiquement. Le Dockerfile dev conserve
  son écart préexistant entre /app et les chemins ../../libs et ../../scripts,
  hors périmètre. Lots 1/2 et modifications étrangères préservés ; tâche 1.4 ouverte.


- 2026-10-25 : priorité confirmée par Dimi au socle ReBAC pour le prochain lot ;
  portage complet du filtrage d'admission globale Swift conservé mais différé.
  Voir l'arbitrage SEC-1 et la décision 2a du change existant. Aucun blocage
  temporaire des autres fonctions à introduire ; raccordement non encore validé.



- 2026-10-25 : raccordement du vrai lifespan Python au binding Weaver : stockage
  durable d'abord, SELECT de `authorization_store` et restitution SQL, validation
  du modèle exact, puis client OpenFGA lié à `active_store`/`model_id`, y compris
  après recréation, avec HIGHER_CONSISTENCY. Pas de résolution par nom, création,
  synchronisation ou latest. Fermeture du client ajoutée au finally ; moteur SQL
  possédé avant le premier await et fermetures des ressources indépendantes.
- Pod : suppression des initialisations Swift d'admission/suspension et du store
  `users`, ainsi que des appels de suspension avant outil. Les contrôles métier
  de ressources restent présents. Les dépendances utilisateur communes du pod
  utilisent la même vérification JWT/délégation, puis `terms_acceptance` selon
  la version configurée, y compris pour la personne déléguée canonique. Aucun
  annuaire écrit ni resolver Rust délégué annoncé. Knowledge Flow, MCP Swift et
  `rebac_sdk_factory` conservent leurs helpers d'admission existants.
- Profil C3/PostgreSQL requis ; identité de store `control-plane` et CGU v1
  alignées dans les configurations livrées du pod et l'overlay k3d, sans activation.
  Catalogue, Custom sans outil par défaut, modèles, historique/checkpoints et
  observabilité conservés. Les migrations runtime/capacités restent nécessaires,
  jamais celles du manager Python. Le filtrage global reste différé en 4.1.
- Relecture statique seule : aucun test, lint, build, génération, démarrage,
  déploiement, commit, push ou autre assistant. Tâche 1.4 et parcours global non
  cochés ; arc42 et travaux étrangers préservés. Vérifications proposées à Dimi :
  démarrage Weaver sans tables Swift, échecs binding/modèle/CGU explicites,
  fermeture après échec/annulation, modèle figé après recréation du client,
  catalogue réel, JWT invalides, CGU absentes/périmées, OIDC non UUID et assertions
  d'un bearer ordinaire refusées. Catalogue servi ne prouve pas conversation.



- 2026-10-25 : resolver Rust pour le pod Python, sous-incrément de 1.5 :
  `GET /spaces/{space_id}/agent-instances/{agent_instance_id}/runtime` lit
  l'instance persistée et rend `subject_id`, le placement canonique et
  `agent.{instance_id,runtime_id,template_id,template_key,configuration}`.
  `configuration` restitue le JSON tuning sauvegardé complet, sans redécouverte
  ni définition/exécution d'agent Rust. Espaces équipe/personnel comme les
  instances existantes ; niveaux absents null, personnel sans héritage documentaire.
- Identité : vérification JWT existante, audience déléguée acceptée uniquement
  par ce resolver si `security.delegation.accept_delegated_calls=true`.
  `person/run/agent` exigent rôle, audience, issuer, restrictions de clients et
  éventuels marqueurs de service ; grant incomplet/invalide ou cible différente
  refusé. Un workload sans personne ne prend pas les droits d'un utilisateur.
  CGU de la personne effective, espace actif/lisible, instance dans cet espace
  et activée, provenance du template et `can_use` sont contrôlés à chaque appel.
- Contrat OpenAPI déclaré dans le code, sans génération. Aucun changement au
  consommateur Python, sessions, frontend, Ralph ou moteur embarqué. Renouvellement
  des credentials conservé côté Python ; aucun nouveau jeton/bail émis. Pas de
  filtrage global ajouté. Relecture statique seulement, aucun test, génération,
  build, déploiement, commit/push. Tâche 1.5 ouverte jusqu'au raccordement Python
  et à la validation Dimi ; le parcours de conversation n'est pas déclaré acquis.

- 2026-10-25 : préparation du déploiement catalogue sur `k3d secondary` à la
  demande de Dimi. Overlay : pod Python `fred-agents` activé, migrations runtime /
  capacités activées avec le secret PostgreSQL existant, source Rust
  `http://fred-agents/fred/agents/v2` et route ingress `/fred/agents/v2` ajoutées.
  Le hook de préparation accepte désormais les quatre déploiements attendus ;
  son contrôle précédent à trois aurait refusé la nouvelle topologie.
- Catalogue existant conservé, sans changement de protocole ni auto-activation
  des templates. Adresse retour du pod vers le Rust déjà fournie par le chart ;
  secrets, modèles, issuer secondary et stockage hérités conservés. README k3d
  actualisé pour remplacer le blocage de démarrage devenu obsolète.
- Activation métier laissée à Dimi dans l'UI après son déploiement. La découverte
  ne valide pas le chat : consommateur Python du resolver, contrôles d'exécution,
  préparation/sessions et réception déléguée configurée restent au raccordement
  suivant. Aucun changement de Ralph ni du lot de démarrage. Lecture statique
  seule ; aucun test, rendu, génération, build, déploiement, commit ou push.

## DOC-3 Vue d'ensemble de Weaver

- 2026-10-23 : à la demande de Dimi, le chapitre 1 contient uniquement le
  diagramme général : UI, Control Plane, Knowledge Flow, Agentic Pod, Temporal
  et Shared Infrastructure. Les liens invisibles organisent les blocs sans
  représenter les interactions. Les séquences seront traitées ultérieurement.
- Aucun changement de code ou de déploiement ; aucun build ou test lancé.

- Premier incrément de diagrammes ajouté sur accord de Dimi : découverte opérateur
  dans le chapitre 6 ; séquence de traitement et états d'une tentative dans le
  chapitre 5. Chapitre 1 conservé inchangé. États relus dans models/store,
  publication et dispatch : pending, running, succeeded, failed ; les retries
  d'activités restent dans running, la relance explicite crée une nouvelle tentative.
  Aucun build, test ou validation du rendu Mermaid exécuté.


## DOC-4 Dossier humain et périmètre Weaver

- 2026-10-24 : passe éditoriale avec Dimi sur l'introduction, la vue d'ensemble,
  les journeys, la sécurité, les organisations et les documents. Texte court,
  schémas lisibles, vues fonctionnelles et techniques séparées ; détails déplacés
  dans les annexes A4 à A9. Liens actualisés après renumérotation des journeys.
- Skill partagé `fred-architecture` ajouté, lecture obligatoire via AGENTS.md et
  CLAUDE.md. Retrait des consignes qui plaçaient un feature plan dans arc42.
- Agents, conversations et extensions non câblés dans Weaver retirés du dossier,
  ainsi que le feature plan. La découverte CLI seule ne valide pas leur intégration.
- Dimi accepte de conserver le dossier jusqu'à l'ingestion native en cours de
  finalisation et demande le commit de cette passe. Cet accord porte sur le contenu
  documentaire ; il ne valide pas le parcours d'ingestion de bout en bout.
- Aucun test applicatif, build ou déploiement lancé pour cette passe documentaire.


## F-012 Suppression unifiée

- 2026-10-24 : lot D2 implémenté localement : suppression unitaire et groupée
  des documents manager dans `DocumentWorkspace.tsx`, confirmation existante,
  erreurs backend et bilan partiel. Le menu lit `managerProcessing.status`
  (pending/running) ; aucun pré-filtrage en suppression groupée ni suivi de purge.
  `controlPlaneApiEnhancements.ts` exporte le hook généré, désactive le rejeu
  sur 401 et invalide Documents (liste et stockage). Tests ajoutés dans
  `DocumentWorkspace.manager.test.tsx` et `controlPlaneApi.test.ts` pour les
  confirmations, traitements actifs, échecs partiels, détail backend et
  DELETE suivi du rafraîchissement. Chemin tags conservé, couvert notamment
  par `useDocumentCommands.removeFromLibrary.test.tsx` (conservation du chemin
  du dossier) et la suppression groupée de `DocumentWorkspace.folderBulk.test.tsx`.
  `COMPONENT-UX.md` adapté. Après revue, confirmations du seul chemin manager
  corrigées : titre `rework.resources.action.delete` et nouvelles clés fr/en
  `rework.resources.confirm.deleteManagerDocument`, `deleteManagerDocuments`
  et `deleteManagerMixed` pour décrire la suppression, avec assertions adaptées.
  Clés de l'ancien chemin tags inchangées ; `deleteManagerPartial`
  parle désormais d'éléments en fr/en pour couvrir documents et dossiers.
  Commandes proposées, non lancées : `make code-quality`,
  `make -C apps/frontend test`. Aucun test, build, make, npm, commit ni push
  exécuté ; validation fonctionnelle à effectuer. Passe arc42 réservée à D3.

- 2026-10-24 : lot D1 implémenté : `DELETE /documents/{id}`, reçu document,
  migration 0009 (`target_kind` en texte) et complétion par la purge P3a.
  Décisions : 409 `processing_active` pour un traitement pending/running,
  rétention héritée du catalogue de l'espace, `GET /deletions/{id}` inchangé
  et réservé à la plateforme. Le test de parcours couvre droits, rejeu,
  invisibilité immédiate, réutilisation du nom, attente du nettoyage dérivé,
  purge avec/sans traitement et conservation du dossier et du témoin.
  Limite connue : un dossier contenant un document supprimé non encore purgé
  ne peut pas être supprimé ; `DELETE /folders/{id}` répond 409 jusqu'à la purge.
  Observations après revue : un reçu par document rend la purge en masse lente
  avec les réglages par défaut (100 reçus / 10 min, verrou plateforme par batch).
  Un reçu de document non terminé bloque la suppression de son espace par
  chevauchement ; ce point reste à traiter avec la suppression des espaces.
  Annexes A2/A3 adaptées ; aucun chapitre principal ni bloc généré modifié.
  Commandes non lancées : `make code-quality`,
  `make -C apps/control-plane test-integration`,
  `make -C apps/control-plane test-lifecycle-temporal`,
  `make -C apps/control-plane generate-openapi`,
  `make -C apps/frontend update-control-plane-api`,
  `make -C docs/architecture generate check`.
  Aucun test, build, cargo, make, Docker, commit ni push exécuté ; validation
  et régénération OpenAPI/client/routes/ER restent à effectuer.

- 2026-10-24 : correction de la fixture S3 après reproduction des 19 échecs
  d'intégration : SeaweedFS refusait les écritures avec 0,47 % d'espace libre
  sur le disque hôte, sous son seuil de 1 %. `tests/support/content_bucket.rs`
  place désormais les données jetables dans un tmpfs borné à 256 Mio par
  conteneur. Aucun comportement de production modifié, aucune adaptation arc42
  nécessaire. Validation exécutée : contrat SeaweedFS ciblé réussi, puis
  `make -C apps/control-plane test-integration` réussi (121 tests, 0 échec,
  60,84 s), y compris les deux tests P3a. Aucun commit ni push.

- 2026-10-24 : lot P3a implémenté : migration 0008 et compteur `documents_deleted`,
  purge bornée des documents marqués après nettoyage des résultats dérivés.
  Correction après revue : le curseur d'une génération publiée pouvait laisser
  des vecteurs protégés derrière lui ; la purge par document remplace ce balayage
  pour les documents retirés. Les deux discriminants `Cleanup.purge_document`
  et `Cleaned.purge_document` distinguent les modes ; un compte rendu dont le mode
  ne correspond pas à l'état retiré est refusé. Knowledge Flow modifié avec
  l'accord de Dimi : suppression des vecteurs par document, comptage avant
  acquittement et suppression bornée des objets du préfixe de l'installation.
  Si le comptage voit encore des vecteurs (visibilité OpenSearch différée après
  `delete_by_query`), un log info est émis sans acquittement ni exception ; le
  balayage continue avec le candidat suivant. La suppression idempotente est
  rejouée au prochain cycle. Le test vérifie aussi le traitement et l'acquittement
  d'un second candidat dans la même liste.
  Marques encore posées uniquement par les tests ; acceptation inchangée.
  Tests Rust adaptés (curseur à 200 sur 400 chunks, modes périmé et inverse) et
  tests Python ajoutés (objets 0/200/201, vecteurs restants sans acquittement).
  Le test actif conserve ses assertions ; seul le champ Rust obligatoire
  `purge_document: false` est ajouté. Annexes A2/A3/A9 adaptées.
  L'entrée `/apps/control-plane/agent/` de `.gitignore` est retirée
  (déjà absente au début de cette correction).
  Limite connue : après suppression des lignes du document, ses vecteurs ne
  sont plus rebalayés ; une écriture zombie au-delà du bail + 60 s ne serait
  pas rattrapée. Les originaux S3 restent couverts par l'inventaire sans fin.
  Commandes non lancées : `make code-quality`,
  `make -C apps/control-plane test-integration`,
  `make -C apps/control-plane test-lifecycle-temporal`,
  `make -C apps/knowledge-flow-backend test-one TEST=tests/features/manager_processing/test_persistence.py`,
  `make -C apps/control-plane generate-openapi`,
  `make -C apps/frontend update-control-plane-api`,
  `make -C docs/architecture generate check`.
  Aucun test, build, cargo, make, Docker, commit ni push lancé ; validation et
  régénération OpenAPI/client/ER restent à effectuer.

- 2026-10-24 : I3 committé à la demande de Dimi (`63e6a1eae`), avec les
  changements de formatage et d'ER présents au moment de la demande.
  Lot P2 implémenté : migration 0007, visibilité des dossiers/documents actifs,
  unicité des noms actifs, lectures, quota et producteurs filtrés ; aucune marque
  posée hors du test. Décision : ligne retirée = absente, sans nouveau code
  d'erreur ; le 409 des espaces reste inchangé.
  Exclusions conservées : inventaire des originaux (ligne marquée encore vivante),
  contrôles des espaces contenant des documents et nettoyage lifecycle,
  écritures du worker de traitement (état terminal à imposer en P3).
  Un test dans `tests/support/document_processing.rs` réutilise les fixtures HTTP,
  stockage et processing ; aucun invariant existant ne formule exactement P2.
  Adaptation demandée par Dimi : `r.pdf` est marqué seul dans `C/` actif,
  auprès de `c.pdf` témoin ; aucune fixture de document à la racine. Réutilisation
  des noms par HTTP : dossier `A` à la racine et nouvel upload `r.pdf` dans `C/`.
  Preview native également filtrée après inventaire des requêtes directes.
  A2 mis à jour, aucun chapitre
  principal ni bloc généré modifié ; ER à régénérer.
  Commandes non lancées depuis la racine : `make code-quality`,
  `make -C apps/control-plane test-integration CARGO_TEST_OPTS=retired_folders_and_documents_are_absent_from_reads_and_producers`,
  `make -C apps/control-plane test-integration`,
  `make -C docs/architecture generate check`.
  Aucun test, build, cargo, make, Docker ni push lancé ; P2 non committé.

- 2026-10-24 : lot I3 implémenté : reçu SQL renommé en `deletion` par la
  migration 0006, avec ses index de recherche, sa clé primaire et son unicité
  de cible ; requêtes et noms d'audit adaptés, `target_kind` ajouté à l'audit
  d'acceptation. Pas de colonne `origin` : `target_kind` reste le point d'entrée.
  Workflow Temporal `SpaceDeletionSweep`, schedules et préfixe inchangés ;
  leur renommage demanderait une décision et une étape d'exploitation séparées.
  Migrations précédentes, blocs générés et chemins des tests conservés.
  Commandes non lancées depuis la racine : `make code-quality`,
  `make -C apps/control-plane test-integration`,
  `make -C apps/control-plane test-lifecycle-temporal`,
  `make -C docs/architecture generate check` (dont régénération ER).
  Aucun test, build, déploiement, commit ni push exécuté.

- 2026-10-24 : lot I2 implémenté dans
  `apps/control-plane/src/lifecycle/{worker,cleanup}.rs` et
  `docs/architecture/A3-manager-operations.md`, avec mise à jour du présent journal.
  Le futur de `clean` porte le span `deletion` ; `batch`
  renseigne `target_kind` après lecture du reçu via sa sérialisation API.
  Ce champ reste absent avant cette lecture.
  Le test existant `logging::tests::json_has_fred_core_fields_and_request_context`
  couvre la propagation des champs du span ; aucun test ajouté.
  Le contexte du span prévaut dans la map JSON, sans doublon : le champ
  `operation_id` de l'audit est conservé. Commandes non lancées depuis la racine :
  `make code-quality`, `make -C apps/control-plane test-one TEST=logging`,
  `make -C apps/control-plane test-lifecycle-temporal`.
  Aucun test, build, commit ni push exécuté.

- 2026-10-24 : validation rapportée par Dimi après recompilation :
  `make -C apps/control-plane test-lifecycle-temporal` réussit
  (1 test, 0 échec, 25,19 s). Les 118 tests d'intégration avaient également
  réussi lors du lancement précédent. Aucun test relancé par Codex.

- 2026-10-24 : Dimi rapporte 118 tests d'intégration réussis et un échec du
  test Temporal sur le délai de progression. Le test lançait la commande
  `worker` supprimée ; `tests/lifecycle_temporal.rs` lance désormais `serve`,
  utilise l'identité de test et attend le rôle de journal `api`. L'attente
  détecte aussi la sortie du processus. Correction non exécutée ici ; aucun
  test, build, commit ni push lancé.

- 2026-10-24 : I1 implémenté : Mode retiré (policy.rs, store.rs), migration 0005, catalogue,
  values.yaml, tests, A3 ; openapi.json, client frontend et ER à régénérer.

- 2026-10-24 : lot I1 implémenté : retrait de `Mode` dans
  `apps/control-plane/src/lifecycle/{policy,store}.rs`, migration
  `apps/control-plane/migrations/0005_drop_deletion_mode.sql`, adaptation de
  `apps/control-plane/tests/support/{space_deletion,organization_console}.rs`,
  `apps/control-plane/config/lifecycle_policy_catalog.yaml`,
  `deploy/charts/fred/values.yaml` et `docs/architecture/A3-manager-operations.md`.
  Le helper `immediate()` désérialise `PT0S`, sans nouvelle API publique.
  Commandes non lancées : `cargo fmt --check`,
  `cargo clippy --lib --tests -- -D warnings`, `cargo test --lib lifecycle::policy`
  dans `apps/control-plane` ; depuis la racine,
  `make -C apps/control-plane test-integration CARGO_TEST_OPTS=space_deletion`,
  `make -C apps/control-plane generate-openapi`,
  `make -C apps/frontend update-control-plane-api`,
  `make -C docs/architecture generate` et `make -C docs/architecture check`.
  Restent hors périmètre : le catalogue du test `tests/lifecycle_temporal.rs`
  contient encore `mode` et sera rejeté ; la spécification OpenSpec courante
  décrit encore les modes, tout comme la description du reçu dans A2. Les
  migrations appliquées, archives et fichiers générés restent inchangés. Aucune validation exécutée, aucun commit ni push.

- 2026-10-24 : conception discutée et validée avec Dimi, sans OpenSpec ni issue
  GitHub (choix explicite). Swift n'a pas de chemin unifié : document synchrone
  dans Knowledge Flow, équipe sans purge des documents, seules les conversations
  passent par Temporal. Le module Rust `lifecycle/` porte déjà le patron swift
  (reçu durable, catalogue, balayage Temporal) pour les espaces sans documents.
- Décisions :
  1. Plus de `Mode` : une rétention par type de cible, `PT0S` pour « immédiat ».
  2. Suppression acceptée pendant un traitement : arrêt forcé (statut `failed`)
     dans la transaction d'acceptation ; les rappels Knowledge Flow refusent déjà
     un traitement terminé ; le nettoyage des générations rattrape les écritures
     tardives.
  3. Tout le périmètre est marqué à l'acceptation (`deletion_id` sur espaces,
     dossiers, documents) ; une seule règle : visible si espace actif et
     `deletion_id` nul. Unicité des noms restreinte aux lignes actives ; quota sur
     les seules lignes actives.
  4. Effet immédiat sur toutes les lectures et sur la recherche via SQL ; contenu
     (S3, chunks, vecteurs, lignes) purgé en différé. Exigence pour le futur lot
     recherche : résultats confirmés par le control plane, l'index ne décide
     jamais de la visibilité.
  5. Toute suppression passe par `accept(target)` (202 + reçu), dossiers vides
     compris. Points d'entrée : document, dossier, projet, équipe, organisation,
     utilisateur.
  6. Utilisateur : Fred ne touche jamais Keycloak/OIDC. Accès coupé à
     l'admission pendant la purge ; ensuite, un retour SSO crée un utilisateur
     vierge, sans liste de bannis. Root du bootstrap protégé.
- Observabilité : pas de colonne `origin`, le `target_kind` du reçu est le
  point d'entrée (document, dossier, projet, équipe, organisation, utilisateur) ;
  un span par batch, audit `deletion.*` ; KPI par requête sur les reçus tant
  qu'aucun exporteur n'existe.
- Lots immédiats : I1 retrait de `Mode` ; I2 span `deletion` du worker ; I3
  renommage `space_deletion` en `deletion` (workflow Temporal non renommé).
  Prompts Codex rédigés pour I1 à I3, à relire avec Dimi avant exécution.
- Lots prudents, prompts écrits après revue du lot précédent : P2 règle de
  visibilité unique (`deletion_id` sur dossiers et documents) ; P3 purge des
  documents par le worker et arrêt forcé du traitement ; P4 `DELETE` document et
  dossier en 202 ; P5 origine utilisateur. Chaque lot met à jour arc42 pour le
  seul comportement implémenté.
- Aucun code modifié, aucun test, build ou déploiement lancé.
- 2026-10-24 (revue) : P3 scindé en P3a (le worker purge les documents marqués
  de son opération une fois leurs générations nettoyées ; acceptation inchangée,
  marques posées par les tests seulement) et P3b (l'acceptation marque dossiers
  et documents, arrête les traitements en cours, lève le refus des espaces avec
  documents). Knowledge Flow traite 404 et 409 comme des erreurs permanentes
  non relancées (`client.py`) : aucune différence de comportement entre les deux.
- 2026-10-24 : répartition validée par Dimi. Le Control Plane décide et purge
  SQL, originaux S3 et tuples OpenFGA ; Knowledge Flow reste l'exécutant des
  données qu'il écrit (chunks, vecteurs, objets dérivés) par le protocole de
  nettoyage des générations, sans jamais décider d'une suppression. Les anciens
  chemins de suppression propres à Knowledge Flow (swift) sont des candidats au
  retrait lors d'une consolidation ultérieure, hors lots P3.


## F22 Agent Rust embarqué hello-world

- 2026-10-24 : `make test-integration` reproduit un seul échec (121 réussis) :
  le test de démarrage sans Temporal attendait encore 404 pour PATCH/DELETE
  document. Attente PATCH corrigée en 405 ; DELETE vérifie désormais 202, le
  reçu document en état `queued` et son lien persistant en base malgré Temporal
  indisponible. Nouvelle exécution complète : 122 réussis, aucun échec ni test
  ignoré. Aucun code de production modifié, aucun commit créé.
- 2026-10-24 : correction ciblée des trois échecs OpenAPI avant les commits :
  inventaire complété avec les deux routes agent et la suppression de document,
  reçu `Receipt` vérifié pour les réponses de suppression `200`/`202`, absence
  des anciennes routes document toujours contrôlée. `make test` du Control Plane
  passe : 66 tests réussis, 124 tests avec services/navigateur ignorés par cette
  cible. Tests d'intégration et qualité non exécutés ; aucun commit créé.
  Correction de tests uniquement, sans changement de contrat ni impact arc42.
- 2026-10-24 : raccordement local de Console d'administration -> Features -> Agents
  au contexte d'organisation (`useOrganizationAdmin`, garde, navigation et layout).
  La lecture `GET /organizations/{organization_id}/agents` réutilise la découverte
  Rust après admission, contexte unique, cycle de vie, `can_manage` et contrôle du
  type organisation. Aucun droit plateforme ni ownership seul ne fait exception ;
  le cumul plateforme/admin d'organisation conserve l'accès organisationnel.
- Identifiant et nom `fred.github.ralph`, version `0.1.0`, fournisseur
  `control-plane`, description de démonstration sans LLM conservée. L'exécution
  utilise le même `AGENT_ID` ; exemple HTTP mis à jour. Source fred-agents désactivée
  dans la configuration locale fournie ; toute source externe activée conserve
  sa politique d'échec global. Aucun service démarré ni fred-agents modifié.
- Onglet Agents ouvert par défaut dans ce parcours, table et identité existantes,
  sans nom d'organisation ni libellé technique ajouté. Lecture Rust uniquement ;
  pas de projection factice en enablement. Cellules d'activation, de portée et de
  santé sans valeur ; commandes legacy inopérantes dans le contexte organisationnel.
  Autres onglets conservés avec leurs lectures existantes, non portés.
- OpenAPI et client RTK régénérés depuis les sources (`make -C apps/control-plane
  generate-openapi`, puis `npx --no-install @rtk-query/codegen-openapi
  src/slices/controlPlane/controlPlaneOpenApiConfig.json` depuis apps/frontend).
  Compilation strictement pour la génération autorisée explicitement par Dimi.
  Fixtures AppState et mocks frontend adaptés, sans exécution de tests.
- README du composant/de l'agent, carte des sources et annexes A2/A5 actualisés ;
  bloc des routes A2 régénéré avec le générateur existant. Coût dérivé du code
  ajouté au chapitre 09, sans mesure. Aucune validation manuelle du parcours,
  aucun test, lint, build frontend, audit indépendant, commit, push ou déploiement.
  Restent à valider par Dimi : affichage, accès direct/rechargement, refus API
  (rôles insuffisants, équipe/projet, autre organisation), cumul de rôles et
  fonctionnement sans source externe activée. Les modifications locales antérieures
  sont conservées.

- 2026-10-24 : découverte CLI du template embarqué depuis la définition de la
  bibliothèque, sans source configurée ni appel HTTP local. Catalogue unique
  `fred-native`, identifiant réservé et refusé pour toute source externe, même
  désactivée. Template `hello-world`, titre `Hello World`, `kind: static` pour
  cette réponse fixe sans LLM ni données ; aucun moteur ReAct ou Graph annoncé.
  Sources externes et échec global conservés. Aucun raccordement UI ni changement
  SSE. Relecture du code seulement ; aucun build, test ou déploiement exécuté.
- 2026-10-24 : Dimi choisit une bibliothèque dans `apps/control-plane/agent/`,
  versionnée et liée au control-plane, pour garder un seul processus/déploiement.
- Conversion du serveur autonome en bibliothèque ; route du control-plane
  `POST /control-plane/v1/agents/execute/stream`, admission via `AdmittedUser`,
  extraction/erreurs JSON communes, enregistrement OpenAPI commun. La route sert
  seulement `hello-world` ; aucune donnée métier, instance gérée ou connexion LLM.
- Flux Fred `status`, deux `assistant_delta`, puis `final`, sans sentinelle.
  Aucun producteur détaché ni connexion SQL conservée pendant le flux.
- Cargo.lock actualisé hors ligne (une dépendance locale ajoutée), Dockerfile
  adapté pour embarquer les sources. Serveur TLS et Makefile autonomes supprimés.
- Documentation locale : `apps/control-plane/agent/README.md`, README du composant
  et carte des sources. Pas de parcours frontend ajouté. Le dossier arc42 reste
  dans son périmètre validé ; raccordement agent à y reporter après validation.
- Validation : relecture seulement ; aucun build, test ou déploiement lancé.
  OpenAPI/client générés non régénérés (la génération compile le binaire).
- Prochaine étape : compilation et appel manuel du hello-world par Dimi ; vérifier
  le flux via le proxy HTTPS du déploiement avant de brancher un modèle.
- 2026-10-24 : priorité recentrée par Dimi sur le cas d'usage simple : un éditeur
  supprime un document d'un dossier, nettoyé de bout en bout par les workers du
  Control Plane et de Knowledge Flow. Nouveau découpage : D1 `DELETE /documents/{id}`
  (backend), D2 frontend, D3 validation k3d et passe arc42 avec Dimi. Reportés :
  suppression d'un espace avec documents (ancien P3b : arrêt forcé, uploads en
  cours), dossier avec contenu (P4), utilisateur (P5). Simplifications proposées
  pour D1 : 409 `processing_active` pendant un traitement, rétention héritée de
  l'espace, `GET /deletions` inchangé.


- 2026-10-24 : déploiement secondaire interrompu pendant la compilation frontend
  du lot A. Correction ciblée dans `FeaturesPage.tsx` : narrowing numérique de
  `suspended_instances` sur la réponse Rust/legacy, et ajout de `defaultOn` aux
  identifiants de colonnes autorisés. Aucun élément UI modifié ou supprimé.
  Changements préexistants préservés. Aucun test, build ou déploiement relancé ;
  validation attendue lors de la prochaine exécution par Dimi.

## F-013 Synthese organisationnelle en lecture

2026-10-24 : évaluation demandée par Dimi, sans UI, nouveau service, accès physique
S3/OpenSearch, cache, worker ou table. Base lue : `4b19b48ab` ; branche `weaver`,
13 commits devant la référence distante locale, arbre propre au début de cette
évaluation. Cette fiche est le support unique de cadrage avant décisions ; toutes
les propositions ci-dessous restent non validées. Aucun code implémenté.

### Faits vérifiés par lecture

- `domain.rs`, `db.rs`, `spaces.rs` : organisation > équipe > projet. Un espace
  personnel est un `team` avec `personal_owner`, sans parent ni projet, rattaché
  par `organization_id`. Le chemin de recherche contient les ancêtres : il ne
  permet pas de sélectionner les descendants d'une équipe.
- `roles.rs` et `openfga/model.fga` : `can_own_organization` ne dépend que de
  `organization_owner`. Ni admin, ni rôle plateforme ne donne cette permission.
  Aujourd'hui son usage documenté est la désignation des administrateurs : lui
  ajouter les agrégats techniques est une extension à valider, sans droit contenu.
- `documents/reads.rs::usage` distingue octets du seul espace et consommation du
  propriétaire de quota. `Storage::quota` rattache les projets au quota équipe,
  mais sépare organisation et personnel. Les originaux sont comptés en SQL ; les
  réservations d'uploads et les dérivés ne sont pas des documents stockés.
- `processing/store.rs::summaries` sélectionne la dernière tentative par
  `(created_at,id)`. `preview.rs` sélectionne séparément le succès. La migration
  0001 garantit au plus une tentative active et un succès par document ; les
  états terminaux et manifestes sont immuables. `admit` refuse toute nouvelle
  tentative après succès (`processing_exists`) : retraiter un succès puis échouer
  n'est pas un parcours actuellement disponible. Ne pas le créer dans ce lot.
- `publication.rs` copie les compteurs du manifeste final dans la ligne réussie.
  Les générations intermédiaires/abandonnées et leurs réservations ne sont pas
  des publications à additionner. `processing/cleanup.rs` protège la génération
  publiée d'un document actif, puis nettoie les générations du document retiré.
- Knowledge Flow `manager_processing/service.py::_commit` publie actuellement
  `chunks=vectors=count` (ordinaux écrits), distinct du nombre de fragments issus
  de l'extraction. Un pointeur tabulaire peut être un chunk/vecteur. Cela ne mesure
  ni la disponibilité actuelle de l'index ni son contenu physique.
- `LocalTabularArtifacts.put_file` produit `datasets/<hash>.parquet` ;
  `TabularProcessor` écrit un artefact par document et transmet son `row_count`
  via les métadonnées au `Manifest.rows` SQL. Le manifeste contient chemins,
  tailles et empreintes, pas un nombre de lignes par artefact. Plusieurs Parquet
  dans un manifeste ne permettraient pas d'attribuer `rows` à chacun sans autre
  contrat. Un nom CSV n'est pas une preuve de publication tabulaire.
- Les lectures actives utilisent `space.deletion_id IS NULL` et
  `document.deletion_id IS NULL`. La fiche F-012 et A9 décrivent la suppression
  document implémentée ; le chapitre 05 dit encore qu'elle est indisponible.
  Cet écart est signalé, pas corrigé dans ce cadrage.
- `fga.rs::read_keys` draine les pages Read en HIGHER_CONSISTENCY et rejette un
  curseur immédiatement répété. `roles_of` est par utilisateur, `space_holders`
  par espace/rôle. `children_of` borne la concurrence à 8. Ne pas utiliser les
  premières pages de `references` comme inventaire exhaustif des rôles.
- Routes réutilisables comme patrons : résumé de stockage, `GET /admin/teams`
  (UUID, 100 lignes), `GET /admin/organizations` (101 lignes pour détecter la suite).
  Leurs permissions plateforme/contenu ne conviennent pas à cette nouvelle vue.
  Aucune route de synthèse organisationnelle existante identifiée. Le change
  `add-knowledge-base-pod-metrics` exclut explicitement ces statistiques métier.

### Dictionnaire proposé, à valider

Périmètre actif commun : espaces SQL de l'organisation, non retirés ; documents
non retirés. Trois compartiments disjoints : organisation directe, équipes avec
projets, personnel agrégé. Les valeurs SQL sont celles d'une transaction courte
REPEATABLE READ READ ONLY, terminée avant les lectures réseau OpenFGA.

| Compteur | Définition et source canonique | Exclusions, fraîcheur et limites | Réutilisation |
| --- | --- | --- | --- |
| Equipes actives | COUNT space de type team, personal_owner nul, organisation exacte | Personnel, projets et espaces retirés exclus ; état SQL | Filtre team_registry, placement SpaceRow |
| Documents / octets originaux | COUNT document, SUM(size) par compartiment/équipe | Uploads pending, dérivés et retirés exclus ; zéro si ensemble vide ; pas une mesure S3 | Prédicats Storage::usage, agrégation groupée à ajouter |
| Documents en attente de purge / octets logiques | Lignes document encore présentes avec deletion_id non nul, ou espace retiré | Bloc séparé, jamais ajouté à l'actif ; ne mesure pas les objets restant physiquement ni les reçus terminés | Marqueurs F-012, jointure space/document ; pas SUM des reçus |
| Traitements pending/running par étape | Dernière tentative par document actif, GROUP BY status,stage | Documents sans tentative exclus ; état enregistré, pas santé live du worker | Ordre de store::summaries et enums ProcessingStatus/Stage |
| Documents en échec | Dernière tentative failed par document actif | Echecs historiques remplacés par une relance exclus ; pas de somme des tentatives | Même sélection distinct on(document_id) |
| Documents publiés / chunks publiés / vecteurs publiés | Ligne succeeded et manifeste final du document actif ; SUM des colonnes chunks/vectors | Ni générations ni vecteurs physiques ; publication indépendante du dernier état ; documents sans succès exclus | Sélection preview, contrat publication, index unique success |
| Jeux tabulaires publiés | Nombre de chemins datasets/*.parquet du manifeste réussi | Pas COUNT des CSV ; aucun catalogue/table SQL créé ; nommer la mesure comme artefacts publiés | Convention LocalTabularArtifacts et Manifest.artifacts en JSONB |
| Lignes tabulaires connues / inconnues | SUM(rows) pour un document publié ayant exactement un Parquet et rows non nul ; compter séparément les jeux sans compte attribuable | Plusieurs Parquet : lignes non attribuables, inconnues ; rows nul n'est pas zéro ; zéro connu est conservé ; total nullable si couverture incomplète | Manifest.rows et artifacts ; ne pas ouvrir metadata.json/S3 |
| Utilisateurs distincts / attributions par rôle | Union des sujets user des grants directs des espaces actifs ; attributions = tuples (sujet,espace,rôle) | Dédupliquer les personnes globalement ; ne pas sommer les colonnes ni les équipes ; pas un annuaire de comptes IdP actifs ; aucun nom/ID utilisateur retourné | read_keys, Role::parse, ensembles locaux à la requête |

Les totaux d'utilisateurs incluent les rôles directs organisationnels et les
espaces personnels ; une ligne équipe inclut uniquement les attributions directes
sur cette équipe et ses projets, pas des droits hérités supposés. Les six rôles
existants restent distingués, y compris organization_owner et personal_space_creator.
Le rôle member fixe du propriétaire personnel se compte depuis FGA, pas depuis
personal_owner. Les droits effectifs ne sont pas recalculés à partir de Role::descends.

### Décisions demandées et recommandation

1. Autoriser uniquement OwnOrganization sur l'organisation cible, après admission,
   contexte unique et cycle de vie. Cumul de rôles accepté seulement si owner présent.
2. Inclure les projets dans la ligne équipe ; cohérent avec le propriétaire de quota.
3. Exposer organization_direct, teams_total, personal_total sans détail personnel ;
   total organisation indépendant de la page. Les sommes de personnes ne sont pas additives.
4. Séparer les documents retirés dans pending_purge, y compris les espaces retirés,
   avec sous-compartiments organisation/équipes/personnel, sans détail nominatif.
5. Compter les documents dont la dernière tentative a échoué, sans historique d'échecs.
6. Livrer les rôles directs seulement. Un inventaire exhaustif des effectifs évalués
   par FGA exige un contrat et un chemin de lecture supplémentaire ; aucun helper
   existant identifié ne le fournit sans interrogation par utilisateur.
7. Toute indisponibilité FGA : 503 dependency_unavailable, sans données partielles
   ni faux zéros, même si la panne survient après le Check d'autorisation.
8. Réutiliser l'admission inchangée en acceptant son effet existant : AdmittedUser
   appelle users::snapshot, qui peut rafraîchir user_identity en annuaire local
   (et son cache existant). Le module de synthèse ne ferait aucune écriture.
   Si l'exigence zéro écriture couvre aussi l'admission, décider une adaptation
   ciblée de l'admission commune avant le code ; ne pas la contourner silencieusement.
9. Garder le retraitement après succès hors périmètre ; préparer le cas de refus
   actuel et tester séparément la sélection publication/dernier état avec une
   fixture contrôlée si Dimi valide ce scénario de contrat, sans modification de données réelles.

### Contrat et coût proposés

- GET /organizations/{organization_id}/supervision : compteurs organisationnels,
  compartiments et page d'équipes, tri UUID ascendant, after et taille fixe 100,
  next_cursor explicite par lecture de 101 lignes. GET du même préfixe
  /teams/{team_id} : une équipe non personnelle et ses projets. Aucun document,
  chemin d'artefact, identité utilisateur ou téléchargement dans la réponse.
- Admission existante, 404 hors contexte/équipe étrangère, 403 sans owner dans
  le contexte, 409 espace retiré/contexte ambigu, 503 dépendance indisponible.
  Conserver ErrorBody et les extracteurs ApiPath/ApiQuery ; ni exception root
  ni Permission::Read requise pour les agrégats techniques autorisés.
- Plan SQL à concrétiser : 3 SELECT de garde (espace cible, organisation du
  demandeur à partir des tuples, état lifecycle), puis 3 SELECT métier : périmètre
  des espaces, page/identité équipe, agrégats groupés document/dernier traitement/
  publication. Au détail, vérifier aussi l'organisation et le type de la cible.
  Réutiliser les contrôles sans les contourner ; le décompte exact final dépendra
  du branchement retenu. Commandes BEGIN/SET/COMMIT et admission à compter séparément.
  Préagréger les artefacts JSON avant jointure pour ne pas multiplier les documents.
  Totaux calculés avant application du curseur, aucun SELECT par document.
- FGA recommandé : P_actor pages Read (roles_of pour contexte) + 1 Check
  can_own_organization + somme(P_s) pages Read, filtre object=space:<id>, pour
  chaque espace actif s du périmètre. Lire toutes les relations d'un espace en
  une chaîne paginée, filtrer les rôles typés ; petit helper dans Fga réutilisant
  read_keys, plutôt que six appels space_holders ou un appel par personne.
  Reprendre la borne de concurrence existante 8 ; pages d'un même espace séquentielles.
  read_keys ne fixe pas page_size : ne pas inventer un nombre fixe de tuples/page.
- S espaces, D documents, H tentatives, A artefacts publiés, G grants directs,
  U utilisateurs distincts déterminent le coût. SQL agrège D/H/A dans le périmètre ;
  les lectures FGA sont O(S + pages de G), mémoire O(S+G+U) avec read_keys et les
  ensembles. La synthèse relit tous les espaces de l'organisation pour ses totaux,
  même si la page est petite. Aucun cache ni garantie de latence mesurée.
- Horodatages de début/fin de collecte ; pas d'instantané commun SQL/FGA, ni de
  garantie de pagination stable sous mutations concurrentes. Sur jeu stable,
  parcours UUID sans perte ni doublon ; création sous le curseur exige de recommencer.
  Ne jamais retourner un comptage tronqué en succès ; erreur plutôt que partiel.

### Acceptation à préparer après décisions

- O1/E1/projet et O2 sans équipe ; données O2 témoins dans chaque famille ;
  totaux O2 à zéro seulement si son organisation directe/personnel sont aussi vides.
- Owner autorisé, admin/plateforme/admin équipe seuls refusés par HTTP ; cumul
  avec owner autorisé ; autre organisation non divulguée ; espace retiré refusé.
- Un sujet avec plusieurs rôles et espaces : un distinct, plusieurs attributions ;
  rôles hérités non présentés comme directs ; personnel agrégé sans identités.
- Echec puis relance pending/running puis succès ; publication sélectionnée
  séparément du dernier état ; retraitement après succès refusé selon le code actuel.
- Suppression différée : retrait immédiat de l'actif, entrée pending_purge,
  disparition des lignes après purge sans prétendre mesurer S3/OpenSearch.
- Plus de 100 équipes et plusieurs pages de tuples FGA ; derniers éléments inclus,
  totaux identiques sur chaque page à données constantes ; panne intermédiaire = 503.
- Aucun traitement, zéro chunk, Parquet zéro ligne, rows nul, plusieurs Parquet :
  distinguer absence de publication, zéro connu et valeur inconnue.

Après validation, préparer un seul change OpenSpec pour ce nouveau contrat public
et son autorisation ; ne pas importer d'exigences des anciennes métriques Swift.
La fiche gardera les décisions et un lien, sans maintenir un deuxième contrat.
OpenAPI et RTK seront générés depuis les sources : make -C apps/control-plane
generate-openapi (compile Rust, autorisation explicite requise), puis le codegen
RTK existant de apps/frontend. Aucun fichier généré modifié manuellement.
Vérification actuelle : lecture seulement. Aucun test, build, lint, génération,
appel aux données déployées, délégation, commit ou push. Aucun parcours validé
par Dimi et aucune implémentation autorisée par cette évaluation.

### Préalable demandé : distinguer le type personnel

2026-10-24 : Dimi demande d'évaluer la correction du modèle avant la supervision,
avec priorité à la cohérence des permissions, rôles et données. Evaluation en
lecture ; le contrat de supervision ci-dessus reste non validé.

Constats : `SpaceKind` est partagé par SQL, réponses API, création générique,
filtre `AuthorizeScope.levels` et politiques de rétention. Le type `team` et
`personal_owner` discriminent actuellement le personnel dans les memberships,
quotas, registre, purge et `Fga::can_use_agent`. Ce dernier exige actuellement
Team même pour le personnel. La création personnelle accorde Member ET Editor
au propriétaire, pas seulement Member. Les tuples `space:<id>`, lien organization
sans parent et grants personnels peuvent être conservés ; aucune nouvelle matrice
de droits ni migration FGA n'est nécessaire pour changer le discriminant SQL.

Recommandation à valider : ajouter `SpaceKind::Personal` / `kind="personal"`
dans le modèle canonique, garder personal_owner comme identité, et faire garantir
par SQL l'équivalence type personnel/propriétaire présent et l'absence de parent
du personnel. Conserver organisation_id, UUID, documents, quota_owner, chemins et
tuples FGA. Pas de type dérivé uniquement dans la supervision : il laisserait
l'ambiguïté dans toutes les autres lectures.

Périmètre minimal identifié :
- domain/db/spaces : création personnelle dédiée, parcours et scopes, filtres
  collectifs explicites. La création générique doit refuser Personal ; ajouter
  la variante à l'enum partagé ne doit pas ouvrir un chemin de création avec
  admin arbitraire, sans propriétaire ou avec un lien parent.
- Documents : quota personnel inchangé ; rattachement des projets au quota équipe
  inchangé. Activation d'agents : accepter Team et Personal dans le helper en
  gardant exactement les contextes FGA actuels et leurs exceptions personnelles.
- Lifecycle : personnel toujours non supprimable seul ; purge via organisation
  conservée, y compris parcours des références orphelines et ordre de drainage.
  Ne pas inventer un reçu personnel pour satisfaire un match Rust exhaustif.
  Les règles de rétention document utilisent le type de l'espace : contrôler
  explicitement la compatibilité des sélecteurs team lors du changement de type.
- Migration nouvelle : convertir les lignes personnelles existantes, actives et
  retirées. `forbid_space_move` interdit aussi le changement de kind ; la migration
  doit organiser une exception strictement bornée à cette conversion puis conserver
  l'immuabilité. Migrations appliquées intouchées. Aucune migration exécutée,
  aucun historique SQL déployé ni donnée réelle inspectés ; sauvegarde et procédure
  de déploiement restent nécessaires avant toute application. Ancien binaire/client
  à trois variantes incompatible avec une réponse ou ligne Personal : pas de
  coexistence annoncée sans validation.
- API/UI : enum généré, fixtures personnelles et consommateurs des memberships,
  navigation, ressources et contexte personnel à aligner sans changement d'écran.
  Aucun renommage opportuniste des anciennes routes team ou relations FGA.
- Preuves ciblées à préparer : conversion préserve IDs/données/tuples, invariants
  SQL, refus création générique, absence héritage personnel, Member+Editor fixes,
  isolation organisations, quota, activation agents, purge organisationnelle,
  filtres de scope et UI conservée. Aucun test lancé.

Décisions avant code : valider Personal comme type canonique ; décider si
`levels=[team]` et les sélecteurs de rétention `space_kind: team` deviennent
strictement collectifs. Recommandation : oui, sans alias caché ; `personal` explicite
pour le personnel, scopes sans levels inchangés. Toute configuration existante
qui voulait couvrir les deux devra le déclarer explicitement. La configuration
de rétention fournie a rules: [], mais les installations externes ne sont pas
inspectées. Ces changements de sélection doivent être assumés dans le contrat,
pas présentés comme un renommage invisible.

Après décision, un seul change OpenSpec consacré à ce préalable (contrat public
et migration), sans commencer la supervision. Génération OpenAPI/client à prévoir
avec autorisation de compilation. Code, schéma, modèle FGA et UI inchangés à ce
stade ; seul ce journal est complété, aucune validation utilisateur déduite.

### Préalable personal : implémentation locale

2026-10-24 : Dimi valide `personal` et la séparation stricte des filtres, puis
demande l'implémentation directe sans OpenSpec. Arc42 explicitement différé.

- Type canonique ajouté ; création dédiée conservée, création générique refusée.
  Scopes, memberships, registre collectif, quotas, rôles fixes et activation agents
  utilisent le type. Modèle et tuples FGA inchangés ; aucun droit supplémentaire.
- Migrations 0010/0011 préparées : ajout de la valeur enum, puis conversion des
  espaces personnels actifs/retirés sous verrou SQL et contrainte type/propriétaire/
  absence de parent. Protection d'immuabilité rétablie dans la transaction.
  Aucune migration appliquée ni ancienne migration éditée.
- Suppression autonome personnelle toujours refusée via conversion typée de la
  cible ; purge organisationnelle et parcours des références conservés. Filtres
  `levels` et rétention stricts, sans alias team vers personal.
- Consommateurs Resources/navigation adaptés au discriminant, écrans et routes
  conservés. Fixtures et tests de contrat, scope, ouverture personnelle, rétention
  adaptés ; scénario de migration ajouté dans le fichier d'intégration existant
  pour préserver lignes actives/retirées et documents et vérifier les contraintes.
- README du composant précise les filtres et la compatibilité de migration.
  Relecture seulement ; aucun test, compilation, lint, génération, déploiement,
  commit ou push. Vérification fonctionnelle et migration restent non exécutées.
- OpenAPI/client restent à régénérer depuis les sources avec autorisation explicite
  de compiler. En attendant, le client à trois variantes est incompatible avec les
  nouveaux consommateurs TypeScript : ce lot n'est pas prêt au déploiement.
  Aucun fichier généré édité à la main. Définitions de supervision toujours en attente.

- Après le "go" explicite de Dimi : `make -C apps/control-plane generate-openapi`
  réussit, compilation Rust comprise. Puis, depuis `apps/frontend`,
  `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`
  réussit. OpenAPI expose les quatre types ; le seul changement du client généré
  est l'ajout de `personal` à `SpaceKind`, relu avec les consommateurs adaptés.
  Le blocage de génération ci-dessus est levé. Aucun test, lint, compilation
  TypeScript, migration ou déploiement exécuté ; validation fonctionnelle toujours
  attendue et arc42 toujours différé. Aucun commit ni push.

- Dimi lance les tests frontend et rapporte des échecs au rendu DocumentWorkspace :
  le mock commun `inactiveManagerFolders.test-support.ts` omet
  `useDeleteDocumentMutation`, appelé par le composant même dans les fixtures
  legacy. Hook ajouté au mock existant, comme les autres mutations inactives ;
  aucune assertion supprimée ni comportement applicatif modifié. Correction
  vérifiée par lecture seulement ; aucune relance de tests par l'assistant.

### Supervision : décisions validées et implémentation

2026-10-24 : après le préalable personal et le retour de Dimi indiquant que la
qualité frontend passe, reprise du lot initial. Dimi valide le lot : owner seul,
projets inclus, trois compartiments disjoints, purge séparée, dernière tentative
pour les échecs, rôles directs seulement, panne FGA = 503 sans résultat partiel,
admission existante conservée, retraitement après succès hors périmètre. Ces
choix remplacent le statut « proposé » des neuf décisions ci-dessus. Travail
direct dans le cadrage existant, sans nouveau document OpenSpec ; arc42 différé.

- Module `src/supervision` enregistré dans le routeur existant : résumé et détail
  d'équipe, contrats utoipa, extracteurs et admission communs, OwnOrganization
  évalué par FGA. Aucun nouveau droit de contenu ni exception plateforme.
- Agrégations SQL par espace ; dernier état distinct de la publication réussie,
  artefacts agrégés avant jointure, valeurs inconnues conservées. Transaction
  REPEATABLE READ READ ONLY fermée avant les lectures de rôles. Cycle de vie
  revérifié dans la transaction pour éviter des résultats actifs après un retrait
  intervenu entre la garde et la collecte. Aucun verrou supplémentaire.
- Helper FGA `grants_on` réutilisant read_keys/concurrently (8), puis déduplication
  des tuples et union des sujets. Comptages complets, aucun appel par utilisateur.
- Coût concret remplaçant l'estimation initiale : 8 SELECT résumé / 10 détail,
  hors admission, plus BEGIN/SET/COMMIT. FGA : P_actor Read + 1 Check + somme des
  pages de chaque espace actif. Les totaux ne dépendent pas de la page. Contrat,
  cardinalités, coût et limites documentés dans le README du composant.
- Trois scénarios d'intégration préparés dans organization_console : isolation
  O1/O2, owner et refus HTTP, personnel/projets, cumul de rôles et pages FGA ;
  102 équipes avec totaux constants ; tentative/publi indépendante, relance après
  échec, purge différée et lignes inconnues. Une histoire succès puis échec est
  une fixture SQL de sélection, pas un nouveau parcours d'ingestion. Registre
  OpenAPI attendu mis à jour. Aucun test exécuté.
- Relecture du code et des contrats seulement à ce stade. Dimi autorise ensuite
  explicitement la génération OpenAPI (compilation Rust comprise) et RTK ;
  génération en cours. Pas de lint, migration, accès aux données déployées,
  délégation, commit ou push. Validation utilisateur des parcours encore attendue.

- Génération autorisée terminée : `make -C apps/control-plane generate-openapi`
  réussit (compilation Rust incluse), puis le codegen RTK existant réussit. Client
  généré relu : deux routes/hooks, compteurs typés et total_rows nullable ; pas de
  modification manuelle du généré ni d'UI. Les retouches ultérieures ne portent
  que sur la présentation du Rust, sans changement de contrat.
  Trois tests d'intégration sont écrits mais ni compilés ni exécutés ; pas de lint.
  La génération ne valide pas les requêtes SQL dynamiques ni les parcours HTTP.
  Restent la validation ciblée par Dimi, les migrations personal à appliquer dans
  son environnement selon sa procédure, et la mise à jour arc42 différée.

### Arc42 : modèle personnel et supervision

2026-10-24 : Dimi autorise l'alignement arc42 et demande un état final, sans récit
progressif, avec premiers chapitres brefs et illustrés et annexes exploitables
pour revue de sécurité. Chapitres 03/04 : portée du rôle owner, distinction du
personnel et schéma des trois compartiments. Annexes A2/A7/A8 : contraintes SQL,
routes, matrice d'autorisation, divulgation, dictionnaire des compteurs et
limites de cohérence. Chapitre 09 : invariants concernés et coût source-dérivé.
Index de lecture relié au contrat. Aucune UI de supervision inventée.

Table des deux routes produite par la fonction existante du générateur documentaire,
sans compilation ni régénération globale. Relecture des changements et des sources ;
pas de test, lint, rendu Mermaid, make check, migration ou déploiement. Aucun code
applicatif modifié dans cette étape. Les références aux tests désignent des scénarios,
pas des résultats exécutés. Historique conservé dans ce journal uniquement.
Le README du composant renvoie désormais aux annexes pour le contrat et le coût,
sans recopier ces règles. Les autres sections et changements préexistants sont
conservés. Cette consolidation documentaire ne vaut pas validation fonctionnelle.

### Retour tests frontend : mock du pipeline

2026-10-24 : Dimi rapporte 395 fichiers réussis, 1 en échec et 1 ignoré ; les
quatre échecs concernent usePipelineRun au montage. Lecture du hook et du mock :
les deux lazy queries prompts/session sont appelées au montage mais absentes du
mock legacy. Ajout de ces deux exports à la liste de stubs existante dans
usePipelineRun.test.tsx. Aucun changement applicatif, généré ou d'assertion.
Correction relue, sans relance de tests, compilation ou lint par l'assistant.
Le résultat après correction reste à confirmer par Dimi.


### F-013 : vue de supervision organisationnelle, lot 2

2026-10-24 : Dimi valide la proposition UI : entrée avant Fonctionnalités dans
Administration, route /admin/supervision, panneau InlineDrawer pour le détail,
contrôle serveur partagé own_organization et exception de navigation pour le cumul
de rôles. Il demande un code minimal, partagé, avec en-têtes Apache-2.0 et layout
existant conservé. Les composants existants sont réutilisés sans refonte globale.

Implémentation locale : page, trois compartiments, totaux serveur, pagination UUID,
détail équipe, états de chargement/erreur/refus et traductions FR/EN. Présentation des
compteurs commune aux totaux, compartiments et détail ; rôle direct non confondu
avec utilisateur distinct, lignes inconnues non converties en zéro. Contexte issu
de /me/spaces et permission issue de /authorize/space, partagés entre menu et page.
Actualiser et retour au premier plan revérifient le contexte/l'autorisation ; les
requêtes de métriques reprennent ensuite, détail compris. Pas de polling ajouté ;
le polling du hook organisation admin est désactivé sur cette route. Client généré,
backend Rust, migrations et données inchangés. Les fichiers source nouveaux portent
l'en-tête Apache-2.0.

Vérification : relecture des sources et du diff uniquement. Branche weaver,
HEAD initial 1a53d36d3, arbre initial propre. Le contrat lot 1 et les annexes sont
cohérents par lecture ; présence de 0010/0011 ne prouve pas leur application.
Aucun test, build, lint, génération, requête déployée, migration, délégation, commit
ou push exécuté. L'application des migrations, le déploiement local et les tests
d'intégration restent non établis. La validation de la proposition UI n'est pas
une validation fonctionnelle de la vue implémentée.

Parcours manuel proposé sans préparation de données : o1owner/O1/E1 avec projets ;
o2owner/O2 sans équipe ; autres rôles refusés par menu et URL ; owner avec rôles
plateforme autorisé ; utilisateurs distincts non additionnés ; pagination sans
perte sur données stables ; actualisation résumé/détail après ingestion/suppression
par un utilisateur autorisé ; erreur réseau avec date inchangée et sans faux zéro ;
lignes inconnues distinguées de zéro ; changement de contexte sans anciennes
valeurs ; révocation détectée retirant l'accès et le détail. Retour de Dimi attendu.

Arc42 : 04 décrit la vue au présent, A8 contient le branchement frontend et ses
limites, A2 et l'index pointent vers cette explication. Aucun parcours présenté
comme validé, aucun résultat de test inféré.

2026-10-24 : composition compacte de supervision approuvée par Dimi, avec
répartition uniforme sur la largeur et adaptation aux petits écrans. Synthèse
unique, états sémantiques (zéro neutre), comparaison des trois compartiments,
tableau d'équipes sans hauteur fixe et détails/attributions repliables. Réutilisation
de PageHeader, DataTable en taille small, StatusBadge, Disclosure et InlineDrawer ;
aucun composant partagé modifié. Correctif local de révocation, requêtes, cache,
rafraîchissement et curseurs conservés. Traductions FR/EN complétées.
Vérification par lecture du code et du diff uniquement ; l'instance k3d sert une
image frontend sans montage des sources, donc les changements locaux ne sont pas
visuellement validés. Aucun test, quality, build, déploiement, commit ou push lancé.

2026-10-24 : essai manuel de suppression bloqué par un 503 à 19:44, avec
`scheduler.lifecycle.enabled=false` dans la configuration k3d déployée. Les trois
documents sont restés présents, sans marqueur de purge. Sur demande de Dimi,
le message devient `document deletion is disabled by configuration` et le profil
k3d active lifecycle. Les deux clés scheduler du profil sont réunies pour conserver
ensemble lifecycle et processing. Relecture du diff uniquement ; aucun test, build
ou déploiement exécuté. Redéploiement et nouvel essai à effectuer par Dimi.

Sur demande de Dimi, la rétention par défaut du seul profil k3d passe à PT1M.
Le délai de balayage reste inchangé ; une minute rend la purge éligible mais ne
garantit pas son achèvement à la seconde près. Aucun déploiement exécuté.


## REL-1 Génération Weaver 5.0.0

- 2026-10-25 : décision de Dimi de conserver les noms de packages et de démarrer
  toutes les distributions Weaver en 5.0.0 ; Swift conserve ses lignes actuelles.
  Applications Python/frontend, crates Rust, quatre bibliothèques Python, neuf
  packages de capabilities, trois bibliothèques npm, charts et versions par défaut
  des images alignés. Workspace npm et harnais de validation alignés également.
- Dépendances internes Python bornées à `>=5.0.0,<6`, peer dependency UI/tokens à
  `^5.0.0`. Lockfiles ajustés mécaniquement pour les coordonnées locales, sans
  résolution ni changement des dépendances tierces. Ralph expose la version de
  sa crate via `CARGO_PKG_VERSION`.
- Versions de schéma des manifests capabilities, protocoles/API, migrations,
  fixtures synthétiques et preuves de publications historiques conservées.
  Aucun changement des règles OpenFGA ou de l'admission runtime dans ce lot.
- Politique de versions actualisée. Avant publication : adapter les helpers Python
  (bornes et maintenance d'une ancienne majeure), le contrat npm encore lié à
  Swift, les tags/branches de publication et les bornes côté Swift. Aucun accord
  historique de publication réutilisé pour Weaver.
- Modifications préexistantes du lot k3d conservées. Relecture du diff seulement ;
  aucun test, build, régénération OpenAPI, déploiement, tag, publication, commit ou
  push exécuté. Le numéro 5.0.0 ne vaut pas validation fonctionnelle de Weaver.


## SEC-1 Invariants de sécurité Weaver

- 2026-10-25 : Dimi réaffirme que Weaver ne doit jamais s'écarter du modèle de
  sécurité Swift. La refonte simplifie le modèle ReBAC et concentre les contrôles,
  sans sacrifier identité, admission, isolation, délégation, renouvellement des
  credentials, révocation ou fin de vie des runs. Section normative ajoutée dans
  `AGENTS.md`, avec renvoi depuis `CLAUDE.md`.
- Direction : permissions documentaires portées par les espaces, sans tuples par
  document ; disparition de Knowledge Flow API, recherche vectorielle et lectures
  via les capacités locales du pod agent. L'accès direct au stockage reste soumis
  aux contrôles d'autorisation partagés. Cette direction n'est pas une preuve
  d'implémentation ou de validation du parcours.
- Le scénario initial à cadrer est Bob dans fredlab, organisation TSN, avec des
  capacités locales uniquement. La généralisation des appels REST d'autorisation,
  un mode catalogue séparé, un nouveau grant signé et les détails de la réponse
  de contexte ne sont pas des décisions acceptées. La distinction entre personne
  et service et les mécanismes de renouvellement doivent être préservés.
- Pour chaque garantie affectée : identifier son contrôle Swift, son application
  Weaver et la preuve à apporter. Un équivalent manquant reste une question de
  contrat, sans contournement implicite. Aucune conclusion d'homologation CVSSI
  ne découle de cette clarification.
- Modification des consignes et du journal uniquement pour ce lot ; changements
  locaux précédents conservés. Aucun code applicatif modifié, test, build,
  déploiement, commit ou publication exécuté.

- 2026-10-25, suite du cadrage SEC-1 : décisions validées par Dimi :
  `can_read` sur l'espace d'exécution et `can_use` de cet espace sur le template ;
  consommation locale du binding PG/OpenFGA canonique en lecture seule ; contrôle
  à l'entrée puis avant chaque opération protégée, sans cache inter-opérations ni
  contrôle par token SSE ; renouvellement JWT conservé indépendamment des droits.
- Portée documentaire confirmée : espace et ancêtres, sans `can_read` supplémentaire
  sur les ancêtres ; fredlab inclut TSN, un projet inclut équipe et organisation,
  aucun descendant/frère ajouté, espace personnel isolé. Aucun tuple par document.
- Dimi exclut explicitement toute rétrocompatibilité Weaver/Swift : aucun mode,
  alias ou fallback ; migration séparée, remplacement et suppression du code
  obsolète, simplicité et réduction du code de production prioritaires.
- OpenSpec de planification créé :
  `openspec/changes/simplify-weaver-runtime-authorization/` (proposition, conception,
  exigences et lots conditionnels). Les anciens changes centrés sur KF/tags ne
  constituent pas le contrat Weaver. Aucun code de production modifié dans ce lot.
- Trois prérequis restent visibles avant exécution gérée : correspondance du
  contrôle Swift de compte actif avec la révocation/admission Weaver ; source et
  contrat Rust des faits instance/conversation ; disponibilité/autorisation des
  capacités et modèles du template. La relation Swift `suspended` absente ne prouve
  pas qu'une nouvelle fonction de suspension est nécessaire : comparaison à faire,
  sans supprimer implicitement la garantie. Dimi a demandé une explication de ce
  point ; aucune décision de suppression ou de nouveau mécanisme n'est acquise.
- Recherche locale proposée : filtre de portée et vérification SQL groupée des
  publications/cycles de vie ; exclusion conservatrice pendant changement
  d'inclusion à confirmer. L'exécution d'agents en projet reste distincte de la
  portée documentaire, le helper Rust actuel acceptant équipe/personnel seulement.
- Changements utilisateur précédents préservés. Aucun test, build, déploiement,
  commit, push ni validation dynamique exécuté. Planification ne vaut pas accord
  d'implémentation ni preuve de réduction effective du code.

- 2026-10-25, arbitrage suivant de Dimi : aucun besoin de suspension réversible
  ni de restauration de l'ancien contexte de Bob ; un retour suit l'admission
  d'un nouvel arrivant. Quelques minutes d'activité déjà engagée après révocation
  sont acceptables, avec arrêt/nettoyage rapide. Consignes et OpenSpec actualisés.
  Les contrôles avant opération restent acquis ; la borne chiffrée et son
  application aux runs/délégations restent à préciser. Aucune assimilation entre
  nettoyage des accès/runtime et purge des documents, historiques ou audits.
  Planification uniquement, sans modification de code ni validation dynamique.

- 2026-10-25 : Dimi valide une borne maximale de cinq minutes après révocation
  effective des accès pour les activités déjà engagées et la fin d'autorité des
  runs/délégations concernés. Consignes et OpenSpec alignés ; le mécanisme qui
  garantit cette borne reste à préciser, notamment sans nouvel appel d'outil.
  Le renouvellement des tokens de service ne doit pas prolonger cette autorité.
  Aucun code de production ni validation dynamique dans cette mise à jour.

- 2026-10-25 : Dimi délègue la proposition du contexte minimal et exige de conserver
  des logs/KPI riches filtrables par organisation, équipe et projet. Conception
  précisée : resolver demandé par espace/instance, réponse sujet + placement
  canonique + binding/configuration agent ; session/run/trace restent au runtime,
  qui conserve le contrôle d'appartenance conversation/checkpoint. Aucun second
  stockage de conversation côté Rust ni liste de permissions dans le contexte.
  Projection centrale du même contexte vers logs/KPI existants, dimensions
  organisation/équipe/projet stables, isolation concurrente, attribution terminale.
  Les dimensions produit ne sont pas ajoutées implicitement aux labels Prometheus.
  Route/source d'instance Rust et mécanisme de borne à cinq minutes restent à
  préciser. Proposition documentaire uniquement, sans validation dynamique.

- 2026-10-25 : Dimi valide le contexte canonique minimal puis la règle de
  dépendances : l'activation du template autorise ses capacités/modèles configurés,
  sans catalogue ReBAC distinct ; disponibilité et restrictions de données restent
  vérifiées. Registre, configuration, routage des modèles, clients et renouvellement
  Swift conservés ; aucun élargissement vers leur refonte ou les autres capacités.
- OpenSpec `simplify-weaver-runtime-authorization` réconcilié en quatre lots :
  consommateur Python Weaver ; contexte/run/dépendances/observabilité ; accès
  documentaire local ; configuration et remise à Dimi. Suppressions dans chaque
  lot, sans lot général de nettoyage ni mode compatible. La source d'instance Rust
  et la garantie technique des cinq minutes restent à établir au début du lot 2,
  sans rouvrir les règles métier validées ni élargir implicitement le périmètre.
- Documentation uniquement dans cette mise à jour (OpenSpec et journal).
  Aucun code, configuration de déploiement, test ni fichier généré modifié ;
  aucun test, build, déploiement, commit, push ou validation dynamique exécuté.


- 2026-10-25, arbitrage de périmètre après inventaire des règles Swift : Dimi
  confirme que toutes les fonctions d'admission globale restent nécessaires,
  mais reporte leur portage à un lot ultérieur. Le prochain lot traite le socle
  ReBAC Weaver ; le filtrage global récent n'en est pas un prérequis.
- Le report couvre la politique sur attributs d'identité (allow/block, all/any),
  les exceptions individuelles, l'admission des gestionnaires d'accès, les équipes
  autorisées et les adhésions par liens Free, avec leurs contrôles sur la personne
  déléguée. Ce besoin est conservé, pas abandonné ni remplacé par la seule règle
  « appartenir à une organisation ». Le détail du séquencement est consigné dans
  la décision 2a du change simplify-weaver-runtime-authorization.
- Identité/JWT, distinction personne-service, délégation, CGU, droits sur les
  espaces/templates et cycle de vie restent dans leurs périmètres de sécurité
  acquis. Les décisions antérieures sur le départ sans restauration automatique
  et la borne de cinq minutes restent inchangées ; « tout » ne réintroduit pas
  la suspension réversible écartée précédemment.
- Aucun mode catalogue, refus temporaire des autres fonctions, fallback Swift ou
  politique d'admission de substitution à ajouter pour attendre ce portage.
  Le découpage précédent qui imposait le filtrage complet avant le socle ReBAC
  est remplacé par cette décision. Elle ne prouve ni démarrage opérationnel ni
  équivalence complète avec l'admission Swift.
- Traçabilité documentaire uniquement : aucun code, test, build, génération,
  déploiement, commit ou push dans cette mise à jour.


### SEC-1 : remise au vert des tests locaux (2026-10-25)

- À la demande de Dimi, réparation des tests après le passage du pod au socle
  Weaver : fixtures de démarrage hors ligne, attentes CGU/permissions à jour,
  isolation des contextes globaux, reprise après crash et fermeture des ressources.
- Les vérifications existantes de démarrage sont regroupées dans
  `fred_runtime.app.security.prepare_authorization`, avec accord explicite de Dimi
  pour modifier le code de production. Les règles C3, PostgreSQL et OpenFGA sont
  conservées et testées séparément des fixtures de routes ; tests dédiés des CGU.
- Contrat OpenAPI du resolver runtime et schémas générés du control-plane/chart
  remis en cohérence avec les changements déjà présents.
- `make test` à la racine réussi sur les 17 sous-modules, dont 2 263 tests runtime
  et 134 tests fred-agents. Qualité runtime et fred-agents réussie ; cinq
  avertissements de typage préexistants côté runtime. Contrôle de dérive des
  schémas de chart réussi. Les skips/xfails et avertissements restants sont
  conservés ; aucun test d'intégration ou parcours déployé validé par ce lot.
- Aucun commit, push ou déploiement. Cette vérification technique ne clôt pas
  les lots fonctionnels Weaver ni la validation des parcours par Dimi.


## F23 Stockage des instances d'agents

- 2026-10-25 : premier sous-incrément demandé de la tâche 1.1 du change
  `simplify-weaver-runtime-authorization`. Migration additive `0012_agent_instances.sql`
  et module Rust `agent_instances.rs` : création, relecture espace/UUID et liste par
  espace. Identités, métadonnées, attribution et dates conservées ; tuning JSON
  complet et opaque, dont enveloppes de capacités et distinction null / [].
  Noms sans espaces de bord, unicité insensible à la casse dans chaque espace.
- Pas de route, validation métier, autorisation ou exécution ajoutée. La couche
  appelante doit fournir le contexte canonique et un tuning déjà validé. Tâche 1.1
  laissée décochée ; API et autres mutations restent à réaliser dans un autre pas.
- Décision restante consignée dans le design : FK d'espace sans cascade, donc purge
  physique refusée tant qu'une instance le référence. Le worker actuel peut déjà
  avoir purgé documents/dossiers et références FGA avant cet échec, puis réessayer.
  Définir la rétention/suppression des instances et l'ordre d'admission/purge avant
  de raccorder ce stockage au cycle de vie des espaces ; aucun worker modifié ici.
- Relecture statique seulement. Migration non appliquée ; aucun test, build,
  contrôle qualité, déploiement, commit ou push. Modifications préexistantes
  préservées. Aucun parcours agent intégré/validé ajouté à arc42 ; documentation
  architecturale à reprendre lors de l'intégration validée, conformément à sa limite.


## F24 Catalogue des templates par espace

- 2026-10-25 : Dimi accepte F23 en revue statique et demande uniquement la route
  `GET /spaces/{space_id}/agent-templates`. La suppression d'un espace contenant des
  instances reste hors de ce pas et à résoudre avant toute création exposée.
- `agents.rs` : admission existante, lecture de l'espace avec contrôle de cycle de
  vie, types équipe/personnel seulement, puis découverte publique et `can_use_agent`
  par identité canonique organisation/runtime/template. Huit checks simultanés au
  maximum ; erreurs propagées et aucune transaction SQL pendant ces appels réseau.
- Projection Swift dédiée : champs complets, défauts et traductions, capacités
  annoncées et sélection par défaut, sans schémas internes ni FGA de capacités.
  Visibilité publique et exclusion des entrées d'application conservées. Ralph
  n'est pas proposé à la création : son runtime refuse déjà les instances gérées.
- Route/réponse inscrites à l'OpenAPI Rust ; aucun consommateur ou client frontend
  généré modifié. Relecture statique seulement, aucun test, build, génération,
  migration, déploiement, commit ou push. Tâche 1.1 toujours décochée.
- Vérifications proposées : espace autorisé, espace étranger/retiré, template
  désactivé, conservation exacte de `prompts.system`, des défauts localisés et des
  capacités déclarées. Aucun parcours agent validé ni élargissement d'arc42 déduit
  de la présence au catalogue. Modifications préexistantes conservées.


## F25 Création et relecture d'une instance Custom

- 2026-10-25 : deux routes POST/GET et contrats OpenAPI ajoutés à partir des
  contrats Swift. Stockage existant réutilisé ; découverte configurée, UUID
  canoniques, auteur authentifié et copie complète du tuning du pod. Validation
  locale des seules valeurs soumises, sans défauts injectés ni obligation de
  formulaire ajoutée. GET limité à espace/instance et à la configuration stockée.
- Admission, espace équipe/personnel actif, écriture/lecture et can_use_agent ;
  découverte hors transaction puis revérification sous verrou/fence existants.
  Conflit de nom 409 agent_name_conflict. Capacités effectives vides uniquement,
  persistées en [] ; outil actif ou profil recommandé non nul refusés en 422.
- OpenSpec actualisé, tâches 1.1/1.2 toujours décochées. Aucun changement Python,
  frontend, migration ou autre route. Aucune disponibilité d'exécution déduite.
  Relecture de sources seulement ; ni tests, build, migration, déploiement,
  génération client, commit ou push. Arc42 reste dans sa limite validée.
- À vérifier par Dimi : prompt personnalisé relu à l'identique, défauts,
  nom en conflit, espace/instance étrangers, espace retiré pendant découverte,
  refus d'un outil/profil non raccordé. Prochaine étape après cette validation.
- 2026-10-25 : ajout ciblé de PATCH sur la même instance, contrat OpenAPI et UPDATE
  RETURNING. Métadonnées omises/null conservées ; tuning omis conservé, null/{}
  vidé, objet remplacé après validation existante. Le tuning stocké et ses clés
  inconnues sont conservés ; seules les FieldSpecs sont actualisées à l'édition
  tuning/capacités. Repli sur les champs sauvegardés uniquement pour le tuning,
  jamais sur un refus d'accès ; catalogue obligatoire pour les capacités.
  Relecture sous les verrous existants après découverte, autorisation/lifecycle
  revérifiés et fence avant écriture. PATCH sans effet conserve updated_at/by.
  Renommage indépendant du rôle/prompt ; status gère activation/désactivation.
  Capacités actives et recommandations non nulles restent refusées en 422.
  OpenSpec précisée, 1.1/1.2 décochées ; arc42 reste dans sa limite validée.
  Sources relues uniquement, aucune commande de test/build/migration/déploiement
  ni génération client/commit. Parcours UI non validé. À vérifier par Dimi :
  édition/relecture du prompt, omission/null/{}, renommage, status, absence d'effet,
  conflit de nom, espace étranger/retiré, concurrence et réglages non raccordés.
- 2026-10-25, étape 6 : DELETE de la configuration par espace et UUID, avec 204
  sans corps ou 404 si absente/étrangère, y compris à la seconde suppression.
  Admission, espace équipe/personnel actif et Write revérifiés sous lock_for,
  authorize_locked et fence existants, puis commit. Pas de contrôle can_use_agent :
  Write conservé permet de retirer une instance même si son template est révoqué.
  Nom libéré ; état activé/désactivé indifférent. Catalogue, runtime, historique et
  purge d'espace inchangés ; métadonnées de session/dernier nom à leur intégration.
  Contrat et vérifications proposées dans l'OpenSpec (décision 1f), 1.1/1.2 décochées.
  Relecture statique seulement, aucune validation dynamique ni commande de test,
  build, migration, génération client, déploiement ou commit. Arc42 inchangé.
- 2026-10-25, étape 7 : GET de la liste par espace et contrat OpenAPI ajoutés dans
  agent_instances/http.rs uniquement en production. list_by_space et record_to_summary
  réutilisés : projection sauvegardée identique au GET individuel, ordre created_at
  puis agent_instance_id, instances activées/désactivées, [] si aucune visible.
  Admission, espace canonique actif équipe/personnel et Read, puis can_use_agent une
  fois par template distinct, avec la borne READ_CONCURRENCY existante. Refus omis ;
  erreurs FGA, SQL et de projection autorisée propagées sans succès partiel.
  Aucun verrou/transaction, connexion SQL retenue pendant FGA, appel catalogue/runtime
  ou rafraîchissement des FieldSpecs. enabled n'atteste aucune disponibilité d'exécution.
  DELETE inchangé : Write permet toujours la suppression après révocation du template,
  sans exception de visibilité ni nouveau statut. Modifications préexistantes préservées.
  OpenSpec actualisée (décision 1g), 1.1/1.2 décochées ; UI et validation restent à faire.
  Prochain jalon : tests ciblés, leur inventaire OpenAPI et campagne listés dans tasks.md.
  Relecture statique seule ; aucun test, build, migration, déploiement, génération client,
  commit ou push. Arc42 reste dans son périmètre validé.

- 2026-10-25, jalon de validation 1-7 demandé : sept groupes d'intégration
  PostgreSQL/OpenFGA passent (CRUD, tuning, autorisations/concurrence, migration
  additive et purge). Correction du refus des capacités fixes filtrées du catalogue
  à la création ; revue indépendante et assertions OpenAPI nullable/optionnel.
  Tests hors ligne (55 + 12), qualité Rust du checkout, Temporal, génération du
  client Control Plane, qualité/tests/build frontend et contrôle d'architecture
  réussis. Frontend : 4 878 tests passants, 8 ignorés. Générateur SQL documentaire
  corrigé pour une transaction par migration, sans modifier les migrations.
- Validation globale bloquée : trois assertions historiques de budget FGA en purge
  échouent, identiquement sur le HEAD propre 6cea52adf (39/33, 16/13, 7/6 lectures).
  Assertions conservées. Le HEAD propre échoue aussi à rustfmt ; les corrections
  de formatage locales préexistantes restent exclues du commit ciblé. Après retrait
  de l'interception 503 erronée du Control Plane dans le harnais navigateur, le
  parcours attend les CGU et reste sur « Fred is starting... » ; non validé.
- k3d secondaire confirmé (k3d-fred-secondary / fred), migrations 1-11 réussies,
  composants Control Plane/KF worker/frontend prêts, fred-agents absent. Lint/rendu
  factory réussi avec les anciennes images ; aucun upgrade. La sauvegarde préalable
  a été refusée par le contrôle automatique pour copie locale de données sensibles ;
  confirmation demandée. Migration 0012 déployée, droits API et ingestion dédiée
  restent en attente. Pas de push de jalon validé, pas de PR, pas de raccordement
  fred-agent. OpenSpec 1.1/1.2 restent décochées ; change non archivé.
- Vérification de reproductibilité : la sélection ciblée appliquée au HEAD propre
  compile et passe ses 55 tests unitaires, 12 contrats OpenAPI et sept groupes
  d'intégration. Le client régénéré est identique sans les versions locales exclues.
  Clippy passe ; rustfmt retrouve les seuls écarts préexistants. Le rendu k3d de
  cette sélection passe avec les images du chart, sans build ni déploiement.
  Un commit local conserve le lot ; aucun push tant que les blocages persistent.


### F25 : raccordement de la gestion UI Weaver (sous-lot 1.7, 2026-10-25)

- Demande explicite de Dimi : implémenter ce sous-lot, exécuter les tests frontend
  ciblés, TypeScript et le build ; aucun déploiement, test cluster, migration,
  commit ou push. Les modifications locales préexistantes sont conservées.
- `TeamAgentsPage` utilise les six opérations déjà présentes dans le client Rust
  généré : liste/catalogue, création, GET individuel, PATCH et DELETE. Aucun
  fichier généré ni backend modifié pour ce lot. Les URLs restent `/team/:teamId/agents`.
  L'identité vient de `/me/spaces` : UUID canonique équipe/personnel ou résolution
  de l'alias personnel ; aucun ancien teamId accepté sans correspondance, aucun
  espace organisation/projet ajouté.
- La lecture et l'état du catalogue sont indépendants. La gestion dépend de la
  réponse serveur à `authorize/space` avec `write`, pas des libellés de rôle.
  Pas de catalogue pour un lecteur. Les contrôles backend Read/Write/can_use et
  le parcours d'authentification/CGU restent l'autorité.
- Formulaire complet conservé : métadonnées, rôle, usage, onglets et FieldSpecs.
  L'édition part d'un GET et le PATCH omet les valeurs inchangées ; tuning,
  sélection null/[], enveloppes de capacités et profil non pris en charge restent
  sauvegardés. Un tuning modifié puis rétabli n'est pas renvoyé. Sans catalogue,
  l'édition des métadonnées reste disponible ; les FieldSpecs sauvegardés ne sont
  pas exposés par GET, donc aucun champ de tuning n'est inventé dans ce cas.
- RTK invalide seulement la liste et l'instance du bon espace après succès.
  Les données `currentData` et le remontage par espace empêchent de réafficher
  l'ancienne liste ou sélection ; une confirmation de suppression devenue étrangère
  au contexte ne déclenche pas de requête. Les erreurs de mutation gardent la saisie.
- Chat, copie/duplication, publication, assistant de création, bibliothèque de
  prompts, sélection de profils/capacités et assets sont explicitement indisponibles.
  Les composants partagés gardent leur comportement hors de cette route. Les
  branchements legacy de page/formulaire/auteurs sont retirés ; les lectures legacy
  annexes du shell sont sautées sur Agents seulement (équipe/bootstrap, applications,
  wiki, knowledge bases, sessions, tâches, charte Swift et annonces). L'identifiant
  d'auteur reste affiché sans résolution legacy de son nom.
- Les états vide/chargement et erreurs 401/403/404/409/422/réseau/serveur sont distincts,
  en français et anglais. Un catalogue vide/403 ne masque pas les instances lisibles.
  Un 403 d'instance n'est pas converti en perte supposée du droit Write de l'espace.
- Vérifications finales, depuis `apps/frontend` : 30 fichiers / 256 tests ciblés
  passent (commande dans le suivi OpenSpec), `npm run typecheck` passe,
  `npm run build` passe. Avertissement Vite sur des chunks > 500 kB, sans échec.
  `git diff --check -- apps/frontend` passe ; client généré inchangé. Les premières
  erreurs introduites de typage et de montage des tests sont corrigées ; aucun
  échec restant signalé par ces contrôles. Pas de campagne globale ni test backend.
- Pas de validation utilisateur déployée. Tâche 1.7 entière toujours ouverte :
  préparation, sessions et chat hors lot. Dossier arc42 non étendu ; report des
  explications d'agents après validation explicite de Dimi.
- Essai proposé après redéploiement : Éditeur, créer/reouvrir/modifier le rôle ou
  nom seul (prompt intact), activer/désactiver, supprimer après confirmation ;
  Lecteur, consulter/rechercher/trier sans commande de gestion ni appel catalogue ;
  accès refusé, réponse 403 explicite et aucune donnée étrangère. Tester aussi
  espace personnel, bascule entre espaces et fonctions désactivées sans appel legacy.


### F25 : création confirmée et découpage du chat (2026-10-25)

- Dimi confirme avoir créé son instance dans l'UI déployée ; le bouton Discuter
  reste désactivé conformément au périmètre précédent. Cette observation ne
  valide pas encore l'édition, la suppression, les autres rôles ou le chat.
- Dimi confirme la frontière : Rust reprend seulement les responsabilités du
  Control Plane Python Swift. Exécution, streaming, modèles/outils, messages,
  checkpoints, renouvellement et arrêt des runs restent dans le pod Python.
- Plan simple ajouté au change OpenSpec existant : A consommateur du resolver,
  B exécution Python, C métadonnées/association des sessions, D préparation,
  E raccordement du chat existant. Un diff ciblé et un résultat vérifiable par
  incrément ; contrôle dynamique par Dimi. Première cible : Custom sans outil.
- Durée maximale d'un tour et budget de nettoyage à expliciter avant la mise en
  oeuvre de la borne de cinq minutes ; aucune nouvelle surveillance dans Rust.
- Cette étape prépare le plan uniquement : aucun code de production modifié,
  test, build, migration, déploiement, commit ou push. Les tâches parentes restent
  ouvertes et arc42 n'est pas étendu à un parcours chat non validé.


### F25 : parcours de l'administratrice et appartenance des capacités (2026-10-26)

- Dimi valide la distinction : autoriser les agents, encadrer les modèles,
  configurer les fonctions du pod, contrôler les données et connexions externes.
  Pas de permission utilisateur/capacité ni de confirmation d'activation de toutes
  les dépendances. L'activation d'un agent ne permet pas un modèle interdit.
- Une capacité offerte appartient à un seul pod logique. Deux pods intégrant le
  même package exposent deux offres distinctes ; aucune fusion globale par nom.
  Cette appartenance devra être portée par le modèle de données et les contrats.
- Dimi demande explicitement de commencer par une proposition arc42 : introduction,
  deux schémas simples, conventions Alice/Bob/Carol et parcours admin organisation.
  Le périmètre éditorial est étendu à ces décisions et à ce parcours spécifié,
  sans affirmer leur réalisation dans l'UI ou le runtime.
- Proposition rédigée dans 00 et le nouveau 02.3 ; index raccordés. Exemples
  Resources/documents et annexes harmonisés avec Acme/Research/Bob ; les vrais
  noms Priya/Demo/fredlab des fixtures restent explicitement identifiés comme tels.
- Décision 5b du change existant enregistrée ; l'ancien ordre Custom sans outil
  n'est plus le jalon prioritaire. Applications et Knowledge Bases laissées à part.
- Aucun code de production, schéma SQL ou contrat généré modifié. Aucun test,
  génération, build, déploiement, commit ou push. Relecture des sources Markdown
  seulement ; pas de validation visuelle du rendu Mermaid. Aucun gain de performance
  mesuré. Prochaine étape : modèle de données/contrats et lots.
- Dimi approuve le récit et précise son bénéfice : trois équipes peuvent partager
  une bibliothèque Fred tout en adoptant ses versions à leur rythme. Une seule
  peut mettre son pod à jour en production sans attendre les deux autres.
  L'introduction et le parcours expliquent cette adoption progressive, avec un
  exemple à trois pods ; la coexistence facilite la convergence, sans encourager
  les forks ni une multiplication de variantes. La décision 5b reprend ce motif.
  Cette précision reste documentaire et ne constitue pas une validation runtime.
- A la demande de Dimi, lecture allégée : trois schémas ciblés au total dans
  l'introduction et le parcours (droits, appartenance, mise à jour indépendante).
  Le récit est condensé et les décisions administratives regroupées en tableau ;
  les limites de sécurité et le statut de spécification restent explicites.
  Relecture Markdown uniquement, sans test ni build ni validation visuelle Mermaid.


### F25 : socle de persistance des offres par pod (2026-10-26)

- Branche `weaver`, arbre propre au début de ce lot. Lecture ciblée Rust, contrats
  SDK/pod et consommateurs UI ; Swift sert uniquement de référence fonctionnelle.
- Premier incrément de la décision 5b : migration additive 0014 et module interne
  `agents/catalog.rs`. Identité composée runtime/capacité, liens de templates vers
  une offre du même pod, remplacement atomique sérialisé par runtime. Les offres
  retirées gardent leur descripteur ; une panne conserve le dernier inventaire.
- Pas de branchement découverte/API à ce stade : les pickers de templates ne
  garantissent pas un inventaire exhaustif du pod. Aucun contrôle de modèle ni
  validation de configuration spécialisée n'est revendiqué. Les anciens refus
  explicites restent en place jusqu'au raccordement de leurs remplaçants.
- Découpage et cas manuels dans l'OpenSpec existante, décision 5c et tasks.md.
  Suite : inventaire complet et contrats admin générés, choix agents/modèles,
  validation/sauvegarde des configurations par leur pod propriétaire.
- Relecture statique seulement. Aucun test, qualité, génération, build, migration
  appliquée, déploiement, commit ou push. Annexes arc42 : référence au stockage
  interne uniquement ; parcours 02.3 toujours spécifié, non validé de bout en bout.

### F25 : inventaire complet et API administrative par pod (2026-10-26)

- Sous-lot réalisé sur `weaver`, arbre propre au départ ; migration 0014 conservée
  sans modification. Le registre Python et ses descripteurs alimentent maintenant
  `/agents/capabilities`, y compris les capacités sans consommateur. Seul `tool`
  entre dans cet inventaire ; les liens de tous les templates enregistrés réutilisent
  leurs règles de compatibilité et de sélection par défaut. Ce sont des déclarations,
  pas des exécutions constatées. Registre absent : 503, jamais un succès vide.
- Rust réutilise les sources configurées et `agents/catalog.rs`. Consultation par
  organisation et rafraîchissement ciblé par runtime ; identité/URL issues de la
  configuration plateforme. Réponse complète valide : remplacement atomique du pod
  seul. Offres retirées conservées ; panne/réponse invalide : observation indisponible,
  ancien inventaire intact. Lecture cohérente en repeatable read, états et dates
  explicites ; sources désactivées visibles mais non rafraîchissables.
- Admission, placement organisation, lifecycle et Manage réutilisés, sans droit
  implicite plateforme. Recontrôle sous verrou/fence après découverte, puis écriture
  dans la même transaction autorisée. Appel pod hors SQL, dix secondes, deux MiB,
  sans redirection. Doublons, liens absents et provenances contradictoires refusés.
  Descriptions de configuration sans valeurs, réglages privés de connexion ni secrets.
- Sources OpenAPI et deux clients régénérés ; aucun écran adapté. Configurations,
  historiques, droits agents/modèles, exécution, Applications et KB restent hors lot.
  Décision 5d, spécification et cas manuels ajoutés au change OpenSpec existant.
  Arc42 02.3/A2 distingue l'API implémentée du parcours non validé ; note de contrat
  runtime ajoutée. Aucun nouveau plan, branche, commit ou publication.
- Commandes : rustfmt ciblé, `ruff format` ciblé ; `make code-quality` Control Plane,
  fred-runtime et frontend ; depuis frontend, `make update-runtime-api` et
  `make update-control-plane-api`, puis Prettier ciblé sur les clients générés.
  Rust/Python/frontend réussis ; Python signale cinq avertissements de code inaccessible
  dans des fichiers hors lot. Premier Clippy : import inutilisé corrigé, relance
  réussie. Contrats relus : marqueur complet requis, défauts SDK conservés,
  types de champs et modèles d’exécution typés, descriptions localisées absentes
  omises plutôt que null pour correspondre au client généré.
  `openspec validate simplify-weaver-runtime-authorization --strict` et
  `git diff --check` réussis.
- Aucun test, campagne fonctionnelle, migration sur une installation, déploiement,
  commit ou push. Le contrôle arc42 complet n'est pas lancé : sa cible applique
  les migrations dans un conteneur ; seul le bloc de routes concerné est régénéré.
  Cas à jouer par Dimi dans `tasks.md` : même identifiant sur deux pods, absence de
  consommateur, retrait/panne/invalide/récupération, doublons/provenance/liens étrangers,
  admission/Manage/organisation étrangère et correspondance JSON/contrats générés.


### F25 : cadrage du catalogue de modèles plateforme (2026-10-26)

- Analyse seule sur `weaver`, en préservant les modifications en cours des deux
  incréments capacités. Cadrage consolidé dans le change OpenSpec existant,
  décision 5e, exigences acquises et incréments M1-M5 ; aucun plan parallèle.
- Direction acquise : découverte API uniquement, identité source/modèle amont,
  inventaire et décisions dans le Control Plane, destinations/credentials sous
  contrôle plateforme, inférence dans les pods. Aucun modèle interdit utilisable
  par défaut/fallback/autorisation d'agent ; aucun catalogue manuel de pod cible.
- Constat code Swift présent : découverte avec `OPENAI_API_KEY`, URL d'inférence
  dérivée du catalogue, défaut/fallback manuels ; `PLATFORM_BINDING` et
  `POD_FALLBACK` exclus du contrôle final `usable_model_ids`. Leur remplacement
  et les consommateurs à adapter sont identifiés, sans modification runtime.
- Propositions à arbitrer : credentials de découverte distincts, qualification
  chat/complétude des sources, maintien des choix existants en panne, références
  d'offres sans profil administrable séparé et lecture courante de politique par
  le gate du pod. Aucun de ces mécanismes n'est présenté comme implémenté.
- Cas ciblés consignés : deux sources/même nom, isolation organisationnelle,
  fallback interdit, panne/retrait/réapparition, destination non approuvée,
  credentials distincts et révocation avant une nouvelle invocation.
- Seuls les quatre documents du change et ce suivi F25 sont actualisés. Arc42,
  code, migrations, configurations, clients générés, UI/chat, Applications,
  Knowledge Bases et embeddings/traitement Knowledge Flow inchangés par ce lot.
  Relecture statique et contrôle du diff documentaire seulement ; aucun test,
  qualité applicative, génération, build, migration appliquée, déploiement,
  commit, push ou autre assistant. Implémentation à lancer séparément après examen.

- Arbitrage accepté par Dimi après relecture du cadrage : préférer de vrais droits
  de découverte seuls ; si le fournisseur ne les sépare pas, acceptation plateforme
  explicite par source, sans exclusion automatique ni transfert implicite de clé.
  Accepter les sources mixtes avec métadonnées fiables ; distinguer présence,
  aptitude chat et retrait confirmé. Maintien des choix autorisés pendant une panne
  de découverte, sans fallback ; défaut de lecture d'autorisation bloquant.
- Références d'offres sans profil administrable séparé retenues. Suppression des
  exceptions plateforme/fallback imposée par l'invariant déjà décidé. Accès SQL
  limité recommandé, contrat précis à cadrer dans M4 sans bloquer M1.
- Préparation de M1 uniquement : configuration des sources, découverte et
  persistance. Prompt remis pour lancement par Dimi ; aucun code de M1 ni lancement
  d'assistant. Documents existants harmonisés, sans modification d'arc42.


### F25 : M1 catalogue de modèles plateforme (2026-10-26)

- Réalisé sur la branche `weaver` existante, en préservant les changements capacités
  et cadrage présents au départ. M1 seulement : `platform.model_sources`, module
  Rust `model_catalog/{config,discovery,store}`, migration additive 0015 après
  revérification de la séquence ; aucune migration antérieure modifiée.
- Approbations persistées au démarrage sans appel fournisseur. Sources vides par
  défaut ; URLs découverte/inférence distinctes, provider/périmètre et références
  de credentials explicites. Secrets via ENV_FILE/environnement existant, jamais
  valeur SQL/réponse/log. Droits réels déclarés ; autorité d'inférence du credential
  de découverte soumise à acceptation explicite par source. Aucun secret de pod lu.
- Adaptateur unique : HTTP 200, data[], IDs exacts distincts/bornés, cinq secondes,
  un MiB, sans redirection. Enveloppe conservative ; pagination, réponse partielle
  ou tronquée et absence de garantie de complétude ne remplacent pas l'inventaire.
  Panne, invalide et incomplet distingués. Sources chat qualifiées ou mixtes avec
  `capabilities.completion_chat` booléen ; métadonnées absentes/invalides inconnues,
  aucune aptitude déduite du nom. Présence distincte de l'aptitude au chat.
- Deux tables indépendantes des pods. Publication source/offres atomique,
  identité composée, dates première/dernière présence et retrait conservées.
  Réapparition sur la même clé, panne sans retrait. Révisions strictes et jeton de
  rafraîchissement SQL : dernier démarré seul autorisé à publier, y compris pour
  les échecs. Changement/désactivation de source invalide l'ancien résultat ;
  aucune connexion/transaction SQL pendant HTTP. Suppression d'une source active
  de la configuration refusée jusqu'à sa désactivation explicite.
- `configure_sources`, `refresh` et `inventory` internes ; aucune route, CLI ou
  découverte automatique. M2 devra apporter ses autorisations et son recontrôle
  après découverte. Aucune politique, instance, résolution, UI ou exécution modifiée.
  Knowledge Flow, OpenFGA et exceptions Swift PLATFORM_BINDING/POD_FALLBACK intacts.
- Documentation : M1 coché comme implémenté uniquement, détail en décision 5e,
  contrat de composant, pointeurs de sources et annexe A2. Aucun parcours admin ou
  runtime déclaré validé. Cas manuels M1 remis dans tasks.md : identités A/B,
  qualification mixte/inconnue, vide/retrait/retour, erreurs/limites/pagination,
  révision/concurrence/annulation et liaison/confidentialité des credentials.
- Vérifications techniques : `rustfmt --edition 2024 --config skip_children=true`
  ciblé puis `make code-quality` dans `apps/control-plane` réussis (Clippy all-targets,
  fmt --check, parité modèle FGA). `make generate-config-schema` réussi, sans chargement
  de configuration ni service. `make generate-chart-schema` bloqué par le bootstrap
  existant : `target/scripts-venv/venv/bin/pip` absent. Reprise réussie par
  `python3 scripts/generate_chart_schema.py --fred-agents apps/fred-agents/config/schema/configuration.schema.json --knowledge-flow apps/knowledge-flow-backend/config/schema/configuration.schema.json --control-plane apps/control-plane/config/schema/configuration.schema.json --output deploy/charts/fred/values.schema.json`.
  Aucun fichier généré édité à la main ni environnement réparé hors lot.
- Validation statique des valeurs Helm réussie avec
  `libs/fred-runtime/.venv/bin/python scripts/check_chart_values.py deploy/charts/fred/values.schema.json deploy/charts/fred/values.yaml`
  (le Python système manque de `jsonschema`).
  `openspec validate simplify-weaver-runtime-authorization --strict` et
  `git diff --check` réussis. Comparaison à l'état initial : modifications des autres
  lots préservées, migrations 0001-0014 identiques. Le constructeur d'une fixture
  Rust est adapté au nouveau champ par défaut ; aucun test exécuté. Relecture
  statique du lot, sans autre assistant.
- Aucun fournisseur réel, test, campagne fonctionnelle, migration appliquée,
  déploiement, commit ou push. La migration et les comportements SQL/réseau restent
  à valider manuellement ; un endpoint tronquant silencieusement son inventaire
  exige une garantie plateforme et ne peut être détecté à partir des IDs seuls.


### F25 : M2 administration des modèles par organisation (2026-10-26)

- Implémentation locale sur `weaver`, au-dessus des changements M1/capacités présents
  au départ et préservés. Quatre routes : inventaire avec observation/offres/politique
  cohérents, refresh d'une source approuvée, GET/PUT de politique. Admission, placement,
  lifecycle et Manage existants, sans exception plateforme ; aucun objet modèle FGA.
- Migration additive 0016, après revérification de la séquence, non appliquée : politique
  et permissions par organisation, références composites aux offres, défaut/fallback
  contraints à l'ensemble permis, révision et attribution. Remplacement atomique sous
  verrou existant ; conflit 409 si révision dépassée. Purge physique d'organisation
  supprime ses décisions par cascade ; retrait ou départ d'une personne ne les efface pas.
- Nouvelles permissions et choix modifiés vérifiés seulement : offre connue, source
  active, observation réussie à la révision courante, présence et chat établi. Ancien
  snapshot après rotation insuffisant. Choix conservés en panne/retrait/non-chat visibles
  avec leurs diagnostics ; révocation/réduction/effacement restent possibles. Défaut
  révoqué à effacer ou remplacer explicitement dans la même écriture. Aucun choix implicite.
- Refresh M1 scindé en claim/publication sur connexion du caller. Autorisation avant
  découverte et après HTTP sous verrou/guard/fence, avant publication dans cette même
  transaction. Aucune connexion SQL pendant HTTP. Configuration exacte et dernier jeton
  démarré continuent de protéger sources/révisions ; refus tardif ne publie ni succès
  ni échec. Dernier succès conservé, aucune politique modifiée par la découverte.
- Projections typées sans destinations, références de credentials ou configuration
  privée. Adaptateur M1 réutilisé ; aucun fournisseur au démarrage, polling, source réelle,
  UI, instance, resolver, binding, routeur ou gate runtime ajouté. Exceptions Swift,
  Knowledge Flow et catalogues de capacités inchangés par ce lot. Arrêt avant M3.
- Contrat de composant, décision 5e, tâches/scénarios M2, source map et annexe/parcours
  d'administration mis à jour. M2 coché uniquement comme implémenté ; cas d'acceptation
  précis dans `tasks.md` restant à jouer, sans déclaration de validation runtime.
- Vérifications exécutées depuis la racine, sauf indication :
  - `/home/dimi/.cargo/bin/rustfmt --edition 2024 --config skip_children=true apps/control-plane/src/api.rs apps/control-plane/src/model_catalog/{mod,store,discovery,policy,http}.rs` : réussi.
  - `make -C apps/control-plane code-quality` : premier passage refusé par Clippy
    pour deux `needless_borrows_for_generic_args` dans le nouveau `policy.rs`.
    Corrections, puis `/home/dimi/.cargo/bin/rustfmt --edition 2024 --config skip_children=true apps/control-plane/src/model_catalog/policy.rs`
    et relance de la même commande qualité : réussies (Clippy all-targets,
    rustfmt --check, parité du modèle FGA). Compilation technique, aucun test exécuté.
  - Depuis `apps/frontend`, `make update-control-plane-api` : réussi ; appelle
    `make -C ../control-plane generate-openapi` puis
    `npx --no-install @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`.
    OpenAPI local (ignoré par Git) et client générés, aucun fichier généré édité à la main.
  - Depuis `apps/frontend`, `npx --no-install prettier --config .prettierrc --write src/slices/controlPlane/controlPlaneOpenApi.ts`,
    puis `make code-quality` : réussis (tsc --noEmit, Prettier, ESLint).
  - Régénération ciblée du seul A2 par `regenerate` du générateur canonique
    `docs/architecture/tools/docs.py`, chargé via `importlib.util` dans le script
    d'édition du lot. Pas de `make -C docs/architecture check`, car sa cible `er`
    applique les migrations dans un conteneur, contrairement à la consigne du lot.
  - `openspec validate simplify-weaver-runtime-authorization --strict` et
    `git diff --check` : réussis, relancés après la dernière édition documentaire.
- Relecture statique des sources/contraintes et du JSON OpenAPI généré : quatre routes,
  PUT avec quatre champs requis et choix nullables, aucun schéma privé ModelSource,
  InferenceDestination ou DiscoveryAuthentication. Comparaison au snapshot initial :
  client existant conservé avec ajouts M2, fichiers hors lot inchangés, migrations
  antérieures intactes. Ce constat ne valide pas la SQL ni les interleavings réseau.
- Aucun blocage préexistant rencontré par les contrôles demandés ; bootstrap Helm non
  touché. Aucun test, campagne, appel fournisseur, migration appliquée, déploiement,
  commit, push ou autre assistant. Cas M2 restant à jouer dans `tasks.md` : refus/isolation,
  révocation pendant HTTP, concurrence refresh/politique, inconnus/non-chat/retraits,
  panne/révision et confidentialité. Aucun parcours runtime déclaré validé.


### F25 : M3 recommandations, options et contrat du resolver (2026-10-26)

- Implémentation locale sur `weaver`, au-dessus des changements M1/M2/capacités
  préexistants sauvegardés puis préservés. Aucun autre assistant. Périmètre :
  `agent_instances/{http,tuning,runtime}`, `model_catalog/{instance,mod,policy,store}`,
  client Control Plane généré, affichage/sauvegarde du formulaire existant et docs.
- POST/PATCH/GET/list ajoutent `recommended_model` composite et `model_options`
  dans le JSON existant ; aucune migration. Organisation canonique de l'espace,
  personnel inclus. Nouvelle recommandation : permission courante et garde M2
  `require_selectable`, dans la transaction et les locks existants. Les locks
  source/offre empêchent une publication/configuration concurrente d'invalider
  les faits avant commit. Aucun deuxième catalogue/profil/sélecteur backend.
- Options limitées à temperature finie, max_tokens entier positif, top_p fini [0, 1].
  Objets fermés ; aucune option de transport, credentials ou reasoning. Limites
  connues de sortie/contexte vérifiées quand applicables, sans défaut fournisseur
  inventé ni preuve de compatibilité fournisseur. Omission PATCH conserve ; null
  efface la recommandation ou remet les options à {} ; objet options remplace
  complètement ses trois valeurs. Réglages non concernés inchangés.
- Resolver authentifié existant enrichi : snapshot repeatable-read de configuration,
  politique, sources/offres et connexions approuvées ; révisions, métadonnées connues,
  permissions, candidats, sélection possible et diagnostics séparés. Admission,
  délégation personne/workload, espace, template et état conservés ; droits recontrôlés
  après lecture. Connexions uniquement pour workloads délégués de confiance et offres
  candidates ; pas dans CRUD/admin ni pour un appel personne. Aucun secret ni
  paramètre de découverte. Le binding reste une photographie, pas un bail.
- Ancien `recommended_chat_profile_id` conservé en stockage/lectures ordinaires,
  non-null refusé en écriture. Dans le resolver seulement, référence retirée de la
  copie de configuration et exposée comme diagnostic avec re-sélection requise.
  Re-sélection composite explicite sans effacement automatique de l'ancien identifiant.
  Révocation/retrait/panne n'effacent rien ; édition descriptive et effacement possibles.
- Frontend exact : `weaverAgents.ts` omet le profil lors de la création et conserve
  son PATCH descriptif ; `AgentFormBody.tsx` affiche source/modèle dans le même champ
  déjà désactivé, ou l'ancien profil avec explication explicite. Libellés EN/FR adaptés.
  Aucun écran, parcours, onglet, contrôle, style ou interaction ajouté/déplacé ; aucun
  sélecteur, option UI, parcours organisationnel ou raccordement chat ajouté.
- Vérifications exécutées :
  - `/home/dimi/.cargo/bin/rustfmt --edition 2024 --config skip_children=true apps/control-plane/src/agent_instances/{http,tuning,runtime}.rs apps/control-plane/src/model_catalog/{instance,mod,policy,store}.rs` : réussi.
  - `make -C apps/control-plane code-quality` : premier passage Clippy refusé pour
    une variable inutilisée introduite dans `instance.rs`, corrigée ; relances après
    corrections et dernière adaptation Rust réussies (Clippy all-targets, rustfmt,
    parité FGA). Compilation technique seulement, aucun test exécuté.
  - `make update-control-plane-api` depuis `apps/frontend` : réussi, via le générateur
    OpenAPI Rust puis RTK codegen canonique. Aucun fichier généré édité à la main.
  - Depuis `apps/frontend`, `npx --no-install prettier --config .prettierrc --write`
    sur le client Control Plane, `weaverAgents.ts`, `AgentFormBody.tsx` et les traductions
    EN/FR du lot, puis `make code-quality` : réussis (tsc, Prettier, ESLint).
  - Relecture statique du schéma généré : trois options fermées et nullables,
    contraintes numériques, nouveaux champs d'instances/resolver, aucun schéma privé
    ModelSource/DiscoveryAuthentication/InferenceDestination. Relecture des consommateurs
    legacy, du contrôle de divulgation et des requêtes paramétrées, sans test dynamique.
  - Régénération ciblée A2 par `regenerate` du générateur canonique `docs.py` ; pas de
    `make -C docs/architecture check`, dont la cible `er` applique les migrations
    dans un conteneur et contreviendrait à la consigne explicite.
  - `openspec validate simplify-weaver-runtime-authorization --strict` et
    `git diff --check` : réussis après la dernière édition documentaire.
- Documentation : composant, source map, décision 5e, tâches/scénarios M3, delta spec,
  proposition, annexe A2, explication 02.3 et note contractuelle Weaver actualisés.
  M3 coché comme implémenté, sans validation fonctionnelle. Cas précis restant à jouer
  dans tasks.md : création/relecture, omission/null, limites/options invalides,
  révocation, panne/récupération, retrait, révision périmée et courses, organisation
  personnelle canonique, délégation/confidentialité, ancien profil et conservation UX.
- Aucun test, campagne, fournisseur réel, source activée, migration appliquée,
  déploiement, commit ou push. Aucun blocage technique restant dans les contrôles
  exécutés. M4 non commencé : pas de routeur/factory Python, choix de credentials,
  SQL pod, gate par invocation ou suppression des exceptions/catalogues runtime.
  L'ordre choix explicite/recommandation/défaut et le fallback pour retrait confirmé
  sont documentés pour le consommateur futur, pas déclarés appliqués aux invocations.


### F25 : arbitrage M4, autorisation une fois par tour (2026-10-26)

- Dimi confirme un appel unique et complet au resolver Control Plane au début de
  chaque tour. Le pod applique ensuite localement ce contexte à tous les appels
  LLM, sorties structurées, clients réutilisés, retries et descendants. Aucun
  appel HTTP/SQL/OpenFGA supplémentaire pour actualiser l'autorité pendant le tour.
- Révocation ou décommissionnement d'une personne/instance/template/source et
  retrait de modèle après admission : effet au tour suivant. Le tour engagé peut
  finir. Cet arbitrage remplace les relectures à chaque invocation et la garantie
  de révocation sous cinq minutes pour ces changements. Annulation explicite,
  terminaison, limites d'exécution et contrôles propres aux données/services restent
  distincts. Un retry ou un enfant ne renouvelle ni n'élargit l'autorité du tour.
- Proposition de vue SQL, rôle et connexion de lecture dédiés à l'autorisation M4
  abandonnée. Le compte SQL existant pour historiques/checkpoints n'est pas modifié.
  Support initial d'inférence compatible OpenAI accepté ; credentials locaux liés
  à chaque source, aucun secret envoyé par le resolver ni mutation globale d'env.
- Lecture ciblée : le pod appelle encore le resolver Swift /teams/... et calcule
  usable_model_ids une fois par tour, avec exceptions plateforme/fallback. Le
  resolver Weaver /spaces/... et son contrat M3 doivent être raccordés dans M4.
  RunScope/credentials sont réutilisables ; aucun gate distant par invocation
  préexistant n'est présumé. Ces constats ne valent pas validation fonctionnelle.
- Consignes AGENTS et quatre documents OpenSpec harmonisés ; historique M1-M3
  préservé, arc42 inchangé. Cadrage accepté seulement, aucun code, test, fournisseur,
  migration, déploiement, commit ou push. M4 reste non implémenté.

### F25 : M4 Python et retrait du catalogue du pod, validation conjointe à faire (2026-10-26)

- Code local raccordé : un appel au resolver Weaver /spaces/... par admission
  execute/stream/evaluate, via délégation personne/workload. Contrôle des identités,
  runtime, run/conversation et complétude des offres. Rust renvoie run_id et
  conversation_id ; SDK typé et clients générés actualisés. Aucun secours Swift.
- TurnAuthority privée dans RunScope, jamais sérialisée. Les retries et descendants
  restent dans le tour ; un autre template est refusé. Fin, pause HITL, annulation
  et déconnexion ferment l'autorité ; reprise ultérieure = nouvelle admission.
  Révocations/retraits après admission : effet au tour suivant, sans relecture,
  polling, SQL d'autorité ou contrôle par token SSE, ni délai artificiel de 5 min.
- Routeur existant : choix explicite, recommandation, défaut d'organisation ;
  identité source/modèle. Ancien profil ou choix interdit refusé. Fallback seulement
  pour retrait confirmé et destination autorisée/utilisable. Contrôles locaux au
  client et à chaque envoi HTTP effectif, y compris retry, outils et sortie structurée.
- OpenAI-compatible seulement. Configuration `inference_credentials` : source_id,
  api_root, credential_binding et nom d'env secret local doivent correspondre à
  la connexion approuvée. Pas de secret CP, pas de mutation d'env, pools réutilisés.
  Aucun changement du comportement par défaut de la factory Knowledge Flow.
- Provenance de conversation ajoutée à la table existante checkpoint_thread_owner
  (`binding_json`, identifiants seulement). Le code de création paresseuse contient
  l'ajout de colonne ; aucune évolution SQL exécutée. Anciennes conversations sans
  provenance refusées, pas de réattribution implicite. Effacement des checkpoints
  avec conservation d'historique : reprise à traiter explicitement.
- Dimi confirme explicitement la suppression du catalogue et des tests Swift et
  demande d'avancer sans nouvelle campagne de contrôles, puis de valider ensemble.
  Supprimés : model_routing/catalog.py et authz.py, YAML du pod, bootstrap et câblage
  Docker/Helm, contrats de profils/politique locale et anciens cas associés.
  Les tests Weaver préparés restent présents et n'ont pas été exécutés.
- Complément demandé explicitement par Dimi : les trois routes HTTP /models-catalog,
  /refresh, /detail et leurs quatre DTO ont ensuite été supprimés. Après le refus
  initial pour risque de rupture API avant M5, la revue automatique des commandes
  Codex a accepté cette suppression ciblée avec la nouvelle autorisation. OpenAPI
  runtime et client RTK régénérés ; aucun consommateur applicatif manuscrit restant.
  Les surfaces OpenAI direct-template et
  creation-assistant refusent explicitement en 503. Métadonnées de skills : lecture
  personne via espace canonique, distincte de l'admission et sans connexion secrète.
- Contrôles déjà terminés avant ce dernier nettoyage : make code-quality dans
  fred-core, fred-sdk, fred-runtime, fred-agents, control-plane, zéro erreur ; cinq
  avertissements de code inaccessible préexistants côté runtime. Pas de revalidation
  du diff final. Ruff ciblé appliqué aux fichiers nettoyés.
- Génération canonique : make update-control-plane-api et make update-runtime-api
  dans apps/frontend réussis. Schéma AgentPodConfig généré ; sous-cible chart en
  échec (pip absent du venv scripts), puis scripts/generate_chart_schema.py et
  scripts/generate_pod_chart_schemas.py exécutés avec apps/fred-agents/.venv/bin/python,
  succès. Aucun fichier généré édité à la main.
- À faire ensemble avant clôture M4 : qualité finale des composants/frontend,
  OpenSpec strict, git diff --check, fixtures d'intégration Swift restantes, puis
  dix appels/une résolution, révocation au tour suivant, resolver indisponible,
  choix/fallback/profil refusés, isolation A/B, structured output/bind_tools/retries,
  enfant non couvert, annulation/fin/reprise et provenance concurrente. Détail dans
  les tâches M4 et décision 5e. Aucune validation fonctionnelle revendiquée.
- Aucun test, campagne, fournisseur réel, migration appliquée, déploiement, commit
  ou push. M4 reste ouvert pour validation conjointe ; M5 et parcours chat complet
  non entrepris/validés. Modifications préexistantes et lots concurrents préservés.

### F25 : clôture technique M4 après nettoyage autorisé (2026-10-26)

- À la demande de Dimi, les contrôles finaux ont été exécutés sans campagne ni
  test fonctionnel. M4 coché pour code et qualité technique, pas pour validation
  du parcours chat. M5 reste non commencé.
- `make code-quality` : succès (exit 0) dans libs/fred-core, libs/fred-sdk,
  libs/fred-runtime, apps/fred-agents, apps/frontend et apps/control-plane
  (PATH=/home/dimi/.cargo/bin:$PATH pour Rust). Aucun échec introduit. Runtime :
  cinq avertissements préexistants de code inaccessible, zéro erreur. Core/SDK/pod :
  zéro avertissement. Frontend : tsc, Prettier, ESLint ; Rust : Clippy, fmt, parité FGA.
- Corrections finales : descriptions OpenAPI encore Swift remplacées, références
  de catalogue dans les fixtures MCP/config et exemples de chart retirées. Aucun
  catalogue, profil ou chemin local réintroduit. Runtime, pod et frontend revérifiés
  après ces corrections. `make update-runtime-api` et Prettier ciblé réussis.
- Charts : `scripts/check_chart_values.py` avec le Python fred-agents et `helm lint
  deploy/charts/fred` passent. Le lint nu agent-pod refusait les valeurs obligatoires
  runtime_id/security absentes, comme documenté. `helm lint deploy/charts/agent-pod
  -f /tmp/fred-m4-agent-pod-values.yaml` passe avec l'exemple du README. Générateurs
  canoniques chart vers /tmp puis diff des deux schémas : aucun écart. Aucun rendu
  n'a été installé/déployé ; pas de build d'image.
- `openspec validate simplify-weaver-runtime-authorization --strict` et
  `git diff --check` passent, y compris après cette dernière mise à jour.
  Commandes détaillées et matrice des contrats/consommateurs dans les tâches M4.
- Recommandations et réglages M3 conservés : recommended_model reste stocké et
  géré par Rust, transmis comme models.recommendation ; model_options devient
  models.options, appliqué par la factory (temperature, max_tokens, top_p). La
  projection AgentTuning concerne prompts/capacités et ne remplace pas ces faits.
  Priorité explicite > recommandation > défaut ; ancien profil diagnostic seulement.
  Types générés et affichage existant de gestion restent cohérents, sans nouveau sélecteur.
- Confirmé par lecture du code : une résolution complète par tour externe ; aucun
  contrôle distant d'autorité supplémentaire par appel LLM ; retries et descendants
  limités au RunScope ; autre template refusé ; autorité terminée inutilisable ;
  révocations/retraits considérés au tour suivant. Les contrôles de données/services
  et credentials restent distincts. Ce constat n'est pas une mesure fonctionnelle.
- Suppression finale des trois routes /models-catalog et quatre DTO confirmée,
  avec clients régénérés et absence de consommateur applicatif manuscrit restant.
  Modules/YAML/catalogues/profils locaux, bootstrap et montages supprimés ; seules
  références locales de credentials de source subsistent, sans pouvoir d'autorisation.
- Les scénarios M4 préparés restent non exécutés ; les anciennes fixtures d'intégration
  d'exécution Swift seront à adapter lors de leur reprise. Pas de résultat annoncé
  pour ces suites. OpenAI direct-template/creation-assistant restent explicitement
  non raccordés (503) ; conversations sans provenance refusées ; OpenAI-compatible
  seulement. Aucun fournisseur réel, migration, déploiement, commit ou push.

### F25 : correction du bearer de service à l'admission M4 (2026-10-26)

- Défaut signalé par Dimi : `_resolve_agent_instance` exigeait un Authorization
  dans `DelegatedCredentialProvider.credentials()`, alors que ce contrat fournit
  seulement les assertions personne/run/agent. Les contrôles statiques précédents
  ne détectaient pas cette incompatibilité de comportement ; le vrai fournisseur
  était donc refusé avant tout appel au resolver.
- Correction ciblée dans agent_app.py : exiger le fournisseur délégué, conserver
  ses assertions et acquérir le bearer avec son `get_token_lease()` existant.
  Cette acquisition préserve les vérifications du run avant/après l'attente et
  l'acquisition/caching M2M existants. Le bearer utilisateur n'est jamais utilisé
  en secours ; aucun contrat OutboundCredentials artificiel n'a été ajouté.
- Un seul GET au resolver par tour : Authorization construit avec le token de
  service, `auth=None` pour ne pas hériter d'une authentification/retry du client,
  `follow_redirects=False`, aucun replay sur 401. M2MBearerAuth n'est pas utilisé
  ici car son retry 401 ferait une seconde résolution. L'acquisition IAM reste
  distincte de la résolution d'autorité. Après la réponse, une vérification locale
  du fournisseur refuse un run devenu terminal pendant le GET, sans relecture
  distante ni création d'autorité pour ce run.
- Cas préparés dans tests/test_weaver_resolver_credentials.py : vrai
  DelegatedCredentialProvider, vrai M2MTokenProvider via MockIdentityProvider et
  transport IAM simulé ; assertions exactes, Authorization absent des credentials
  mais présent sur le GET, absence du bearer personne, un envoi sur succès et
  refus 401/403/503, identité incohérente, token indisponible, run terminal/supprimé,
  terminaison pendant acquisition et pendant résolution. Aucun de ces tests exécuté.
- Après formatage et ajout complet du fichier, `make code-quality` dans
  libs/fred-runtime et apps/fred-agents : exit 0. Runtime : zéro erreur et cinq
  avertissements préexistants de code inaccessible ; pod : zéro erreur/avertissement.
  `openspec validate simplify-weaver-runtime-authorization --strict` et
  `git diff --check` : succès, revérifiés après cette note. Aucun changement de
  contrat HTTP public : aucune régénération de client nécessaire pour ce correctif.
- Aucun test fonctionnel, campagne, fournisseur réel, migration, déploiement,
  commit, push ou travail M5. Les autres modifications du checkout sont préservées.

### F25 : M5a métadonnées privées et préparation navigateur (2026-10-26)

- Reprise du lot le 2026-10-26 : les API, la migration 0017, les contrats et les
  cas manuels ci-dessous étaient déjà présents dans le checkout. Leur lecture a été
  recroisée avec les consommateurs Swift et la provenance M4 ; aucune nouvelle
  implémentation ni migration concurrente ajoutée. Générations canoniques, formatage
  ciblé, `make code-quality` Control Plane/frontend, validation des valeurs Helm,
  `helm lint`, OpenSpec strict et `git diff --check` relancés avec succès. Les
  générations ne changent pas les contrats existants. Validation fonctionnelle
  toujours non exécutée ; aucun fichier du chantier documentaire parallèle modifié.

- Lot local uniquement sur `weaver`, sans raccordement des pages/hooks ni changement
  UX. Ajout de POST/GET `/spaces/{space_id}/sessions`, GET/PATCH
  `/spaces/{space_id}/sessions/{session_id}` et POST de l'instance
  `/prepare-execution?session_id=...`. Le client choisi conserve son identifiant ;
  Rust fixe propriétaire authentifié et provenance espace/instance/template/runtime.
- Migration additive `0017_session_metadata.sql`, numéro revérifié juste avant
  création, non appliquée. Table privée distincte des instances partagées, sans
  messages/checkpoints ni FK en cascade. Suppression de l'instance ou purge de
  l'espace n'efface pas la provenance ; un espace absent/retiré reste inaccessible.
- Admission et Read de l'espace restent obligatoires. Les métadonnées appartiennent
  uniquement à leur propriétaire, sans exception Manage/plateforme. Reprise POST
  identique : 200 et ligne inchangée, même après suppression/désactivation d'instance ;
  création initiale 201 ; propriétaire/espace étranger 404 ; autre association
  possédée 409. PATCH ne prend que titre/activité, champs d'autorité refusés en 422.
  Activité monotone plafonnée à l'heure serveur ; titre seul sans réordonnancement ;
  tri activité décroissante puis identifiant. Liste/lecture/renommage restent possibles
  après suppression/désactivation d'instance, sous les droits de l'espace.
- Routage : `public_base_url` explicite sur la source runtime, chemin d'ingress
  canonique de même origine ; aucune déduction depuis `base_url` interne ni URL
  navigateur. Sans source activée/routage approuvé : historique URL null et préparation
  refusée. Suppression d'instance seule : URL historique conservée et agent_deleted=true.
  Nom courant ou snapshot de l'inscription après suppression, sans synchronisation.
- Préparation : Read + Use du template, état/provenance de l'instance, source approuvée,
  catalogue actuel et association privée si session fournie. Familles react/graph
  sans outils seulement, streaming/UI parts existants, limite d'entrée annoncée par
  le pod ; HITL false, chat_controls vide. Outils actifs/famille non raccordée refusés
  explicitement. Découverte hors transaction via le client existant, sans fallback.
- Faits modèles réutilisés via M3 resolve(false), DTO navigateur sans connexion,
  URL d'inférence, référence de credential ni nouvelle politique. Recommandation,
  défaut/fallback, réglages et diagnostics restent ceux de M2/M3. Préparation sans
  grant ni promesse de disponibilité fournisseur, réponses no-store.
- Resolver M4 : vérification SQL de l'association enregistrée dans l'unique requête
  d'admission existante. Aucun changement Python ni relecture d'autorité dans les
  appels LLM/retries/descendants ; provenance checkpoint M4 comparée localement,
  ancien historique sans provenance toujours refusé. Aucun moteur de synchronisation.
- Générations canoniques réussies : `PATH=/home/dimi/.cargo/bin:$PATH make
  update-control-plane-api` dans apps/frontend ; `make generate-config-schema`
  dans apps/control-plane ; `python3 scripts/generate_chart_schema.py` avec les
  trois schémas existants. Runtime OpenAPI/client inchangés. Schémas/types lus :
  routes attendues, nullabilité requise et absence de connexions dans le DTO de
  préparation confirmées. Aucun fichier généré édité à la main.
- Formatage Rust ciblé (rustfmt, skip_children) et Prettier du seul client généré.
  `make code-quality` réussit dans apps/control-plane (Clippy --all-targets, fmt,
  parité FGA) et apps/frontend (tsc, Prettier, ESLint). Premier passage Rust corrigé :
  SQLx 0.9 exige des chaînes SQL statiques ; requête commune paramétrée, puis contrôle
  complet relancé avec succès. Ce sont des contrôles techniques, pas des requêtes
  métier exécutées ni une validation du SQL contre une installation.
- `scripts/check_chart_values.py` avec le Python fred-agents et `helm lint
  deploy/charts/fred` passent. `openspec validate simplify-weaver-runtime-authorization
  --strict` et `git diff --check` passent. Aucun conteneur, test ou fournisseur réel
  lancé. Cas manuels de reprise réseau, confidentialité, association, activité,
  suppression/désactivation, destination non approuvée et erreurs préparés dans les
  tâches existantes, non exécutés. M5a coché pour implémentation/qualité, M5 reste ouvert.
- Prérequis précis avant raccordement du chat : la lecture directe d'historique du
  pod filtre aujourd'hui seulement par propriétaire ; ajouter son contrôle d'admission
  et d'espace Weaver, indépendant d'une instance encore exécutable. Puis raccorder
  les consommateurs existants aux contrats espaces/sessions/préparation et aux offres
  composites, configurer les vrais ingress/credentials, appliquer les migrations dans
  un lot autorisé et valider fonctionnellement avec Dimi. Pièces jointes, prompts de
  contexte et HITL restent leurs raccordements propres, non annoncés disponibles.
- Mise à jour du contrat produit/runtime, README/source map et OpenSpec ; arc42 non
  élargi à un parcours non validé. Modifications préexistantes conservées, chantier
  Knowledge Flow/fred-core/document-access inchangé. Aucun test, migration appliquée,
  déploiement, commit, push ou autre assistant.

### F25 : M5b consultation privée d'historique dans le pod (2026-10-26)

- Implémentation locale sur `weaver`, avant raccordement du chat. Point commun
  `fred_runtime/app/history_access.py` pour GET `/agents/sessions`,
  `/agents/sessions/{id}/messages`, `/agents/checkpoints` et
  `/agents/checkpoints/{id}`. Authentification/admission existantes conservées,
  personne propre obligatoire même en mode dev ; user_id navigateur ignoré.
  Identités service (rôle, marqueur de compte ou rôle de délégation) et personnes
  seulement assertées refusées ; aucun run créé pour consulter un historique.
- Lecture seule de `checkpoint_thread_owner.user_id/binding_json`, sans contenu,
  initialisation ni réparation. Placement dérivé de cette provenance M4. GET M5a
  `/spaces/{space}/sessions/{session}` avec le vrai `PersonCredentialProvider` et
  le bearer de la personne vers la destination Control Plane configurée. Client
  HTTP partagé existant, timeout 10 s, auth héritée/redirects désactivés, aucun
  retry ni cache d'autorisation entre consultations. Pas de credentials réels
  configurés ; le contrat délégué du resolver n'est pas inventé pour M5a.
- M5a vérifie propriétaire privé, admission et Read courant ; comparaison locale
  de personne, clé de session, espace, instance, template et runtime. Le runtime
  doit être celui du pod destinataire. M5a ne renvoie pas user_id : sa requête SQL
  filtrée sur le bearer vérifié est la preuve de propriété côté Control Plane.
  Aucun prepare-execution, resolver d'exécution, catalogue ou grant supplémentaire.
- Instance supprimée/désactivée ou template inexécutable : consultation toujours
  possible si ces contrôles passent. Conversation autorisée et liée sans message :
  200 + []. Historique ancien, provenance perdue ou session seulement inscrite sans
  provenance M4 : 404 uniforme, sans rattachement. Même 404 pour inconnu, autre
  propriétaire, droits retirés ou association incohérente. Les indexes omettent
  seulement ces refus ; erreurs d'authentification/stockage/Control Plane remontées,
  jamais transformées en faux historique vide. Réponses de lecture no-store.
- Checkpoints : garde avant chargement des métadonnées brutes ; index limité aux
  candidats vérifiés avant ses agrégats. `_stats` ne contient que comptes/tailles,
  aucun identifiant ni contenu de conversation. Suppression/purge hors périmètre.
  Une consultation coûte un SELECT de provenance puis un GET M5a avant le contenu ;
  listes proportionnelles aux sessions propres, traitées en série pour borner la
  pression du pool. Pas de transaction SQL tenue pendant HTTP. Ce constat est
  statique, sans campagne ni mesure de performance.
- Consommateurs relus : CLI PodClient remonte les erreurs HTTP ; useSessionHistory
  rafraîchit le bearer et marque les non-2xx indisponibles. Aucun raccordement UI ;
  son cache d'affichage reste un point du futur lot M5. Aucun changement des tours
  M4 : une résolution par tour, contrôles locaux LLM/retries/descendants, révocation
  au tour suivant, annulation et fin distinctes.
- Cas préparés dans `tests/test_weaver_history_access.py`, non exécutés : identité
  et credentials réels du fournisseur personne, propriétaire/étranger, révocation
  entre deux lectures, suppression/désactivation, divergence de tous les IDs,
  provenance absente, vide autorisé, erreurs HTTP/SQL, substitution de requête,
  détails/indexes et refus des services/délégations. Quatre anciens cas HTTP directs
  de test_history.py remplacés ; suites d'exécution Swift non migrées/non jouées.
- Formatage ciblé : Ruff imports/format sur les cinq fichiers Python du lot.
  `make code-quality` dans libs/fred-runtime et apps/fred-agents : sortie finale 0.
  Runtime : zéro erreur, cinq avertissements préexistants de code inaccessible ;
  pod : zéro erreur/avertissement. Une erreur Optional introduite a été corrigée,
  puis contrôles complets relancés après les dernières modifications pertinentes.
- `make update-runtime-api` dans apps/frontend et Prettier ciblé réussis : OpenAPI
  régénéré, client RTK identique au fichier avant M5b ; aucune signature HTTP ni
  composant frontend modifié. `openspec validate simplify-weaver-runtime-authorization
  --strict` et `git diff --check` passent. README runtime et change existant mis
  à jour ; arc42 non étendu au parcours chat non validé. M5b coché pour
  implémentation/qualité technique uniquement ; M5 global reste ouvert.
- Aucun test, campagne fonctionnelle, fournisseur réel, migration appliquée,
  déploiement, commit, push ou autre assistant. Modifications préexistantes et
  fichiers du chantier documentaire parallèle préservés. Tous les cas de la
  matrice M5b restent à jouer avec Dimi ; aucune validation fonctionnelle annoncée.

### F25 : M5b correction de l'index des threads Graph (2026-10-26)

- Correction ciblée de GET `/agents/checkpoints` : le filtre exact
  `thread_id.in_(readable)` excluait les threads dérivés, même pour une session
  autorisée. Remplacement par l'union des prédicats `session_threads`, avec
  `graph_thread_prefix`, uniquement pour les sessions ayant passé la garde M5b.
  Le helper canonique conserve la séparation par `:` et l'échappement des motifs
  SQL ; ni préfixe voisin ni `_` ne doivent élargir le périmètre. Aucun changement
  de garde, de contrat de réponse, d'agrégats par thread, de tri, de limite ou d'UX.
- Cas préparé dans `test_weaver_history_access.py`, **non exécuté** : vrai
  FredSqlCheckpointer/SQLite, session autorisée `conversation_a` avec uniquement
  deux checkpoints Graph dérivés, autre session du même propriétaire dans un
  espace refusé par M5a. Variantes interdites `conversation_a_extra` et
  `conversationXa` pour couvrir la frontière du préfixe et le caractère `_`.
  Attendu : seuls les deux threads autorisés sont renvoyés, une ligne chacun,
  après vérification des deux sessions parentes ; aucun contenu de message chargé.
- Formatage Ruff ciblé appliqué aux deux fichiers Python modifiés.
  `make code-quality` dans libs/fred-runtime : sortie finale 0 après la dernière
  modification du cas préparé, zéro erreur et cinq avertissements préexistants
  de code inaccessible. `make code-quality` dans apps/fred-agents : sortie 0,
  zéro erreur/avertissement. `openspec validate simplify-weaver-runtime-authorization
  --strict` et `git diff --check` passent, revérifiés après cette note. Aucune
  signature publique modifiée : pas de régénération de contrats nécessaire.
- Changements préexistants préservés ; aucun test exécuté, raccordement frontend,
  migration appliquée, déploiement, commit, push ou autre assistant. Validation
  fonctionnelle toujours à jouer ; M5 global reste ouvert.

### F25 : M5c raccordement du chat existant (2026-10-26)

- **Implémentation locale sur `weaver`** : consommateurs frontend raccordés aux
  clients générés M5a et aux contrats M4/M5b, sans modification backend ni client
  généré. Inscription avec UUID frontend conservé et reprise POST idempotente,
  liste privée de l'espace courant, GET métadonnées/historique, PATCH titre/activité,
  préparation de l'instance puis SSE directement sur la destination publique du pod.
  Espaces canoniques issus du contexte Weaver existant, sans déduction depuis une
  ancienne équipe, un template ou un modèle. Une association incohérente est refusée.
- Navigation et composants conservés : Discuter, ManagedChatPage, ChatList,
  SessionTitleEditor, ReasoningChip et rendu SSE existants. Aucune nouvelle UX
  d'organisation/espace, administration ou refonte du sélecteur. Le shell du chat
  reprend le chemin Weaver déjà utilisé pour les agents ; appels auxiliaires Swift
  non raccordés désactivés dans ce parcours. Suppression, documents, pièces jointes,
  prompts/skills, voix et HITL non activés par ce lot.
- Historique séparé de l'exécution : l'URL vient des métadonnées, sans préparation
  lors d'une simple consultation. Suppression/désactivation d'instance et panne de
  template ne bloquent pas sa lecture autorisée. Le brouillon et l'intention de
  saisie préparent les contrôles ; chaque envoi refait la préparation après
  inscription. Refus et panne restent des indisponibilités explicites, distinctes
  d'un vrai 200 vide. Le droit d'envoyer reste vérifié indépendamment par M5a/M4.
- Cache et courses : RTK isolé par identité existante, tags par espace/session,
  réponses courantes en erreur non remplacées par currentData ancien. Historique
  annulable, no-store, redirects refusés ; clés personne/espace/session et garde
  de réponse tardive. Pas d'affichage d'un cache avant lecture courante ; refus ou
  panne effacent contenu affiché et snapshot. Revalidation focus/périodique existante
  réutilisée, sans nouveau surveillant. Une lecture autorisée en retard ne remplace
  pas un échange streamé plus récent. Le changement de contexte annule les envois
  préparatoires et réinitialise la page avant de montrer une autre conversation.
- Modèles : faits PreparationModels M2/M3 présentés dans le menu existant, clé
  `(source_id, upstream_model_id)` préservée jusque dans `model_choice`. Les choix
  explicites ne sont pas effacés lorsqu'ils deviennent indisponibles. Aucun choix
  automatique du premier modèle ni traduction d'un ancien profil. Recommandation,
  défaut/fallback et `model_options` restent appliqués par le serveur. Contrôles
  limités aux capacités annoncées. Politique M4, résolution unique par tour et
  gardes locales LLM/retries/descendants inchangées.
- **Contrôles techniques** : Prettier ciblé pendant l'édition, puis
  `cd apps/frontend && make code-quality` : sortie 0, TypeScript sans émission,
  Prettier et ESLint. Les premières erreurs introduites (expression de route,
  références supprimées et fixtures de profils Swift) ont été corrigées ; contrôle
  complet relancé après les dernières modifications. `openspec validate
  simplify-weaver-runtime-authorization --strict` et `git diff --check` passent.
  Aucun contrat modifié, donc aucune génération canonique nécessaire dans M5c.
- **Validation fonctionnelle non exécutée** : matrice complète dans les tâches
  existantes (création/reprise, streaming/rechargement, liste/renommage/activité,
  instance supprimée/désactivée, propriétaire/révocation, vide/panne, réponses
  tardives, modèles composites/options et UX). Fixtures du menu/composite et du
  composer adaptées mais non jouées. Les grands harnais Swift chat/SSE/historique
  gardent des hypothèses d'anciens endpoints/cache/HITL : leur migration/exécution
  appartient à un lot de tests autorisé, pas au résultat du type-check.
- **Prérequis et limites** : migrations existantes 0015-0017 non appliquées ;
  déploiement cohérent M1-M5b, ingress `public_base_url` approuvé, stockage runtime,
  délégation, credentials sources du pod et politique modèles organisationnelle
  requis. Premier périmètre sans outils React/Graph, instance activée/autorisée.
  Historique sans provenance non adopté. Une session uniquement inscrite sans
  provenance M4 reçoit encore le 404 uniforme M5b ; ce n'est pas un historique vide
  prouvé, et son éventuel premier envoi reste soumis à M5a/M4.
- Le runtime persiste après fermeture du flux et n'émet pas d'acquittement durable
  `turn_persisted`. Un rechargement immédiat peut précéder l'écriture ; aucune
  garantie lecture-après-final n'est ajoutée. Plus petit arbitrage proposé pour
  un lot runtime ultérieur : émettre l'événement existant après écriture réussie,
  ou accepter explicitement ce délai de visibilité. Aucun fallback, polling
  supplémentaire, moteur de conversation ou synchronisation n'a été créé.
- Modifications préexistantes préservées, y compris contrats générés et chantier
  documentaire parallèle. Aucun test, service, fournisseur réel, migration,
  déploiement, commit, push ou autre assistant lancé. M5c coché pour implémentation
  et qualité technique seulement ; M5 global, 1.7/1.8 et validation bout en bout
  restent ouverts. Arc42 n'est pas élargi à un parcours non validé.

## F26 Fusion Swift et préférences utilisateur

- 2026-10-25 : résolution de `git merge swift` à la demande de Dimi. Le commit
  entrant `def85bedd` ajoute les préférences personnelles. Conservation des
  adaptations Weaver du profil et des shells ; apports frontend Swift conservés.
- Les fichiers Python supprimés ne sont pas rétablis. GET/PATCH des préférences
  portés dans `user_preferences.rs`, migration additive SQLx 0013 et client RTK
  régénéré. Identité propre avant CGU via OwnUser, valeurs typées, null/defaults,
  champs inconnus refusés, PATCH atomique conservant les champs omis.
- Tests Python entrants remplacés par des cas Rust pour valeurs par défaut,
  isolation, validation, CGU, usurpation de sujet, services, concurrence et null.
  Inventaire OpenAPI et mocks frontend adaptés. Tests non exécutés.
- La suppression de comptes n’existe pas encore dans le Control Plane Rust.
  Son futur portage doit supprimer users_preferences pour le sujet supprimé,
  comme le nouveau contrat Swift ; ne pas confondre départ d’organisation et
  suppression de compte. Aucun endpoint de suppression ajouté dans cette fusion.
- Génération OpenAPI/client uniquement, avec compilation du générateur ; aucune
  migration appliquée, campagne de tests/qualité, installation, déploiement,
  commit ou push. Parcours manuel et validation PostgreSQL à faire par Dimi.


## DOC-5 Etat courant et cible Weaver dans les consignes

- 2026-10-26 : à la demande de Dimi, section `Weaver (Fred 5.x): current state
  versus target` ajoutée dans `AGENTS.md`, avec renvoi depuis `CLAUDE.md`.
  Tableau composant par composant (rôle cible, état sur `weaver`), étiquetage
  obligatoire courant / cible / Swift dans audits et rapports, et règles de
  coordination des lots parallèles Codex/Claude.
- Dimi confirme la cible : Knowledge Flow API disparaît ; sa recherche passe dans
  une bibliothèque de capacités du pod agent. Seuls restent en Python le pod agent
  et le worker Knowledge Flow. Constat courant : le runtime appelle encore
  `/vector/search` en HTTP et le chart déploie encore l'API.
- Consignes et journal seulement ; aucun code, test, build, commit ni push.

## F27 Primitive de visibilité des chunks

- 2026-10-26 : primitive lecture seule `fred_core/documents/access.py`, tests
  `fred_core/tests/documents/test_access.py`. Objectif : barrière SQL avant
  exposition au LLM d'une future recherche locale (décision 5 d'OpenSpec
  simplify-weaver-runtime-authorization). Aucun appelant, configuration ni connexion.
- `resolve_scope` reproduit le chemin Rust (`domain.rs`, `spaces::scope`) : espace
  et ancêtres, jamais enfants ni frères ; introuvable et en suppression distincts.
  Ce n'est pas une autorisation : le droit de lecture reste à l'appelant.
- `verify_candidates` : une requête groupée ; garde un chunk si son document est
  dans le périmètre, non retiré, d'espace actif, retrievable sans inclusion en
  attente, et si `chunk_uid` = uuid5(generation, ordinal) du manifest publié.
  Ordre conservé ; erreur SQL ou manifest invalide remontent. Métadonnées
  d'index ignorées.
- `make test-one TEST=fred_core/tests/documents/test_access.py` : 18 passés ;
  `make code-quality` (fred-core) : sortie 0.
- Limites : requêtes compilées pour asyncpg/psycopg mais jamais exécutées contre
  PostgreSQL ; pas de niveaux ni dossiers ; `folder.deletion_id` ignoré (jamais
  posé) ; coût uuid5 linéaire en ordinals pour un chunk absent. Aucune
  validation fonctionnelle, aucun commit.

## F28 Requêtes OpenSearch de la capacité Document Access

- 2026-10-26 : port en fonctions pures de la partie OpenSearch de la recherche
  Knowledge Flow API (`opensearch_vector_store.py`, `vector_search_service.py`),
  pour que la recherche quitte l'API. Fichiers : `fred_capability_document_access/
  opensearch_queries.py`, `tests/test_opensearch_queries.py`. Ni client, ni
  embedding, ni port, ni branchement (assemblage au lot C).
- `build_search` : semantic, strict, hybrid (`None` = hybrid) ; préfiltre
  obligatoire `metadata.space_id` + `metadata.retrievable=true` dans chaque
  sous-requête ; espaces vides refusés, pas de repli pour les index Swift sans
  `retrievable`. Pipeline `hybrid-search-pipeline` référencé, jamais créé.
- `read_response` : couples (`Candidate`, `VectorSearchHit`) dans l'ordre ;
  `chunk_uid` = `_id` (vérifié : identifiant uuid5 écrit par le worker) ; hits sans
  `_id`, `document_uid`, texte, ou à `chunk_uid` divergent écartés. Ni tags ni URL
  d'aperçu (point ouvert), ni `retrieved_at`.
- `make test-one TEST=tests/test_opensearch_queries.py` : 22 passés ;
  `make code-quality` : sortie 0 (tri d'imports corrigé dans le test).
- Limites : le préfiltre ne prouve rien, `verify_candidates` reste obligatoire ;
  rangs avant vérification SQL ; métadonnée mal typée = erreur de validation.
  Aucune requête jouée contre OpenSearch, aucune validation fonctionnelle, aucun
  commit.

## F29 Liste SQL des documents visibles d'un périmètre

- 2026-10-26 : lecture seule `fred_core/documents/tree.py`, tests
  `fred_core/tests/documents/test_tree.py` ; `access.py` expose `is_live_document`
  (règle commune, sans changement de comportement). Objectif : alimenter plus tard
  `list_document_tree` de Document Access sans Knowledge Flow API. Aucun appelant,
  rendu, configuration ni connexion.
- `list_visible_documents` : mêmes documents que `verify_candidates` (vivant +
  génération publiée, manifest non lu), chemin de dossiers en noms ; dossier
  retiré, chemin incohérent ou ancêtre sans nom = document écarté. Trois requêtes :
  espaces, documents (`LIMIT max_rows + 1` pour signaler la troncature), noms des
  dossiers (sautée s'il n'y en a aucun). Erreur SQL remontée.
- `make test-one` : `test_tree.py` 18 passés, `test_access.py` 18 passés (inchangé) ;
  `make code-quality` (fred-core) : sortie 0 après `ruff format` de `tree.py`.
- Retouche : la requête de documents reprend la règle dans son `WHERE`, en
  préfiltre seulement (le Python décide toujours) ; sans cela, des documents non
  inclus pouvaient épuiser `max_rows` et masquer les documents visibles.
- Limites : requêtes jamais exécutées contre PostgreSQL ; tri des dossiers par identifiants ;
  `folder.deletion_id` filtré mais jamais posé. Aucune validation fonctionnelle,
  aucun commit.
