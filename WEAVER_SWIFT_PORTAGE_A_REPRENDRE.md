# WEAVER - FONCTIONNALITÉS SWIFT À REPRENDRE

**Borne Swift intégrée : `49aaea6820556c63ff4e688dbfc7f8f702cad9e9`** (fusion décrite section 17 ; parents Weaver `58cc2ffe4` et Swift `49aaea682`).
Cette borne sert à inventorier les
prochaines arrivées Swift. La dernière tranche complète s'arrête à `89baab5b6` (merge `04aee8fbb`, section 14). Les réceptions et portages différés
restent un inventaire distinct ; leur présence dans l'ascendance ne vaut pas
validation produit. Les repères `53e39f6f7` ci-dessous concernent la tranche initiale.

**Etat consolidé de la tranche initiale, le 4 novembre 2026.** Les portages DOCX, titres, skills et
métadonnées e-mail de la tranche initiale sont intégrés. Mistral #3321 est mis de
côté à la demande de l'utilisateur, sans validation fournisseur. Les réceptions
k3d/plateforme et les raccords arc42 correspondants restent à effectuer.

La [méthode de merge](docs/SWIFT_WEAVER_MERGES.md) décrit la procédure réutilisable.
**Pilotage du 12 novembre :** priorité au merge interactif de la tranche `222bc60ac`
en [section 18](#18-audit-swift-et-reprise-kpi---12-novembre-2026). Aucun merge
effectué à ce stade ; la borne intégrée ci-dessus reste inchangée.
Ce dossier conserve les sources Swift, les décisions et les preuves de la tranche
initiale ; ce n'est pas une liste de missions à relancer intégralement.

> Un comportement différé peut déjà avoir son commit Swift dans l'ascendance.
> Un nouveau merge ne le réapplique pas. Les portages adaptés ne déplacent pas
> à eux seuls la borne Swift. Celle de la tranche initiale était `53e39f6f7` ;
> la borne actuelle est celle de l'en-tête.

## 1. Point de reprise consolidé au 6 novembre 2026

**Priorité actuelle : finir la réception du merge, puis ouvrir la tranche Swift suivante.**
Le développeur rapporte le 6 novembre une génération PowerPoint menée jusqu'au bout
sur son déploiement. Il reste à préciser les scénarios couverts ci-dessous. Les lots
applicatifs sont acceptés sur leurs preuves locales ; ne pas refaire leur revue
générale. Cet état consolidé prime sur les instantanés historiques ci-dessous,
notamment les mentions « non commité », « fichiers bloqués » ou « préparation à
raccorder » de la section 12.

### Où se trouve le travail

Vérification locale du 6 novembre, sans nouveau fetch :

| Elément | Emplacement et état constatés |
| --- | --- |
| Code Fred | `/home/dimi/Work/weaver/fred`, branche `weaver`, HEAD `47b08f41c`, identique à la référence locale `origin/weaver` |
| Lots PowerPoint et Temporal | Commit `ad97b2440` : fichiers CP, migrations 0006/0007/0008, préparation, worker, admission, chart et correctif UI |
| Conversations | `chore/conversations` fusionnée par `20779ca75` ; ses migrations portent les numéros 0009 à 0013 |
| Installations neuves seules | Chemins d'upgrade retirés à partir de `8f19b6a95` ; aucune reprise depuis un ancien Weaver ou Swift |
| Logs uniformes | Inclus dans `47b08f41c`, avec le reste de ce commit ; voir la [note opérateur](deploy/release-notes/changes/weaver-logs-stdout-only.md) |
| Configuration de déploiement | `/home/dimi/Work/common/fred-deployment-factory`, branche `weaver`, HEAD `9a884c6`, propre ; `fred-agents-worker` y est activé |

### Branches locales

Conserver `weaver` et `swift`. `chore/conversations`, `chore/rust-agent`,
`codex/merge-swift-20261104`, `codex/port-conversation-titles`,
`codex/port-email-metadata` et `codex/weaver-skills` sont toutes ancêtres de `weaver` :
leurs références locales peuvent être supprimées sans perdre de commit accessible.
Aucune branche n'a été supprimée.

Le chantier `chore/conversations` ne doit pas être confondu avec le sujet différé
« conversations sous Temporal ». Sa fusion n'en établit pas la réception déployée.

Repères de code pour retrouver le lot sans le réauditer :

- Schéma : `apps/control-plane/migrations/0006_powerpoint_files.sql`,
  `0007_capability_preparation.sql`, `0008_powerpoint_template_settings.sql`.
- CP : `apps/control-plane/src/documents/powerpoint/` et
  `apps/control-plane/src/capability_preparation/`.
- Worker : `apps/fred-agents/fred_agents/__main__.py`,
  `libs/fred-runtime/fred_runtime/app/preparation_worker.py` et
  `libs/fred-runtime/fred_runtime/capabilities/preparation_workflow.py`.
- UI : `CapabilityPlatformDrawer.tsx`, `PptBuilderPlatformPanel.tsx` et
  `PptBuilderTemplatePanel.tsx` dans `apps/frontend/src/rework/`.
- Exploitation : [note PowerPoint](deploy/release-notes/changes/weaver-powerpoint-file-ownership.md)
  et [raccord de déploiement](deploy/k3d/README.md).

### Consignes permanentes pour les assistants

- Développement et documentation seulement. Aucun accès cluster, démarrage de
  service, build de déploiement, déploiement, migration sur base vivante ou campagne
  navigateur. Le développeur garde le déploiement et les tests fonctionnels.
- Aucun commit, push, changement de branche ou résolution de merge sans demande.
  Préserver les modifications des autres auteurs et de la factory.
- Corriger un défaut concret remonté par le développeur, avec contrôles locaux
  ciblés autorisés ; ne pas rouvrir les lots acceptés ni lancer une campagne générale.
- L'UI Swift est un invariant. Réutiliser ses composants ; seules les adaptations
  nécessaires à organisation/équipe/projet et au pod sont admises. Aucun écran,
  sélecteur ou parcours parallèle inventé.

### Décisions PowerPoint à ne plus rediscuter implicitement

1. La capability est une bibliothèque fournie par un **pod logique**, pas un
   service plateforme. Sans offre correspondante, pas d'UI PowerPoint orpheline.
2. Le modèle commun appartient au périmètre **organisation + pod logique** de
   l'offre `ppt_builder`. Deux pods peuvent avoir des formats/versions différents.
   Aucun défaut configurable global plateforme, ni partage implicite entre pods.
3. Résolution : modèle propre à l'agent, sinon commun de son organisation et de
   son pod, sinon intégré à la bibliothèque. Les droits d'espace existants restent
   applicables ; un libellé « administrateur » ne remplace pas une autorisation CP.
4. CP/PostgreSQL font autorité sur rattachements, droits, révision et cycle de vie.
   S3 conserve les octets ; OpenSearch reste une projection. Le pod possède les
   règles PowerPoint et exécute la préparation.
5. Modèle propre à l'agent : pendant sa préparation, pas de nouvelle conversation
   avec cet agent ; succès puis disponibilité, échec visible et relançable. Ne pas
   inventer de repli sur l'ancien modèle propre lors d'un remplacement.
6. Modèle commun : l'ancien actif reste utilisable pendant la préparation du
   candidat et en cas d'échec ; activation seulement après succès. Sans commun,
   le modèle intégré s'applique.
7. UI : engrenage dans « Réglages » de « Générer une présentation » (`ppt_builder`),
   tiroir Swift, upload immédiat, revue/correction des slides, relance et remise à
   l'intégré. Aucun bloc commun ajouté au-dessus du tableau. `ppt_filler` est une
   autre capability : ne pas déplacer ses réglages par confusion de nom.
8. Vision hors tour indisponible et explicitement expliquée. Préparation
   structurelle seulement dans ce lot. Les conversations ne passent pas à Temporal.

### Jalons livrés et niveau de preuve

| Jalon | Livré | Ce qui reste à recevoir |
| --- | --- | --- |
| Persistance | 0006, dépôt/remplacement/retrait/résolution, droits et nettoyage des originaux | Parcours réel UI/CP/S3 |
| Préparation et readiness | 0007, intention durable, Temporal, mode worker, admission, reprise et nettoyage des nouveaux résultats abandonnés | Parcours déployé complet, échec/reprise et redémarrage |
| Raccord worker | Chart et correction du montage `processing-contract` ; valeurs complémentaires dans la factory | Déploiement cohérent des deux checkouts par le développeur |
| Parité UI Swift | Tiroir et composants réutilisés, corrections persistées ; 0008 pour les réglages communs, y compris intégré sans fichier | Comparaison FR/EN, SQL 0008 sur base neuve, persistance et isolation |

Les résultats locaux détaillés restent en section 12. Dernier correctif UI :
59 tests frontend, 19 bibliothèque, 58 runtime, 17 contrat CP rapportés réussis et
qualité des quatre composants conforme. Ces suites ne sont ni additionnées aux
précédentes ni relancées pour ce document. Elles ne prouvent pas le parcours déployé.

Un déploiement antérieur avec worker connecté est documenté en section 12, avant
le correctif UI/0008. Il ne prouve pas que l'installation actuelle exécute ce dernier
lot. L'ancien arrêt au bootstrap/CGU est un instantané historique, pas une affirmation
sur l'état actuel du navigateur du développeur.

### Réception PowerPoint à faire tranquillement dans cet ordre

Préparer deux fichiers `.pptx` valides A et B avec un marquage visuel différent,
un agent de test et, pour l'isolation, deux organisations et deux pods si disponibles.
Noter la révision Fred et l'état de la factory réellement utilisés au déploiement.
Tous les points ci-dessous restent à renseigner : la génération rapportée le 6 novembre
n'est rattachée à aucun d'eux tant que le modèle utilisé n'est pas précisé.

- [ ] **P1 - Interface Swift.** Administration de l'organisation, Fonctionnalités,
  Capacités, pod concerné : engrenage sur `ppt_builder`, même tiroir et disposition
  que Swift, en FR puis EN. Aucun bloc « modèle commun » au-dessus du tableau.
- [ ] **P2 - Modèle intégré.** Sans modèle propre ni commun, ouvrir la revue des
  slides, l'aide et les aperçus disponibles. Créer une présentation depuis le chat,
  télécharger le PPTX et l'ouvrir ; contenu et rendu exploitables.
- [ ] **P3 - Commun A.** Choisir A dans le tiroir : départ immédiat sans nouveau
  bouton Enregistrer. Préparation visible, puis A actif. Fermer/rouvrir et recharger
  la page : A et son état sont conservés. Un agent sans modèle propre utilise A.
- [ ] **P4 - Remplacer par B.** Pendant la préparation, A reste effectif ; après
  succès, une nouvelle génération utilise B. Recharger ne perd pas l'état.
- [ ] **P5 - Echec et relance.** Distinguer fichier refusé avant acceptation et
  préparation acceptée puis échouée. Le second cas doit montrer l'échec et permettre
  la relance, sans remplacer l'ancien commun actif. Si ce cas n'est pas reproductible
  dans l'UI, le noter « non testé » ; ne pas simuler une panne de cluster via assistant.
- [ ] **P6 - Corrections.** Modifier les informations de slides proposées par la
  revue, enregistrer, fermer puis rouvrir/recharger : corrections conservées sur le
  même modèle. Refaire avec le modèle intégré après réinitialisation. Un changement
  de modèle concurrent ne doit pas appliquer des corrections au mauvais fichier.
- [ ] **P7 - Réinitialisation.** Retirer le commun depuis l'action Swift : retour
  à l'intégré et absence des corrections de l'ancien fichier. Un modèle propre
  d'agent conserve sa priorité.
- [ ] **P8 - Modèle propre.** Ajouter A à un agent et sauvegarder. Observer son
  indisponibilité pendant la préparation, y compris après reload, puis sa disponibilité.
  Générer : A prime sur le commun B. Remplacer, tester l'échec si possible, puis
  retirer le propre : retour au commun applicable, sinon à l'intégré.
- [ ] **P9 - Droits et isolation.** Un lecteur non autorisé ne modifie pas le modèle.
  Changer d'organisation/pod ne révèle ni fichier, ni correction, ni état de l'autre.
  Sans pod offrant la capability, aucun réglage PowerPoint. Si un deuxième pod ou une
  deuxième organisation manque, marquer le contrôle non testé, pas réussi.
- [ ] **P10 - Usage réel.** Tester la génération avec texte, graphique et image dans
  les possibilités de Swift ; contrôler aperçu, téléchargement et ouverture du fichier.
  Noter séparément une erreur fournisseur et une erreur de préparation/conversion.
- [ ] **P11 - Suppression UI.** Supprimer l'agent de test hors tour actif : il ne
  réapparaît pas après reload. Ce contrôle UI seul ne prouve pas la purge S3/SQL.

Contrôles techniques distincts, à la main du développeur :

- [ ] Migrations 0001 à 0013 : initialisation sur base neuve ; régénération de la
  référence ER depuis le schéma vérifié.
- [ ] Images API/worker concordantes, file Temporal et identité de workload correctes,
  préparation/reprise après redémarrage sans activation d'une ancienne révision.
- [ ] Nettoyage effectif des originaux et nouveaux résultats abandonnés ; suppression
  de propriétaire acquittée. Ne pas en déduire une purge générale des plans/historiques.

### Autres points du merge et nature du travail restant

| Sujet | Etat et réception attendue | Nature de la suite |
| --- | --- | --- |
| Skills | `3fae108e4` intégré : catalogue, règles d'accès, chargement/traces, ReAct/Deep et limites Graph/Ralph | Réception ; pas de nouveau portage |
| Titres | `d61648f0e` intégré : titre automatique, renommage manuel concurrent préservé, bon historique/espace, échec modèle et usage comptabilisé | Réception |
| Auteur Word | `c784b3b71` intégré : auteur/dernier modificateur issus de l'utilisateur vérifié, repli sûr ; contrôler les propriétés dans Word/LibreOffice | Réception |
| E-mails | `276026917` intégré : `.eml`/`.msg` en bibliothèque et en pièce jointe de chat, détails, droits et frontière de conversation | Réception ; installer le bon contrat worker exporté, voir 7.3 ; aucun backfill |
| Notifications et HITL | Tranche `059ae1c91` : notification depuis une autre page, retour au bon espace, changement d'identité, états pending/unavailable/unknown et refus de reprise | Réception ; ne pas promettre la durabilité après fermeture d'onglet |
| Chat et ingestion déjà adaptés | Arrière-plan, file/steering, refus d'accès, DOCX invalide, retry mail/DOCX, extraction PPTX légère, MCP/tabulaire | Contrôles ciblés si ces usages sont exercés ; ne pas les considérer à réimplémenter |
| Isolation OpenSearch | `8134c78a5` intégré : vérifier la séparation effective Swift/Weaver dans le déploiement | Exploitation ; aucune migration des anciennes données annoncée |
| Backports CI et downgrade | Fusion `dfa19a3cc`, détails et preuves en section 13 | CI réelle et rollback isolé non reçus ; ne pas les tester sur la base vivante par défaut |
| Conversations | Fusion `20779ca75` : mémoire et historique de l'agent Rust, propriété, effacement, fichiers générés et acquittements des producteurs | Réception |
| Logs uniformes | Tout sur stdout au format commun, sans écriture directe dans OpenSearch ; voir la [note opérateur](deploy/release-notes/changes/weaver-logs-stdout-only.md) | Réception : lire une ligne de chaque processus dans `k3d-logs-*`. Factory : `weaver-app-logs` reste dans les droits de `k3d/values.yaml` |
| Déclarations opérateur | `make migration-check` (base `origin/swift`) valide 31 déclarations le 6 novembre | Aucune correction. Une PR ciblant `weaver` devra ajouter sa propre note |
| Architecture arc42 | Actualiser seulement les parcours effectivement reçus et leurs limites | Documentation après réception, pas preuve de fonctionnement |

La majorité de cette liste correspond donc à des **réceptions**. La durée des
éventuelles corrections fonctionnelles ne peut pas être garantie avant les tests. Ne
pas confondre nombre de contrôles et nombre de développements restant à financer.

### Sujets différés ou exclus qui ne bloquent pas ces premiers jalons

- Vision hors tour : reste à concevoir/raccorder sous les règles Weaver de modèle,
  admission et quota. Chantier distinct, pas une simple activation de bouton.
- Conversations sous Temporal : hors lot ; seule la préparation PowerPoint est concernée.
- Ressource remplacée/supprimée pendant un tour déjà admis : étude transversale
  différée. Le tour garde son admission, mais aucune survie garantie du fichier
  supprimé ; pas de rafraîchissement des droits par outil.
- Purge générale des plans, conversations et anciennes données Swift : hors lot.
  Ne pas étendre à ces données la preuve du nettoyage des nouveaux originaux/résultats.
- Skills possédés par espace : évolution produit distincte des skills fournis par pod.
- Mistral Large 4 / PR #3321 : mis de côté ; aucune relance sans demande.
- Erreurs MCP brutes, CP Python, OpenFGA et anciennes voies supprimées : exclusions
  volontaires, pas backlog à restaurer.
- Nouveaux commits Swift après `3d1838420` : inventaire séparé. Le fetch du 6 novembre
  en montre six, jusqu'à `89baab5b6` : `b00551906` (#3460, schémas tabulaires, prochain
  sujet choisi), `a2ebfe48c` (#3476, Azure APIM), `d9eb3738f` (#3453, test React),
  `303b7456e` (#3483, références de documents et écritures NUL), `507866562` (#3475,
  modèle Zabbix) et `89baab5b6` (#3455, SIEM). `b00551906` et `a2ebfe48c` sont depuis
  intégrés ; l'état à jour est en section 14. Aucun n'est nécessaire pour recevoir le
  lot actuel.

### Reprendre après une interruption

1. Lire cette section, puis vérifier les deux checkouts sans changer de branche.
   Comparer les nouveaux HEAD aux repères ci-dessus ; aucun lot n'est à réappliquer.
2. Recueillir les résultats P1-P11 et techniques du développeur. Pour chaque défaut :
   scénario, compte/rôle, organisation/pod/espace, modèle, action, attendu/observé,
   heure, capture ou message, révision déployée. Aucun secret ni jeton dans le suivi.
3. Traiter un seul défaut concret à la fois, réutiliser l'existant, puis laisser le
   développeur redéployer et recevoir. Une absence de résultat reste « non testé ».
4. Après PowerPoint, recevoir titres/DOCX, e-mails, skills, notifications/HITL ;
   consigner les preuves ici. Cet ordre est proposé pour réduire la charge, pas une
   dépendance technique entre ces lots.
5. Avant PR : lancer `make migration-check`, vérifier les contrôles documentaires,
   puis traiter les adaptations arc42 justifiées. Aucun push automatique.

Texte à transmettre à un prochain assistant :

> Nous travaillons dans /home/dimi/Work/weaver/fred, branche weaver. Lis AGENTS.md
> et la section 1 de WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md avant toute action. Les lots
> PowerPoint/Temporal/UI, conversations et logs uniformes sont intégrés dans weaver ;
> seules les installations neuves sont prises en charge. La factory
> /home/dimi/Work/common/fred-deployment-factory porte les réglages de déploiement ;
> vérifie son état sans le modifier. Les lots sont acceptés localement, la réception
> est à ma main. Aucun cluster, service démarré,
> déploiement, base vivante, campagne navigateur, commit ou push. L'UI Swift reste
> l'invariant ; commun PowerPoint par organisation/pod, aucun défaut plateforme.
> Ne refais pas la revue générale. Pars uniquement du résultat de test que je te
> donne, corrige le défaut ciblé et mets à jour ce suivi. Si je ne fournis pas encore
> de défaut, aide-moi à situer les validations restantes sans lancer un chantier.

### Inventaire historique de la tranche initiale

| Sujet | Etat courant | Suite |
| --- | --- | --- |
| [Skills](#skills) | Intégrés en `3fae108e4`, revue favorable après corrections | Réception déployée ; cible future de contenus par espace à discuter séparément |
| [Titres](#titles) | Intégrés en `d61648f0e`, lot code clôturé | Réception k3d/plateforme puis arc42 |
| [Auteur DOCX](#docx) | Intégré en `c784b3b71`, lot code clôturé | Validation humaine de l'export |
| [Mistral](#mistral) | Mis de côté, ne pas relancer sans demande | Ne bloque pas la suite ; aucune activation validée |
| [Métadonnées e-mail](#mail) | Intégrées en `276026917`, revue favorable | Réception bibliothèque/conversation ; aucun backfill |
| [E-mail joint au chat](#mail-chat) | Parcours tracé ; détails raccordés par le lot e-mail | Valider le parcours déployé complet |
| [Exclusions](#excluded) | Décisions maintenues | Ne pas restaurer les anciennes autorités |

L'isolation des index OpenSearch Swift/Weaver est intégrée en `8134c78a5` ; elle
ne constitue pas une migration des données Swift. La recréation du cluster et sa
validation sont pilotées par le développeur.

### Repères Git historiques de la tranche initiale

- Branche : `weaver`.
- Weaver avant fusion : `5786f7f558966f6f442da3d309a6a3e159e86cd9`.
- Swift intégré : `53e39f6f77e63bbc8238b881df38686df5be452e`.
- Ancêtre commun : `9b67927509474225975ebe9f84ba9a148d99d7cd`.
- Périmètre : **25 commits Swift**, inventoriés en annexe.
- Le commit de fusion contenant ce fichier a les deux premiers repères comme
  parents. Pour le retrouver après d'autres travaux :

```bash
git log --merges --oneline -- WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md
git show --no-patch --format='%H%n%P%n%s' <commit-de-fusion>
```

Les liens Swift de ce document sont fixés sur les commits historiques, pas sur une
branche mouvante. Les chemins Weaver désignent l'état du dépôt au moment de la
fusion. Les noms de modèles et paramètres fournisseur cités sont ceux de Swift,
pas une vérification de disponibilité du service chez le fournisseur.

## 2. Règles communes aux portages

- Le control plane Rust et PostgreSQL possèdent identités applicatives, espaces,
  droits, placements et décisions d'admission. Ne pas recréer leur équivalent Python.
- Un identifiant envoyé par le navigateur ou le modèle n'est pas une autorisation.
  Garder la distinction personne, workload et délégation vérifiée.
- Résoudre le contexte d'exécution fiable à l'admission du tour. Ne pas transformer
  un ajout fonctionnel en rafraîchissement des droits à chaque appel d'outil.
  Les nouvelles admissions observent le nouvel état ; les tours déjà admis suivent
  leur contrat existant. Les contrôles propres aux données restent nécessaires.
- L'accès à l'historique et aux pièces jointes conserve sa frontière de conversation,
  d'identité et d'espace. Un flux en mémoire n'est pas une preuve de droit de lecture.
- Réutiliser catalogue, annuaire, sessions, publication et métriques existants.
  Une nouvelle table exige un besoin explicite et une migration SQLx additive ;
  ne pas recopier les migrations Alembic de l'ancien control plane.
- Modifier les contrats dans leur propriétaire, puis régénérer les clients publics.
  Ne pas recopier les fichiers OpenAPI/TypeScript générés depuis Swift.
- Éviter les nouvelles couches de compatibilité et les doubles autorités.
  Vérifier les parcours réellement reliés ; une fonction isolée ne prouve pas l'usage.

Références maintenues : [instructions](AGENTS.md), [architecture actuelle](docs/architecture/README.md),
[control plane](apps/control-plane/README.md), [note opérateur de cette fusion](deploy/release-notes/changes/swift-weaver-2026-11-03.md).

<a id="skills"></a>

## 3. Skills : politique globale, nouveau catalogue et traces de chargement

**Références :** [issue #3299](https://github.com/ThalesGroup/fred/issues/3299), [PR #3342](https://github.com/ThalesGroup/fred/pull/3342), [commit 29c01c681](https://github.com/ThalesGroup/fred/commit/29c01c68131a31309b659842f22d4637dd215075).

**Etat actuel : portage adapté intégré en `3fae108e47c02e491a1ce3411feeac96c39baf8d`.**
Le report initial était intégral parce que Swift utilisait le Control Plane Python.
Le besoin a été repris dans la gouvernance Weaver, sans restaurer cette autorité.

Les skills de ce premier lot sont fournis par les pods et gouvernés comme les
capabilities. Les plafonds organisation, équipe et projet se composent sans
héritage des rôles. La préparation et l'exécution utilisent le contexte admis,
avec aperçus, sélection et traces. ReAct et Deep portent les skills ; Graph
s'exécute indépendamment du catalogue inutilisé et refuse une sélection explicite.
Ralph ne reçoit pas de projection de skills.

Le catalogue reprend `analyze-data`, `compare-options`, `grounded-research`,
`summarize-document`, `meeting-minutes`, `grill-me` et `graph`, avec leurs règles
d'invocation. Les anciens noms restent lisibles dans l'historique. Ni l'ancienne
politique Python ni ses migrations ne sont des dépendances de cette réalisation.

La revue a demandé puis constaté deux corrections : admission Deep dans sa propre
famille et absence de dépendance Graph à une source de skills non utilisée.
L'exécutant rapporte notamment 5 tests SQL et 7 HTTP après ces corrections, ainsi
que la qualité des composants concernés ; ces suites n'ont pas été relancées par
le maître d'oeuvre. La validation k3d/plateforme reste ouverte.

Le modèle « fourni par un pod » clôt ce premier lot ; il ne fige pas la cible.
La réflexion sur des skills possédés par organisation/équipe/projet, analogues aux
prompts, est un chantier produit distinct et n'est pas du code oublié du merge.

Pour retrouver les sources historiques, lire le commit Swift ci-dessus et sa note
`docs/swift/ops/migrations/platform-skills-evolution.md` via Git. Pour les preuves
actuelles, examiner le commit Weaver et ses tests. Ne pas réappliquer les patches
Swift sur le lot intégré.

<a id="titles"></a>

## 4. Titres de conversation générés et modèle configurable

**Références :** [issue #3346](https://github.com/ThalesGroup/fred/issues/3346), [PR #3351](https://github.com/ThalesGroup/fred/pull/3351), [commit 5ba132152](https://github.com/ThalesGroup/fred/commit/5ba132152b745ef338a7c493a4ec28588ebae5b2).

**État actuel : intégré, lot de portage de code clôturé le 4 novembre 2026.**
Commit `d61648f0e875fd77db4d1582ea1264a9c7536340`, intégré sans conflit depuis
`codex/port-conversation-titles`. Le report lors du merge initial reste expliqué
ci-dessous pour les prochains portages.

Le Responsable choisit facultativement un modèle autorisé par organisation.
Sans choix dédié, le titre utilise le modèle admis pour la réponse ; un choix
dédié inutilisable conserve le titre initial. La migration SQLx additive 0004
réutilise la politique et les sessions existantes. Une tentative est réservée
atomiquement au premier tour admis, sans retry ; les anciennes sessions restent
inéligibles. Tout renommage manuel, même à texte identique, invalide la tentative.
Python et Ralph génèrent le titre ; le serveur le persiste conditionnellement et
le navigateur recharge sa valeur canonique. L'usage est comptabilisé par offre.

L'exécutant rapporte 401 tests ciblés réussis et la qualité SDK/runtime/Control
Plane/frontend réussie. Le maître d'oeuvre a effectué une lecture ciblée des
contrats et du cycle de vie, vérifié le diff final et les notes opérateur, sans
relancer ces suites. Le parcours k3d/intégration reste à valider par le développeur.
Les annexes générées sont actualisées ; les raccords narratifs arc42 proposés
restent à intégrer après cette validation, sans prétendre un parcours déjà vérifié.

Le déploiement requiert migration et versions coordonnées : voir la
[note opérateur](deploy/release-notes/changes/weaver-conversation-titles.md).
Pour les futurs merges, préserver la distinction GET lecture / POST admission,
la priorité durable du renommage, l'autorité du tour et l'agrégation d'usage.
Ne pas restaurer le Control Plane Python, le catalogue local Swift ou une
persistance de titre pilotée par un booléen React.

### Ce que Swift apporte

L'administration peut choisir un modèle pour nommer les conversations. Au premier
échange, le frontend demande un titre ; le runtime lance un appel modèle parallèle
puis émet `session_title`. Le frontend le persiste dans la session. Le titre initial
sert en attendant, et le renommage manuel doit rester prioritaire.

Dans ce commit, le générateur reçoit au plus 600 caractères, demande 3 à 8 mots dans
la langue du message et nettoie/tronque le résultat à 80 caractères. À la fin du
flux, une tâche de titre encore en cours bénéficie d'une grâce de 2 secondes, puis
est annulée. Une erreur de génération ne doit pas faire échouer la réponse métier.
Le routage Swift essaie le modèle choisi, puis selon son contexte le binding chat
plateforme ou le modèle par défaut du pod. Ce fallback n'est pas à transposer sans
vérifier la gouvernance Weaver.

### Pourquoi le report

La sélection est stockée/résolue dans l'ancien control plane et ajoute un appel
modèle qui doit être autorisé et comptabilisé dans Weaver. La persistance du titre
et les événements doivent aussi résister aux changements d'identité/espace, à la
navigation en arrière-plan et aux renommages concurrents. Le garde-fou React de
Swift est une référence de comportement, pas une preuve d'arbitrage entre replicas
ou onglets.

### Sources à ouvrir

- [libs/fred-runtime/fred_runtime/app/session_title.py](https://github.com/ThalesGroup/fred/blob/5ba132152b745ef338a7c493a4ec28588ebae5b2/libs/fred-runtime/fred_runtime/app/session_title.py)
- [libs/fred-runtime/fred_runtime/app/agent_app.py](https://github.com/ThalesGroup/fred/blob/5ba132152b745ef338a7c493a4ec28588ebae5b2/libs/fred-runtime/fred_runtime/app/agent_app.py)
- [apps/frontend/src/rework/components/pages/ManagedChatPage/useManagedChat.ts](https://github.com/ThalesGroup/fred/blob/5ba132152b745ef338a7c493a4ec28588ebae5b2/apps/frontend/src/rework/components/pages/ManagedChatPage/useManagedChat.ts)
- [docs/swift/ops/migrations/3346-generated-conversation-title.md](https://github.com/ThalesGroup/fred/blob/5ba132152b745ef338a7c493a4ec28588ebae5b2/docs/swift/ops/migrations/3346-generated-conversation-title.md)

Côté Weaver : [décision de modèle](apps/control-plane/src/model_catalog/instance.rs),
[politiques de modèles](apps/control-plane/src/model_catalog/policy.rs),
[sessions et titres](apps/control-plane/src/sessions.rs),
[exécution et nettoyage du flux](libs/fred-runtime/fred_runtime/app/agent_app.py),
[usage](libs/fred-runtime/fred_runtime/app/usage.py),
[hook de chat](apps/frontend/src/rework/components/pages/ManagedChatPage/useManagedChat.ts),
[hook SSE](apps/frontend/src/rework/core/hooks/useChatSse.ts).

### Cadrage historique ayant guidé le portage

1. Définir qui choisit le modèle de titre et comment ce choix s'articule avec les
   offres autorisées. Réutiliser le catalogue et la décision d'inférence actuels ;
   aucun choix de profil envoyé par le client ne doit devenir une autorisation.
2. Définir quand un titre automatique reste applicable : première génération,
   renommage manuel, reprise et arrivée tardive. Envisager une écriture conditionnelle
   atomique dans le propriétaire de la session, fondée sur l'état/version attendu.
   Ne pas compter seulement sur un booléen local au navigateur.
3. Définir le routage autorisé et le comportement sans modèle disponible. Un titre
   cosmétique peut échouer sans casser le tour ; cela ne justifie pas de contourner
   les règles de modèle avec un fallback local.
4. Porter l'appel borné et son cycle de vie, en conservant le nettoyage et le
   `finally` de reporting Weaver. Comptabiliser l'usage supplémentaire et éviter
   les tâches orphelines ou les doubles appels lors d'une reprise.
5. Relier demande, événement, persistance et UI avec les contrats régénérés.
   Tout callback tardif reste lié à l'identité, l'espace et la conversation d'origine.
6. Porter le sélecteur admin et ses erreurs après l'établissement du contrat serveur.

### Validation fonctionnelle restante sur installation

6 novembre 2026 : OK rapporté par le développeur sur le cas nominal (titre au premier tour, pas de nouveau titre au tour suivant, renommage conservé après un message et un rechargement), selon le protocole prévu avec agent Python sans modèle dédié ; agent, modèle et révision non relevés, Ralph et cases ci-dessous non couverts.

- [ ] Première conversation, tours suivants et reprises : aucune génération répétée injustifiée.
- [ ] Renommage manuel concurrent prioritaire, y compris dans un autre onglet.
- [ ] Fin en arrière-plan et retour sur la conversation sans écriture dans une autre session.
- [ ] Ancienne identité déconnectée : aucun événement tardif ne modifie le contexte courant.
- [ ] Modèle interdit, indisponible, lent, sortie vide/invalide : titre de secours conservé et tour métier intact.
- [ ] Usage du modèle de titre enregistré ; annulation propre ; autorité des sessions inchangée.

<a id="docx"></a>

## 5. Nom de l'utilisateur comme auteur des exports DOCX

**Références :** [issue #3421](https://github.com/ThalesGroup/fred/issues/3421), [PR #3422](https://github.com/ThalesGroup/fred/pull/3422), [commit 55de29845](https://github.com/ThalesGroup/fred/commit/55de298455ffabf3a14b8eadc946553a4045a725).

**État actuel : intégré, lot de portage clôturé le 4 novembre 2026.** Commit
`c784b3b71fae2a5a8d055e159450387fd38bdf73`, intégré sans conflit depuis
`codex/port-docx-author`. Le report intégral décidé lors de la fusion du 3 novembre
est conservé ci-dessous comme contexte historique. Ce lot concerne les propriétés
d'export Word, pas la validation des DOCX importés déjà reprise.

Le routeur utilise le prénom et le nom vérifiés de l'exportateur si tous deux sont
non vides après nettoyage, sinon son username vérifié nettoyé. Sans nom fiable,
notamment pour `AssertedUser`, `author` et `last_modified_by` sont explicitement
vides. Les deux propriétés sont limitées à 255 caractères. Aucun uid ou nom de
workload ne remplace la personne ; aucun appel annuaire ni enrichissement de claims.
Cette divergence volontaire du backport doit être conservée aux prochains merges.

Le routeur, le convertisseur et leurs tests existants ont été adaptés. Les droits,
le contenu enregistré et l'export Markdown sont conservés. Aucun changement de
Rust, de schéma, d'API publique ou de client généré. Le README de la capability et
la [note opérateur](deploy/release-notes/changes/weaver-docx-export-author.md)
décrivent le comportement. Les raccords arc42 ont été approuvés séparément par
l'utilisateur : vue d'ensemble, parcours de Bob, distinction drive/conversation
et repères d'implémentation dans l'annexe A9.

Contrôles réalisés : qualité du package réussie ; **57 tests offline ciblés**
réussis dans `test_router.py` et `test_docx_export.py` ; note opérateur, liens et
ancres documentaires contrôlés. Le contrôle Git d'espacement est également passé.
Les tests remplacent l'authentification et le stockage par leurs fixtures : ils
ne prouvent pas l'export depuis un pod vivant. La validation humaine carte/panneau,
Word/LibreOffice et Markdown, ainsi que le parcours local k3d et plateforme
d'intégration, restent à faire. La clôture du portage ne les déclare pas réalisés.

### Ce que Swift apporte

À l'export, Swift lit `first_name`, `last_name` et `username` de l'utilisateur
authentifié. Il utilise prénom + nom quand les deux existent, sinon le username.
Le convertisseur renseigne `core_properties.author` et `last_modified_by`, avec
une limite de 255 caractères. Les tests couvrent l'auteur transmis et l'export.

### Pourquoi le report initial

La capability accepte notamment un `AssertedUser` qui ne possède pas ces champs de
profil. Copier l'accès aux attributs casserait ce chemin ou pousserait à fabriquer
une identité enrichie non prévue par le contrat.

**Weaver possède néanmoins un annuaire côté Rust.** `users.rs` comporte notamment
`UserSummary::display_name` et `Directory::display_names`, avec des sources
locales ou Keycloak. C'est un point de départ à examiner, pas la preuve qu'une
route utilisable par cette capability existe déjà. Les règles de fallback de cet
annuaire et celles de Swift ne sont pas strictement identiques : décider du rendu
souhaité au lieu de le laisser dépendre du chemin technique.

### Sources à ouvrir

- [libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/router.py](https://github.com/ThalesGroup/fred/blob/55de298455ffabf3a14b8eadc946553a4045a725/libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/router.py)
- [libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/docx_export.py](https://github.com/ThalesGroup/fred/blob/55de298455ffabf3a14b8eadc946553a4045a725/libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/docx_export.py)

Côté Weaver : [identité assertée](libs/fred-core/fred_core/security/delegation.py),
[annuaire Rust](apps/control-plane/src/users.rs),
[route d'export](libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/router.py),
[convertisseur DOCX](libs/capabilities/fred-capability-writable-document/fred_capability_writable_document/docx_export.py).

### Démarche initialement proposée (historique)

1. Confirmer la sémantique : auteur = personne qui exporte, comme Swift, ou autre
   besoin explicite. Définir nom incomplet, utilisateur sans profil et annuaire
   indisponible. Ne pas confondre auteur du contenu, propriétaire et exportateur.
2. Réutiliser l'annuaire fiable en respectant les frontières existantes. Examiner
   les appels disponibles avant de créer un endpoint ou d'élargir une assertion.
   Ne jamais prendre le nom depuis le formulaire ou les arguments du modèle.
3. Fournir au convertisseur seulement le texte d'auteur nécessaire, après résolution
   fiable. Ne pas ajouter tout le profil personnel dans les claims de délégation.
4. Porter les deux propriétés Word, la borne de longueur et les tests. Garder les
   contrôles actuels d'accès au document et à la conversation.

### Critères du portage vérifiés

- [x] Vraie classe `AssertedUser` couverte dans les tests offline du routeur.
- [x] Noms accentués, nom incomplet, absence de profil et chaîne trop longue.
- [x] Auteur et dernière modification cohérents ; propriétés du modèle effacées.
- [x] Refus d'accès préservé dans les tests ; nom fourni par le client ignoré.
- [x] Fallback vide documenté et testé sans profil ; aucun service de profil ajouté.
- [x] Validation fonctionnelle humaine de l'export depuis l'interface et du déploiement.

<a id="mistral"></a>

## 6. Mistral Large 4 dans le catalogue de modèles

**Références :** [issue #3320](https://github.com/ThalesGroup/fred/issues/3320), [PR #3321](https://github.com/ThalesGroup/fred/pull/3321), [commit 2ddc6870b](https://github.com/ThalesGroup/fred/commit/2ddc6870b44485573bed693c51420158a7c8303e).

**Etat : mis de côté à la demande de l'utilisateur le 4 novembre 2026.**
Ne pas lancer de portage ni activer une offre sans nouvelle demande.
L'entrée du catalogue local Swift reste non reprise. Ce n'est pas une suppression
d'un modèle configuré dans une installation Weaver, ni un changement du modèle par
défaut. Aucun appel au fournisseur n'a été effectué durant cette revue.

### Ce que Swift apporte

Une entrée `chat.mistral.large4` dans `apps/fred-agents/config/models_catalog.yaml` :
nom affiché Mistral Large 4, capacité chat, `supports_thinking: true`, fournisseur
compatible OpenAI, nom réseau `mistral-large-4`, base `https://api.mistral.ai/v1`,
`max_retries: 2`, `reasoning_effort: high`, `top_p: 1.0`. La note Swift indique que
le défaut local ne change pas et que les catalogues de production sont indépendants.

### Pourquoi le report et comment le reprendre

Le fichier local visé est retiré de Weaver. Recréer ce YAML ferait réapparaître un
catalogue concurrent de la gouvernance Rust. Le besoin éventuel est d'enregistrer
une offre de modèle, pas de réinstaller l'ancien mécanisme.

- Source historique : [apps/fred-agents/config/models_catalog.yaml](https://github.com/ThalesGroup/fred/blob/2ddc6870b44485573bed693c51420158a7c8303e/apps/fred-agents/config/models_catalog.yaml)
- Point d'entrée actuel : [catalogue Rust](apps/control-plane/src/model_catalog/mod.rs),
  [configuration](apps/control-plane/src/model_catalog/config.rs),
  [initialisation](apps/control-plane/src/model_catalog/initialization.rs),
  [décision commune](apps/control-plane/src/model_catalog/instance.rs).

1. Vérifier que ce modèle est souhaité et accessible avec le fournisseur prévu.
   Les identifiants Swift ci-dessus sont une trace historique à vérifier, pas une
   garantie de disponibilité ou de compatibilité de tous les paramètres.
2. Utiliser le mécanisme actuel d'enregistrement/découverte et les bindings de
   credentials prévus pour ce fournisseur. Ne pas copier une clé dans SQL, le
   navigateur, le dépôt ou les instructions de ce document.
3. Appliquer l'autorisation d'offre par les règles actuelles, puis vérifier que
   préparation UI et résolution runtime obtiennent la même sélection autorisée.
4. Vérifier l'option de raisonnement et les paramètres réellement acceptés, sans
   modifier par effet de bord le défaut des autres utilisateurs.

- [ ] Offre enregistrée et accessible seulement dans les contextes autorisés.
- [ ] Choix UI et décision serveur cohérents ; refus explicite hors périmètre.
- [ ] Credentials résolus côté serveur et jamais exposés au navigateur.
- [ ] Appel fournisseur validé séparément, si demandé, avec le compte prévu.

<a id="mail"></a>

## 7. E-mails : métadonnées structurées et parcours conversation

**Références :** [issue #3306](https://github.com/ThalesGroup/fred/issues/3306), [PR #3317](https://github.com/ThalesGroup/fred/pull/3317), [commit 2b6bf4e16](https://github.com/ThalesGroup/fred/commit/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e).

### Ce qui est déjà repris

Le parseur `.eml`/`.msg`, le rendu Markdown, l'extraction bornée des pièces jointes
prises en charge et les profils worker/Helm sont intégrés dans le worker Weaver.
Les noms, en-têtes et corps sont rendus dans le texte ; les en-têtes Cci ne sont pas
ajoutés à la liste extraite. Cela n'est pas une anonymisation des noms éventuellement
présents dans le corps ou dans une citation.

Les fichiers chiffrés en entrée sont refusés. Certaines pièces jointes illisibles
ou trop lentes peuvent être omises alors que le mail produit une extraction
partielle. Le délai par pièce jointe borne l'attente du thread, pas un arrêt forcé
de ce thread ; le superviseur du processus d'extraction reste l'enveloppe de durée.

### 7.1 Métadonnées structurées : portage intégré

Commit Weaver `276026917f8ad5de206cc0980d9ba49f02f62faf`. Ce commit commun contient
également du travail runtime/chat hors de la revue e-mail ; la réception favorable
porte uniquement sur les 29 fichiers attribués au lot #3317 et leur diff.

Le processeur écrit les faits du mail parent dans l'artefact de sortie. Le manager
reprend seulement le sujet (`title`), l'expéditeur (`author`), la date (`created`)
et `extensions.email` : `to`, `cc`, `message_id`, `in_reply_to`, sans `bcc`.
Les faits survivent au passage entre processus et à la restauration pour indexation.
Le Control Plane valide l'artefact avant publication ; l'aperçu partagé propose
les détails depuis la génération publiée, sous les droits courants.

Le nom de fichier, l'identité, l'espace, l'auteur et la date d'import restent
ceux du catalogue. Les en-têtes ne sont pas des identités authentifiées, ne
confèrent aucun droit et ne créent ni unicité ni regroupement de documents.
Les destinataires ne deviennent pas un nouveau filtre ou moteur de fils.

`DocumentMetadata`, metadata.json et la publication existante suffisent : pas de
migration SQL, table ou nouvelle voie d'ingestion. Les valeurs absentes du résultat
remplacent les anciens faits extraits ; aucune valeur métier utilisateur n'est
éditée par ce lot. Les documents déjà publiés gardent leurs artefacts et un état
vide explicite pour les détails absents. **Le retraitement après succès et le
remplacement de l'original restent indisponibles sur cette base ; aucun backfill.**

L'exécutant rapporte 131 tests worker, 44 UI et 5 Rust (2 unitaires, 3 scénarios
d'intégration), ainsi que la qualité des trois composants. La revue ciblée a
examiné les raccords, le périmètre, la note opérateur et la restauration de la
sauvegarde ; elle n'a pas relancé les tests. Le scénario Rust appelle le vrai
processeur puis publie sur PostgreSQL/S3 jetables ; Temporal et le transport du
worker sont pilotés/simulés. Ce n'est pas une validation du déploiement.

Sources : [extraction](apps/knowledge-flow-worker/knowledge_flow_worker/core/processors/input/email_processor/email_markdown_processor.py),
[manager](apps/knowledge-flow-worker/knowledge_flow_worker/features/manager_processing/service.py),
[validation](apps/control-plane/src/processing/retrievable.rs),
[aperçu et droits](apps/control-plane/src/processing/preview.rs),
[note opérateur](deploy/release-notes/changes/weaver-email-metadata.md).

<a id="mail-chat"></a>

### 7.2 E-mail joint à une conversation : parcours tracé, réception déployée restante

Le traçage a relié l'upload conversation, le profil fast, EmailMarkdownProcessor,
la publication et le périmètre documentaire du runtime sans identifier de manque
nécessitant l'ancien FastEmailProcessor synchrone. Le lot métadonnées raccorde
également le panneau des pièces jointes à l'aperçu partagé pour les mails.

Le lecteur reçoit la session explicitement, vérifie son association au document,
son propriétaire et les droits d'espace. La voie bibliothèque sans session exclut
les pièces jointes de conversation. Les tests couvrent les refus et les lectures
avant/après publication. L'exécution déployée complète avec l'agent, le contrat
worker installé et l'interface reste à valider sur k3d/plateforme.

### 7.3 Activation opérationnelle à ne pas oublier

Le control plane charge un **contrat worker exporté** et capture les profils dans
chaque enregistrement de traitement. Ajouter des lignes YAML ou redémarrer le worker
ne met pas à jour à lui seul un contrat déjà chargé.

Depuis l'image worker mise à jour et avec la configuration effective du déploiement :

```bash
python -m knowledge_flow_worker.features.scheduler.export_contract --configuration <worker-configuration.yaml>
```

Installer cet export au `worker_contract_file` configuré du control plane et le
recharger par la procédure de déploiement habituelle. Les traitements déjà admis
conservent leur snapshot. Au rollback, restaurer ensemble images, configuration et
contrat compatibles. **Ces opérations n'ont pas été exécutées pendant la revue.**
Voir [l'exporteur](apps/knowledge-flow-worker/knowledge_flow_worker/features/scheduler/export_contract.py)
et [le contrat côté Rust](apps/control-plane/src/processing/worker_contract.rs).

<a id="excluded"></a>

## 8. Exclusions volontaires et limites : ne pas les transformer en mauvais portages

### Diagnostics MCP, issue #3196 / PR #3197

**Références :** [issue #3196](https://github.com/ThalesGroup/fred/issues/3196), [PR #3197](https://github.com/ThalesGroup/fred/pull/3197), [commit c6741cde4](https://github.com/ThalesGroup/fred/commit/c6741cde480188e94ffdf70bde4b6c55a91eaac7).

Les diagnostics internes sont repris : route/outillage, statut et références
validées. **L'exposition brute des corps d'erreur amont aux agents est exclue.**
Weaver garde ses erreurs publiques filtrées et l'exception SQL 400 déjà encadrée.
Ce n'est pas un ticket de recodage en attente. Si un futur besoin exige plus de
contexte, définir une information sûre et ciblée, sans restituer un corps arbitraire.

Source actuelle : [montage MCP et politique d'erreur](apps/knowledge-flow-backend/knowledge_flow_backend/mcp_mount.py).

### Chemins historiques supprimés

Ne pas restaurer `apps/control-plane-backend`, ses tables/migrations Alembic,
l'ancienne API d'ingestion, l'agent platform-ops retiré, OpenFGA ou le corpus
`docs/swift`/OpenSpec supprimé. Les sources historiques restent consultables par Git.
Une fonction utile qu'ils contenaient doit être identifiée individuellement puis
replacée dans les propriétaires Weaver, jamais réintroduite par restauration globale.

### Changements repris qu'il ne faut pas refaire demain

- Plafond commun d'appels d'outils : **100 par tour**, PR #3404. Il n'y a pas de
  conflit avec le control plane Rust ; ce n'est pas un report.
- Chat en arrière-plan, files et steering : PR #3399, #3418 et #3429 adaptées.
  Deux courses supplémentaires ont été corrigées pendant la revue : adoption d'un
  historique avant son autorisation, et événements de l'ancienne identité modifiant
  la file de la nouvelle identité. Les tests ciblés couvrent ces frontières.
- Retry ingestion : DOCX et MSG ne transforment plus indistinctement erreurs mémoire
  ou I/O en entrée invalide permanente. La classification et les limites Weaver
  restent propriétaires de la décision ; les fichiers réellement malformés restent
  permanents. `FileNotFoundError` reste permanent selon la politique existante.
- Validation DOCX de #3341 : déplacée au début de l'extraction dans le worker, car
  l'ancienne passe de métadonnées à l'upload n'existe plus.
- Notes et graphiques PPTX de #3318 : adaptation de l'extracteur léger, notamment
  utilisé dans les pièces jointes de mail. Le processeur PPTX normal, qui possède
  déjà sa propre extraction native, n'est pas réécrit par ce changement.
- Tabulaire, diagnostics, ajustements UI, nom de site et chaîne Node/Vite/Temporal/uv :
  repris selon la matrice ci-dessous. Le code Rust et ses migrations, ainsi que les
  clients publics générés, n'ont pas été modifiés par cette fusion.

### Limites de validation encore ouvertes

Les files et indicateurs du chat sont liés à la durée de vie de l'onglet. La revue
ne promet pas de reprise durable après fermeture ou rechargement du navigateur.
Ce n'est pas une fonctionnalité Swift établie que cette fusion aurait omise.

Vérifications réalisées avant le commit, sur les lots concernés :

| Périmètre                                     | Résultat observé                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------------ |
| Chat après correction des courses             | 283 tests réussis, 6 fichiers, aucun ignoré                                    |
| DOCX/e-mail/PPTX léger après correction retry | 69 tests réussis                                                               |
| MCP et tabulaire                              | 97 tests réussis                                                               |
| Runtime steering/nettoyage                    | 26 réussis ; 2 PostgreSQL ignorés faute de `FRED_TEST_POSTGRES_URL`            |
| Logs core                                     | 97 tests réussis                                                               |
| Outillage des packages frontend               | 34 tests réussis                                                               |
| Sélection des images Docker                   | 19 tests réussis                                                               |
| Sélection frontend initiale, plus large       | 402 réussis ; 8 cas iframe ignorés faute de SDK construit                      |
| Qualité des composants affectés               | `make code-quality` passé ; worker : 3 warnings existants de code inaccessible |
| Déclarations opérateur et Git                 | Note de migration valide ; aucun conflit/erreur d'espacement                   |

Les suites se recouvrent : **ne pas additionner ces nombres comme une campagne unique**.
Pas de campagne fonctionnelle navigateur, de test de charge, de migration de base,
de publication de package ou de déploiement. Les tests PostgreSQL ignorés et les
parcours fonctionnels réels restent à valider avec le développeur. Les liens et la
cohérence de ce dossier sont vérifiés séparément ; sa rédaction ne nécessite pas
une nouvelle campagne de tests applicatifs.

## 9. Retrouver les changements Swift sans dépendre du contexte de chat

Exemples de lecture uniquement, à exécuter depuis la racine du dépôt :

```bash
# Examiner tous les fichiers du chantier skills, puis son diff.
git show --stat 29c01c681
git show 29c01c681 -- libs/fred-sdk/fred_sdk/contracts/skills.py

# Lire un fichier historique qui n'existe pas dans Weaver.
git show 5ba132152:libs/fred-runtime/fred_runtime/app/session_title.py

# Comparer le résultat de cette fusion avec son premier parent.
git diff <commit-de-fusion>^1 <commit-de-fusion> -- libs/fred-runtime

# Retrouver le commit d'origine d'une PR différée.
git log --all --oneline --grep='#3342'
```

Les patches des fixes de revue sont inclus dans le commit de fusion, pas dans des
commits Swift séparés. Utiliser le diff du premier parent pour les retrouver.
Les liens ci-dessous permettent aussi de lire les commits complets sur GitHub,
sans confondre leur appartenance à l'ascendance et leur adoption fonctionnelle.

### Matrice des 25 commits entrants, actualisée après portages

| Commit Swift                                                                                     | Sujet du commit                                                                                                              | Traitement dans Weaver                                                   |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| [7a2bbcbc5](https://github.com/ThalesGroup/fred/commit/7a2bbcbc5c8cc34f0eb7d9472715d57ca7faf35f) | fix(tabular): restore tabular SQL compatibility and trace panels (#3365)                                                     | Repris et adapté aux publications/droits Weaver                          |
| [5ba132152](https://github.com/ThalesGroup/fred/commit/5ba132152b745ef338a7c493a4ec28588ebae5b2) | feat(#3346): name new conversations with a generated title and choose its model (#3351)                                      | Portage intégré : `d61648f0e`                                           |
| [fa363690e](https://github.com/ThalesGroup/fred/commit/fa363690ebac5d438904d1538450cacff3c48d56) | fix(#3344): show the agent description on the chat welcome card (#3345)                                                      | Repris : description de bienvenue                                        |
| [c05b1a590](https://github.com/ThalesGroup/fred/commit/c05b1a59086ef91f3653e4100d7cf0494ff4f986) | fix(#3403): raise the per-turn tool call limit to 100 (#3404)                                                                | Repris : plafond 100                                                     |
| [2ddc6870b](https://github.com/ThalesGroup/fred/commit/2ddc6870b44485573bed693c51420158a7c8303e) | chore(#3320): add Mistral Large 4 to local text models (#3321)                                                               | Mis de côté : catalogue local retiré                                      |
| [df0e1993d](https://github.com/ThalesGroup/fred/commit/df0e1993d423c24a494ef062df6b7edd41d14d46) | fix(#3397): upgrade temporalio to 1.35.0 (#3398)                                                                             | Repris : Temporal 1.35, locks Weaver                                     |
| [f437d97f7](https://github.com/ThalesGroup/fred/commit/f437d97f7910211bdb8b221146b732b335e32cec) | fix(#3400): patch Vite across frontend and isolated consumers (#3405)                                                        | Repris : Vite                                                            |
| [b8ea24385](https://github.com/ThalesGroup/fred/commit/b8ea24385ca55b3cb139d77770b0793e37aaaef1) | fix(#3338): validate DOCX during metadata extraction (#3341)                                                                 | Adapté : validation DOCX dans le worker, retry corrigé                   |
| [c20fba2cb](https://github.com/ThalesGroup/fred/commit/c20fba2cbbaec287784fcbb770fe1a3d4fcee8e5) | docs(help-center): conversation privacy and no product name in pages (#3311)                                                 | Repris : aide, confidentialité des conversations                         |
| [92f05b4d2](https://github.com/ThalesGroup/fred/commit/92f05b4d27f4565b22a263dbf783e3aaaef55549) | feat(#3306): keep speaker notes and chart data in fast PPTX extraction (#3318)                                               | Adapté : extracteur PPTX léger dans le worker                            |
| [9d7b5f953](https://github.com/ThalesGroup/fred/commit/9d7b5f9538e854028608439d90524ae9e4249537) | chore(deps): bump the uv group across 14 directories with 2 updates (#3409)                                                  | Repris sur les composants Weaver encore présents                         |
| [2bc9e7012](https://github.com/ThalesGroup/fred/commit/2bc9e7012f32db05be0a781b515db6518eacbd4d) | fix(#3406): keep iframe host tests compatible with security updates (#3408)                                                  | Repris : compatibilité des tests iframe                                  |
| [3dcec9d3f](https://github.com/ThalesGroup/fred/commit/3dcec9d3f1b6f13e3fe72266f54d17294f922858) | fix(#3396): discard chat queues on disconnect and clean up stale steering (#3399)                                            | Adapté : files/steering, frontières Weaver conservées                    |
| [ce8da9dc6](https://github.com/ThalesGroup/fred/commit/ce8da9dc6d6d61128d2df7d0b951a13c629c0de0) | chore(#3416): bump Node.js from 22 to 24 (#3417)                                                                             | Repris : Node 24                                                         |
| [e6b471f70](https://github.com/ThalesGroup/fred/commit/e6b471f70a76ab3a05ee20f2629a1466376d076b) | fix(#3419): reuse the uv cache across worktrees                                                                              | Repris : cache uv partagé                                                |
| [3a8324432](https://github.com/ThalesGroup/fred/commit/3a83244325f0f527f9789ace494eaf0e0854b345) | chore(deps): bump the npm_and_yarn group across 2 directories with 3 updates (#3298)                                         | Repris : dépendances npm                                                 |
| [c6741cde4](https://github.com/ThalesGroup/fred/commit/c6741cde480188e94ffdf70bde4b6c55a91eaac7) | fix(#3196): preserve Knowledge Flow MCP failure diagnostics (#3197)                                                          | Adapté : diagnostics internes, erreurs publiques filtrées                |
| [2b6bf4e16](https://github.com/ThalesGroup/fred/commit/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e) | feat(#3306): ingest Outlook .msg and .eml mail files (#3317)                                                                 | Extraction adaptée ; métadonnées intégrées en `276026917` ; réception déployée restante |
| [a997ee4b3](https://github.com/ThalesGroup/fred/commit/a997ee4b3f8ff3053477c0d2399c2f79abadd580) | chore(deps-dev): bump minimatch from 10.2.4 to 10.2.6 in /apps/frontend in the npm_and_yarn group across 1 directory (#3423) | Repris : minimatch                                                       |
| [55de29845](https://github.com/ThalesGroup/fred/commit/55de298455ffabf3a14b8eadc946553a4045a725) | fix(#3421): use the authenticated user in generated docx metadata (#3422)                                                    | Portage intégré : `c784b3b71`                                      |
| [bcc65f39b](https://github.com/ThalesGroup/fred/commit/bcc65f39b5ca47c9b74d3cbd08e8ec2b11808b29) | chore(#3424): centralize the Node.js toolchain in .nvmrc (#3425)                                                             | Repris : baseline Node centralisée                                       |
| [29c01c681](https://github.com/ThalesGroup/fred/commit/29c01c68131a31309b659842f22d4637dd215075) | feat(#3299): evolve platform skills and native load visibility (#3342)                                                       | Portage intégré : `3fae108e4`                                           |
| [8c5faa604](https://github.com/ThalesGroup/fred/commit/8c5faa6049d105f880304acdb4d5b5ade76a8936) | fix(#2603): keep a streamed chat turn running across in-app navigation (#3418)                                               | Adapté : arrière-plan, autorisation de l'historique avant adoption       |
| [d93037008](https://github.com/ThalesGroup/fred/commit/d93037008bfcdc225cfc206b42002ed041ccdb38) | fix(#3322): show the deployment's site name instead of "Fred" in user-facing text (#3323)                                    | Repris : nom du site                                                     |
| [53e39f6f7](https://github.com/ThalesGroup/fred/commit/53e39f6f77e63bbc8238b881df38686df5be452e) | fix(#3427): preserve queues and clarify background chat status (#3429)                                                       | Adapté : files/statut arrière-plan, événements liés à l'identité         |

## 10. Clôture de la tranche et reprise suivante

Les portages identifiés sont intégrés, sauf Mistral volontairement mis de côté.
La borne Swift de cette tranche reste `53e39f6f77e63bbc8238b881df38686df5be452e`.
La référence locale observée `0773ff95d` lui succède, mais n'a pas été rafraîchie lors
de cette consolidation : ne pas la présenter comme le dernier état distant.

La tranche suivante est décrite en section 11. Pour les arrivées ultérieures,
actualiser les références et inventorier les nouveaux commits selon la
[méthode](docs/SWIFT_WEAVER_MERGES.md), depuis la dernière borne intégrée. Les réceptions DOCX, titres,
skills, e-mails et isolation k3d restent distinctes. Mettre à jour arc42 après leur
validation réelle ; ne pas ajouter les plans ou bilans de merge dans son récit.

A chaque intégration, actualiser les états de ce dossier et les preuves concernées,
sans créer un second tableau de suivi dans les skills. Les notes et métriques de
la fusion initiale en section 8 restent historiques ; les sections de chaque lot
portent les résultats ultérieurs. Les choix de cible futurs ne réouvrent pas
implicitement les portages clôturés.

## 11. Deuxième tranche : Swift 059ae1c91

Base Weaver : `6adc65bf41d10e56202797a529443a67f8dbe191`.
Borne précédente : `53e39f6f77e63bbc8238b881df38686df5be452e`.
Cible : `059ae1c91b959692f6a0fb61ddc9824c67c90355`.
Le commit de merge contenant cette section a pour parents la base et la cible.

| Commit Swift | Apport produit | Traitement Weaver |
| --- | --- | --- |
| `0773ff95d2dcde7c810e88c67cdbfed1e0d078a9` (#3428) | Notification d'une réponse terminée ou d'une demande humaine depuis toute page | Abonnement unique dans App, routes et catalogue de sessions par espace, identité vérifiée à l'émission et au clic ; pas de notification durable après fermeture/rechargement |
| `059ae1c91b959692f6a0fb61ddc9824c67c90355` (#3431) | Demandes humaines historiques périmées identifiées ; refus de reprise et détails d'outils cohérents | Indication facultative calculée après autorisation de lecture, état/checkpoints existants, refus sémantiques et relecture de l'historique ; droits et événements runtime Weaver préservés |

Le champ `resume_status` (`pending`, `unavailable`, `unknown`) est une indication
au moment de la lecture, pas une réservation ou une autorisation d'exécution.
Une reprise reste soumise à l'admission actuelle. Les requêtes sans réponse des
anciens runtimes restent compatibles ; l'annotation ne modifie pas l'historique
stocké ou les checkpoints. Aucun schéma SQL ni migration des données n'est ajouté.
Le client runtime est régénéré depuis le contrat source résolu.

La même tranche Swift introduit l'installation partagée de Trivy pour les scans
Docker. La matrice Weaver est conservée. Un raccord supplémentaire assure que
modifier cette action sélectionne aussi les trois images Knowledge Flow concernées.
La syntaxe et la sélection sont contrôlées localement ; aucun build, téléchargement
du scanner ou run GitHub Actions n'est présenté comme exécuté.

Les évolutions des corpus docs/swift/OpenSpec supprimés ne sont pas restaurées.
Leurs sources restent disponibles dans le commit Swift ; les conséquences opérateur
sont adaptées dans les [notes HITL](deploy/release-notes/changes/2337-hitl-resume-rejections.md)
et [notifications](deploy/release-notes/changes/answer-toast-on-every-page.md).
Les nouvelles explications arc42 restent à intégrer après réception déployée.

Contrôles de cette tranche : tests ciblés core/runtime, historique et admission,
frontend et sélection d'images ; qualité des composants applicatifs modifiés ;
notes opérateur et diff. Les suites d'historique se recouvrent : ne pas additionner
leurs résultats comme une campagne unique. Les anciens tests Swift qui contournaient
l'admission sont adaptés au véritable contrat Weaver, sans retirer les refus d'accès.

Réception restante : notification depuis une autre page et retour dans le bon
espace ; changement d'identité ; demande humaine pending/unavailable/unknown après
reload ; refus avant acceptation et absence de fausse annulation d'outil ; détails
de traces. Aucune validation navigateur k3d/plateforme ni appel fournisseur ici.
Les lots DOCX, titres, skills et e-mails précédents ne sont pas réouverts par ce merge.

6 novembre 2026, notification de réponse terminée : OK rapporté par le développeur, y
compris clic sur « Ouvrir » et retour à la bonne conversation et au bon espace depuis un
autre espace ; révision déployée non précisée. Restent à recevoir : changement d'identité ;
demande humaine pending/unavailable/unknown après reload ; refus avant acceptation et
absence de fausse annulation d'outil ; détails de traces.


## 12. PowerPoint et quatre commits Swift — 5 novembre 2026

### Références et décisions

- Branche locale : `weaver`, initialement propre ; aucun push.
- Parent Weaver : `e017f869ea5d5668a47d04da3c2de572e97af8b7`.
- Borne Swift précédente : `059ae1c91b959692f6a0fb61ddc9824c67c90355`.
- Cible Swift figée : `3d18384205a469f691bbf3ca3cb697911bc6b257`.
- Le merge contenant cette section a ces parents Weaver/cible Swift. La méthode
  de récupération du commit reste `git log --merges --oneline -- ce-fichier`.

| Commit Swift | Décision Weaver |
| --- | --- |
| `de9192157ea898fe9bb8873362b858fca3e7295d` (#3290) | Intégrer le moteur PowerPoint, graphiques, images, aperçu, téléchargement, analyse structurelle, corrections de slides et template partagé. Adapter autorisation, inventaire, UI et ports ; différer les raccords explicités ci-dessous. |
| `d850bdce63a69854ecc77d13ebb7fdb98fa33187` (#3470) | Intégrer le délai Trivy 15 minutes et l'ordre des preuves ; préserver la matrice et les contrôles des trois images Knowledge Flow Weaver. |
| `541f3275d9908732a4b7c5d99a7302756fce2171` (#3433) | Reprendre les notes produit et opérateur utiles ; garder les versions Weaver 5.0.0, sans restaurer le Control Plane Python, son chart ou les anciens corpus. |
| `3d18384205a469f691bbf3ca3cb697911bc6b257` (#3471) | Intégrer les cibles exactes de downgrade et refus des offsets ambigus ; adapter le test à la révision runtime Weaver supplémentaire. |

La décision de défaut configurable global est remplacée par le lot CP du
5 novembre : fichier propre à l'agent, sinon fichier commun de son organisation,
sinon fichier intégré. Les fichiers configurables sont persistés et résolus par
le CP, mais leur préparation et activation dans le pod restent à raccorder.
L'édition exige `write` sur l'espace propriétaire, sans privilège implicite
administrateur. Le champ historique SDK `team_id`
transporte le UUID canonique d'espace. Les routes navigateur viennent de
`public_base_url` configuré côté CP, jamais d'une URL annoncée par le pod.
Export et copie des assets vérifient les droits des espaces concernés ; la
validation avec assets ou instance exige un espace, contrairement au contrôle
JSON pur utilisé par le CP. Le binder est installé sur les routeurs de capabilities et les tests vérifient
les refus comme les autorisations ; désactiver la validation locale du JWT ne
supprime pas l'autorisation CP.

Les contrats CP, runtime et PowerPoint sont générés depuis leurs sources finales.
Les manifests, verrous, migrations et fonts du pod sont adaptés sans réintroduire
catalogue de profils YAML, OpenFGA, ancienne ingestion, état Redux de l'ancien CP
ou routes de readiness sans consommateur Weaver.

### Inventaire séparé des reports

- **Vision hors tour** : aucun contrat Weaver d'admission, quota et sélection
  de modèle n'est disponible ici. Le port refuse explicitement l'inférence ;
  l'UI explique l'indisponibilité et envoie l'analyse structurelle sans vision.
  Ne pas réintroduire les profils Swift pour activer ce chemin.
- **Template par agent et readiness persistée** : l'API Weaver de sauvegarde
  accepte une configuration JSON, pas les fichiers multipart et l'état
  `capability_pending` de Swift. Les hooks de bibliothèque restent disponibles,
  mais le formulaire refuse une sauvegarde avec nouveaux fichiers au lieu de
  les perdre silencieusement. Le fichier intégré reste utilisable. Le lot CP
  définit désormais les rattachements SQL, le transfert S3, le remplacement
  concurrent et la purge reprise des originaux. Il reste à raccorder validation,
  préparation, activation d'une révision exacte et readiness avant l'ouverture UI.
- **Cycle de vie et exploitation** : valider le nettoyage des nouvelles données
  de plans/assets lors de la purge de leur propriétaire et la cohérence du
  modèle d'organisation avec plusieurs replicas/pods. Les originaux CP sont
  couverts par le balayage S3 ; les analyses, miniatures et plans du pod ne sont
  pas purgés par ce lot. Les tests locaux ne prouvent ni ces parcours déployés,
  ni l'activation d'un modèle dans plusieurs pods.
- **Réceptions** : parcours administrateur global, refus hors espace, analyse
  et correction, export réel LibreOffice/fonts, téléchargement et rendu navigateur
  restent à recevoir sur le déploiement. Aucun appel fournisseur, benchmark,
  migration de données vivantes ou déploiement n'a été réalisé.
- **Anciennes tranches** : Mistral reste écarté ; les réceptions DOCX, titres,
  skills, e-mails et HITL des sections précédentes ne sont pas relancées.
  Les corpus docs/swift/OpenSpec et autorités supprimées restent supprimés.

Notes opérateur : [PowerPoint](deploy/release-notes/changes/ppt-builder-capability.md),
[versions](deploy/release-notes/changes/3433-prepare-v3-10-0-release.md),
[Trivy](deploy/release-notes/changes/3469-trivy-sbom-timeout.md),
[downgrade](deploy/release-notes/changes/weaver-exact-agent-migration-downgrade.md).
Le README de capability et l'aide EN/FR distinguent les chemins disponibles des
reports. Pas de description arc42 de fonctionnement déployé avant réception.

### Preuves locales

- `make code-quality` sur CP Rust, frontend, fred-agents, fred-runtime, fred-sdk,
  fred-core, PowerPoint et writable-document ; clients RTK régénérés.
- PowerPoint : `pytest -q`, **1119 réussis, 6 ignorés** faute de template de
  référence facultatif. SDK : **58 réussis** ; conversion office core : **20**.
- Runtime : tests ciblés ports/authz/copy/endpoints, migrations, récupération
  d'outils, admission skills et résolution des modèles : **143 réussis**.
  Le sous-ensemble de montage des routeurs se recouvre : ne pas additionner.
- fred-agents : boot de capabilities et downgrade : **8 réussis**, y compris
  refus d'un offset ambigu et maintien de l'autre arbre lors du downgrade.
- CP : test PostgreSQL jetable `capability_browser_route_uses_approved_ingress`,
  **1 réussi**, URL de descriptor hostile ignorée au profit de l'ingress approuvé.
- Sélection des images CI : **20 réussis** ; YAML des workflows relu et parsé.
- `make db-check-combined-heads db-check-combined-sqlite` sur une base SQLite
  jetable : upgrade de runtime/document/PowerPoint, drift et downgrade réussis.
- Déclarations opérateur : `scripts/migration_guides.py check-pr --base e017f869e
  --worktree`, quatre déclarations valides ; aucune migration SQL existante réécrite.
- Frontend : **385 tests distincts sur 21 fichiers**, incluant le parcours Weaver
  agents. Le dernier passage groupé a réussi 384 tests ; le seul échec, une attente
  de hint vision Swift, a été corrigé puis le fichier entier a réussi (13 tests,
  inclus dans les 385). Contrôles type/format/lint réussis ; revue des résolutions
  envers les deux parents. Aucun test ignoré ajouté pour masquer un échec.

### Lot de persistance CP PowerPoint - 5 novembre 2026 (état historique avant raccord)

Migration additive `0006_powerpoint_files.sql`, registre ciblé dans le stockage CP,
FK de rattachement, reçus rejouables et clés S3 immuables. Le remplacement compare
le fichier attendu puis rattache le nouveau dans une transaction courte, après
vérification S3. Les lectures contrôlent l'usage (instance/espace/organisation) ;
un identifiant de fichier ne permet ni adoption ni accès à un autre agent.
Le balayage de stockage existant nettoie abandons et retraits ; le manifeste de
suppression d'espace attend les originaux CP. Aucun index OpenSearch ni ancien
endpoint Knowledge Flow n'est ajouté.

Les routes, le cache et le panneau du défaut global sont retirés. Le formulaire
existant et le blocage de sauvegarde de nouveaux assets sont préservés. La
résolution CP n'annonce pas une préparation/activation opérationnelle. Les
analyses et plans du pod restent hors purge raccordée.

Voir [la note opérateur du lot](deploy/release-notes/changes/weaver-powerpoint-file-ownership.md)
pour l'upgrade, les contrats et les limites. Aucune base vivante, commit, publication
ou déploiement n'a été effectué.

Preuves locales du lot CP :

- `make code-quality` : CP Rust, frontend (Node 24.22.2) et bibliothèque PowerPoint.
- CP : 38 tests du groupe `document_storage::` réussis, dont les 4 scénarios
  PowerPoint ; le scénario coupure/rejeu a ensuite été complété par un abandon
  expiré et revérifié. Les 17 tests OpenAPI passent. PostgreSQL et S3 jetables
  uniquement ; initialisation fraîche et upgrade 0001-0005 vers 0006 vérifiés.
- PowerPoint : 47 tests ciblés réussis ; frontend : 52 tests du widget et 16
  tests des formulaires, sur des fichiers distincts. Les contrats CP et
  PowerPoint et leurs clients RTK sont régénérés depuis les sources.
- Références SQL/API régénérées et contrôles ciblés des annexes A2/A12 réussis.
  Le contrôle documentaire global rencontre le bloc généré périmé d'A3, déjà
  modifié par un autre auteur. Le contrôle global des notes rencontre les
  changements de configuration hors lot ; la nouvelle note seule est valide.
- Bilan propre au lot : production (migration incluse) +714/-978 lignes,
  tests +527/-964, contrats/graphes générés +482/-132. Les suppressions portent
  principalement sur le défaut plateforme abandonné et ses tests devenus caducs.


### Raccord de préparation durable PowerPoint — 5 novembre 2026 (non commité)

Prolongement autorisé du lot précédent, sur `weaver` à
`394a9150f7e5c6ac6abeb803775ca2a0a16377e8`. Le texte précédent décrit son état
historique ; les limites de sauvegarde/préparation mentionnées là sont remplacées
par le présent raccord. Les changements k3d/Helm et autres travaux voisins ne
font pas partie de ce lot. Aucun autre assistant, commit, push, déploiement ou
changement de base vivante.

- **CP et PostgreSQL** : migration additive 0007, 0006 inchangée ; dépôt provisoire,
  validation de lisibilité via la capability, acceptation atomique configuration /
  fichier / intention, état de préparation et refus d'admission. Les transactions
  libèrent leurs connexions avant S3, validation ou Temporal. La confirmation
  vérifie révision, rattachement, état et identité du workload.
- **Temporal et runtime** : livraison SQL durable, primitives de transport et
  réconciliation extraites du dispatcher existant sans détourner document_processing.
  Mode worker partagé dans fred-runtime, branchement `fred_agents --mode worker` ;
  l'API reste le défaut. Même image/bibliothèques et stockage partagé, file définie
  par installation et pod logique, UUID seul dans l'historique. Aucun workflow de
  conversation ni appel Knowledge Flow ajouté.
- **Bibliothèque PowerPoint** : validation sans écriture, résultat persistant avant
  confirmation, tentatives protégées par les leases SQL existants, reprise sur
  autre replica sans recalcul, tombstone contre les écritures tardives. Retrait des
  relances asyncio depuis sauvegarde/readiness et des anciennes méthodes de reprise.
  La readiness reste consultative ; la vision hors tour est refusée explicitement.
- **UI** : fichier joint au save existant, état CP relu après reload, préparation /
  échec distincts de la désactivation, aperçu autorisé par la résolution courante.
  Le modèle commun reste strictement `(organisation, pod logique)` : ancien actif
  conservé jusqu'à réussite du candidat, jamais un plugin/service d'organisation.
- **Cycle de vie** : nettoyage des nouveaux résultats abandonnés par le worker
  propriétaire ; suppression d'espace attend également cet acquittement. Plans,
  conversations et anciennes lignes Swift restent hors purge générale.

**Décision de portée prise pendant ce lot** : conserver un tour simple et inchangé.
Le suivi durable des usages par tour et les cas de remplacement/suppression pendant
un tour actif sont reportés à une étude transversale ultérieure. Le nettoyage peut
rendre l'ancien modèle indisponible à un tour déjà admis ; aucune garantie générale
de survie des ressources en cours n'est annoncée. Pas de nouvelle réautorisation
par outil ou appel LLM.

La [note opérateur](deploy/release-notes/changes/weaver-powerpoint-file-ownership.md)
détaille configuration, upgrade, démarrage, résolution et limites. La réception
avec navigateur et composants réellement déployés reste à effectuer ; les preuves
ci-dessous sont locales et ne valent pas réception déployée de bout en bout.


#### Réception locale observée

Commandes exécutées depuis le composant concerné, sans base vivante ni fournisseur.
Les résultats ci-dessous se recouvrent ; ils ne constituent pas un total cumulé.

| Composant / commande | Résultat observé et portée |
| --- | --- |
| CP : `make code-quality` | Clippy tous targets et rustfmt conformes. |
| CP : `make test-integration CARGO_TEST_OPTS=powerpoint_` | **8 réussis** ; PostgreSQL, SeaweedFS et Temporal jetables, initialisation fraîche et upgrade, acceptation atomique, refus, concurrence, cloisonnement, livraison rejouée, réconciliation et nettoyage. |
| CP : `cargo test --lib` | **68 réussis, 1 ignoré**. |
| CP : `cargo test --test openapi` | **17 réussis**, après déclaration des réponses 401 et des six routes internes de préparation dans le contrat. |
| Runtime : `make code-quality` puis `pytest -q tests/test_capability_preparation.py tests/test_capability_platform_ports.py tests/test_authorization_startup.py tests/test_weaver_resolver_credentials.py tests/test_outbound_credentials.py -m 'not integration'` | Qualité conforme ; **88 réussis**, test Temporal volontairement désélectionné dans ce passage. |
| Runtime : `FRED_PREPARATION_TEMPORAL_TEST=1 pytest -q tests/test_capability_preparation.py` | **6 réussis** lors du passage avec Temporal réel jetable ; redémarrage du worker après résultat SQL et confirmation interrompue, sans recalcul. Le cas supplémentaire de perte d'acquittement après commit CP est couvert dans le passage à 88 tests. |
| Bibliothèque PowerPoint : `make code-quality`, puis `pytest -q tests/test_analysis_job.py tests/test_builder_capability.py tests/test_pptx_archive.py tests/test_platform_template.py tests/test_plan_validation.py` | Qualité conforme, **58 réussis** ; warning préexistant `builder_decks.py/__all__`. |
| SDK et fred-agents : `make code-quality` dans chacun | Conformes ; `pytest -q tests/test_worker_entrypoint.py` dans fred-agents : **2 réussis**. |
| Frontend : `make code-quality`, puis `npx vitest run src/rework/features/capabilities/ppt_builder src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.marketplace.test.tsx src/rework/components/pages/admin/FeaturesPage/OrganizationCapabilities.test.tsx src/rework/components/shared/organisms/AgentCard/AgentCard.test.tsx src/rework/components/pages/TeamAgentsPage/AgentFormModal/AgentFormModal.pptBuilder.test.tsx` | TypeScript/Prettier conformes ; **11 fichiers, 111 tests réussis** : formulaire réel, états après reload, carte agent, aperçu et modèle commun. |
| Contrats : CP `make generate-openapi generate-config-schema`, frontend `make update-control-plane-api update-ppt-builder-capability-api` | Régénérations depuis les sources effectuées. |

Un premier passage de la suite PowerPoint complète avait donné 1070 réussis,
6 ignorés et 11 échecs sur les anciens contrats Swift de sauvegarde/relance et de
fixture. Ces cas ont été adaptés au contrat de préparation durable et font partie
du passage ciblé vert à 58 tests ; la suite complète n'a pas été relancée. Le
warning LangChain beta du runtime est préexistant.

Les hashes des migrations 0001 à 0006 sont identiques à la capture initiale.
La réception déployée reste ouverte : navigateur, ingress, vrais claims workload,
images concordantes API/worker, conversion Office et arrêt du worker dans ce
parcours complet. Les tests locaux ne prouvent pas ce parcours de bout en bout.

#### Réemploi, convergence et bilan propre à ce lot

Le CP reste propriétaire de l'acceptation et de l'admission. La bibliothèque
reste propriétaire du calcul, du stockage dérivé et de son effacement. Le runtime
possède l'exécution worker commune. Les primitives de connexion/livraison Temporal
sont partagées avec le dispatcher existant ; ses tables d'ingestion ne sont pas
réutilisées pour ce nouveau métier. SQL/S3, quotas, validation authentifiée et
composants d'interface existants sont conservés.

Le chemin supprimé est la relance locale depuis sauvegarde/readiness (`spawn_analysis`,
`restart_from_stored`, `recover_interrupted`, `refresh_outdated`, `_refresh_quietly`
et lanceurs associés). La recherche de consommateurs dans les sources capability,
runtime et application est vide. Les tests remplacés vérifient désormais la reprise
par préparation persistée et la lecture sans effet de bord. Les tombstones sont
conservés pour empêcher une écriture tardive ; les migrations appliquées et les
anciennes données hors périmètre ne sont pas supprimées pour réduire artificiellement
le bilan.

Comparaison avec la **capture du checkout sale au début de ce lot**, et non avec
HEAD : les changements du lot précédent et des autres auteurs sont exclus. Le
code de production augmente pour l'acceptation transactionnelle, le transport
worker et le nettoyage durable ; ce lot ne prétend pas être une réduction nette.
Les documents sont exclus des comptes et les contrats générés sont séparés.

| Catégorie | Ajouts | Suppressions | Net | Fichiers |
| --- | ---: | ---: | ---: | ---: |
| Production | +2066 | −638 | +1428 | 41 |
| Migration SQL | +105 | −0 | +105 | 1 |
| Tests et fixtures | +1276 | −727 | +549 | 19 |
| Contrats générés mesurables | +174 | −12 | +162 | 3 |
| Configuration et dépendances | +9 | −1 | +8 | 2 |

Le bilan généré mesurable couvre les deux clients TypeScript et le schéma de
configuration CP ; OpenAPI est régénéré mais son instantané initial ignoré par Git
n'est pas disponible pour un delta fiable. Aucun changement k3d/Helm voisin n'est
attribué à ce lot.

<details>
<summary>Inventaire des fichiers modifiés par ce lot</summary>

- `apps/control-plane/Cargo.toml`
- `apps/control-plane/config/configuration.yaml`
- `apps/control-plane/config/schema/configuration.schema.json`
- `apps/control-plane/migrations/0007_capability_preparation.sql`
- `apps/control-plane/src/agent_instances.rs`
- `apps/control-plane/src/agent_instances/http.rs`
- `apps/control-plane/src/agent_instances/runtime.rs`
- `apps/control-plane/src/agent_instances/tuning.rs`
- `apps/control-plane/src/agents.rs`
- `apps/control-plane/src/api.rs`
- `apps/control-plane/src/capability_preparation/dispatch.rs`
- `apps/control-plane/src/capability_preparation/http.rs`
- `apps/control-plane/src/capability_preparation/mod.rs`
- `apps/control-plane/src/documents/powerpoint.rs`
- `apps/control-plane/src/documents/powerpoint/acceptance.rs`
- `apps/control-plane/src/documents/powerpoint/http.rs`
- `apps/control-plane/src/lib.rs`
- `apps/control-plane/src/lifecycle/cleanup.rs`
- `apps/control-plane/src/main.rs`
- `apps/control-plane/src/processing/dispatch.rs`
- `apps/control-plane/tests/openapi.rs`
- `apps/control-plane/tests/support/document_processing.rs`
- `apps/control-plane/tests/support/document_storage.rs`
- `apps/fred-agents/fred_agents/__main__.py`
- `apps/fred-agents/tests/test_worker_entrypoint.py`
- `apps/frontend/src/locales/en/translation.json`
- `apps/frontend/src/locales/fr/translation.json`
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.marketplace.test.tsx`
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.tsx`
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/weaverAgentFixtures.ts`
- `apps/frontend/src/rework/components/pages/admin/FeaturesPage/OrganizationCapabilities.tsx`
- `apps/frontend/src/rework/components/pages/admin/FeaturesPage/OrganizationPowerPointTemplate.tsx`
- `apps/frontend/src/rework/components/shared/organisms/AgentCard/AgentCard.test.tsx`
- `apps/frontend/src/rework/components/shared/organisms/AgentCard/AgentCard.tsx`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/PptBuilderTemplatePanel.test.tsx`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/PptBuilderTemplatePanel.tsx`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/api/pptBuilderCapabilityOpenApi.ts`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/usePatternsPreview.ts`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/usePptBuilderAnalysis.test.tsx`
- `apps/frontend/src/rework/features/capabilities/ppt_builder/usePptBuilderAnalysis.ts`
- `apps/frontend/src/slices/controlPlane/controlPlaneApiEnhancements.ts`
- `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts`
- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/analysis_job.py`
- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/capability.py`
- `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/preparation.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/analysis_db.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/conftest.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/test_analysis_job.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/test_builder_capability.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/test_plan_validation.py`
- `libs/capabilities/fred-capability-ppt-filler/tests/test_pptx_archive.py`
- `libs/fred-runtime/fred_runtime/app/agent_app.py`
- `libs/fred-runtime/fred_runtime/app/config.py`
- `libs/fred-runtime/fred_runtime/app/context.py`
- `libs/fred-runtime/fred_runtime/app/preparation_worker.py`
- `libs/fred-runtime/fred_runtime/app/security.py`
- `libs/fred-runtime/fred_runtime/capabilities/platform_ports.py`
- `libs/fred-runtime/fred_runtime/capabilities/preparation_workflow.py`
- `libs/fred-runtime/fred_runtime/common/outbound_credentials.py`
- `libs/fred-runtime/tests/test_authorization_startup.py`
- `libs/fred-runtime/tests/test_capability_platform_ports.py`
- `libs/fred-runtime/tests/test_capability_preparation.py`
- `libs/fred-runtime/tests/test_weaver_resolver_credentials.py`
- `libs/fred-sdk/fred_sdk/contracts/capability/base.py`
- `libs/fred-sdk/fred_sdk/contracts/capability/preparation.py`
- `libs/fred-sdk/fred_sdk/contracts/runtime.py`
- `WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md`
- `docs/SWIFT_WEAVER_MERGES.md`
- `deploy/release-notes/changes/weaver-powerpoint-file-ownership.md`

</details>

### Raccord Helm du worker PowerPoint - 5 novembre 2026 (réception développeur)

**Périmètre ajusté à la demande de l'utilisateur : le développeur garde le build,
le déploiement et les tests fonctionnels.** Le présent lot prépare uniquement le
raccord et ses contrôles statiques. Les ajouts ciblés dans les fichiers déjà
modifiés ont été autorisés ; les changements voisins sont conservés. Base Fred :
branche `weaver`, HEAD `394a9150f7e5c6ac6abeb803775ca2a0a16377e8` ; factory : branche
`weaver`, HEAD `f2db3463601426b03f857552fbe7cae6d6d10d0d`. Aucun nouveau commit.

Le chart réutilise `inheritFrom` pour un Deployment `fred-agents-worker` distinct,
avec `python -m fred_agents --mode worker`. Image et version de capability, runtime
ID, SQL, URL CP, identité et références de secrets restent définis sur l'API ;
le schéma interdit leurs surcharges indépendantes sur le worker. Le scheduler du
worker est activé sans changer celui de l'API. La liaison workload CP est obligatoire
et les connexions Temporal doivent concorder. Le schéma du chart est régénéré depuis
les sources, incluant la configuration CP de préparation du lot précédent.

Le worker ne crée ni service/ingress, ni endpoint métriques, ni sonde API, ni RBAC
Kubernetes, ni migration supplémentaire. Il partage le Secret `.env` de l'API.
Il dispose de 60 secondes d'arrêt pour les 30 secondes de fermeture Temporal et
de limites initiales de 2 CPU / 2 GiB RAM / 2 GiB éphémères pour deux activités.
La valeur explicite `replicaCount: 0` est maintenant respectée par le template
Deployment, ce qui permet une pause sans arrêter l'API. Aucun tuning mesuré annoncé.

Fichiers du raccord dans Fred : `deploy/charts/fred/values.yaml`, templates
`_apps.tpl`, `_postgres.tpl`, `main.yaml`, `deployment.yaml`,
`scripts/generate_chart_schema.py`, `deploy/charts/fred/values.schema.json`,
`deploy/charts/test_manager_chart.py`, README du chart et de k3d, cette section et
la [note opérateur](deploy/release-notes/changes/weaver-powerpoint-file-ownership.md).
Dans la factory, seul `k3d-apps/fred/values-weaver.yaml` est prolongé : activation
du worker et liaison `fred-agents` à `agentic`, issuer local, audience `app`.
Les valeurs d'image existantes de l'API suffisent pour les deux processus.
Les modifications applicatives PowerPoint antérieures ne sont pas attribuées à ce lot.

Contrôles effectués, sans serveur applicatif ni mutation de cluster/base :

| Contrôle | Résultat et portée |
| --- | --- |
| `helm lint deploy/charts/fred --strict` | Conforme sur les valeurs du chart. |
| `make check-chart-values check-chart-schema-drift` | Conforme ; génération reproductible depuis les schémas sources. |
| `python3 -m unittest deploy.charts.test_manager_chart.PreparationWorkerChartTests -v` | 3 contrôles de rendu réussis, dont 9 configurations incohérentes refusées. Vérifie image/secrets/SQL après surcharge, commande, absence de réseau/sondes, ordre CP puis capability, pause à zéro replica. |
| Factory : `make k3d-app-validate FRED=weaver APP=fred DIR=<checkout Weaver>` | Conforme ; aucune construction d'image ou installation. |
| Comparaison des manifestes du profil avant/après | Ajout du Deployment, ConfigMap et ServiceAccount worker uniquement ; seules la configuration CP et son checksum changent parmi les ressources existantes. API, frontend et KF inchangés. |
| Ruff ciblé et vérification du diff | Générateur et bloc de contrôles ajouté conformes ; pas de reformatage des travaux voisins. |
| Empreintes des migrations 0001 à 0007 | Identiques à la capture initiale. Aucune migration ajoutée. |

Limites préexistantes conservées : `helm lint` avec le fichier de valeurs factory
signale les `collection_name: null` des deux vector stores KF, alors que le rendu
Helmfile avec validation du schéma passe. Ces nulls retirent le paramètre pgvector
hérité lors du rendu OpenSearch ; ils ne sont pas supprimés pour masquer le lint.
Le fichier de contrôles voisin contient aussi un import `tempfile` inutilisé et
du formatage antérieur ; le bloc ajouté est vérifié isolément. Aucun composant
applicatif n'étant modifié, aucun `make code-quality` applicatif ni suite runtime
n'a été relancé.

**Réception A-G : non exécutée, laissée au développeur.** Aucune image de ce lot
n'a été construite ou déployée. La cible identifiée est `k3d-fred` / `fred-weaver`,
base `fred_weaver`, namespace Temporal `fred-weaver`, avec S3 et Keycloak partagés
avec Swift ; l'utilisateur a autorisé de dédier Weaver à la réception, puis a
repris la main sur son exécution. Les ressources vivantes sont laissées inchangées.
Seuls des instantanés de sources et rendus temporaires non secrets ont été créés
pour comparer le lot. Aucun appel fournisseur, assistant supplémentaire, commit,
push ou déploiement partagé.

Premier point de test utile après déploiement : vérifier les images API/worker
identiques, la rétention Temporal supérieure à deux heures et les claims workload,
puis sauvegarder A et constater la convergence préparation -> disponibilité CP/UI.
La conversion Office doit encore être observée dans l'image construite. Une pause
avant livraison ne prouve pas la reprise d'une activité en cours. Le fournisseur
déterministe intégré n'est pas raccordé au catalogue Weaver ; aucune conversation
facturable n'est autorisée par ce raccord. Les autres scénarios, la plateforme
d'intégration et la qualification arc42 restent explicitement non reçus.

Bilan propre au raccord, contre la capture du checkout déjà modifié : templates et
générateur **+43/-3** lignes ; valeurs Fred/factory **+75/-0** ; contrôles de rendu
**+118/-0** ; schéma généré **+1126/-176** (inclut la projection du contrat CP déjà
implémenté). Documentation exclue. L'ajout correspond au processus manquant et
réemploie le chart, les hooks et l'héritage existants ; aucun second chemin local.

### Reprise de la réception déployée PowerPoint - 5 novembre 2026 (historique)

Cette mission avait autorisé la construction, le déploiement et la réception
navigateur sur la cible locale convenue. Cette autorisation a ensuite été retirée :
le développeur garde désormais ces opérations, conformément à la section 1.
Les faits ci-dessous sont historiques et n'autorisent aucune intervention actuelle.

**Déploiement effectué ; réception fonctionnelle reprise par le développeur à
sa demande, avant bootstrap. Aucun scénario 1 à 7 reçu.** Checkouts Fred et factory sur les mêmes HEAD
que le raccord ci-dessus, avec leurs modifications préexistantes conservées.
Cible vérifiée : contexte `k3d-fred`, namespace/base/Temporal
`fred-weaver` / `fred_weaver` / `fred-weaver`, ingress
`http://weaver.localhost:8088`. Au départ, aucune application dans le namespace
et aucune table applicative dans la base. Infrastructure existante et secrets
référencés présents ; aucune recréation de cluster ni suppression de données.

Préparation observée : sauvegarde PostgreSQL au format custom avant installation,
catalogue lisible avec `pg_restore` 17 (celui de l'hôte est trop ancien), rétention
Temporal de 72 heures, `helm lint --strict`, valeurs et dérive du schéma conformes,
trois tests `PreparationWorkerChartTests` réussis et rendu factory conforme.
Construction lancée par `make k3d-app FRED=weaver APP=fred
DIR=/home/dimi/Work/weaver/fred` depuis la factory. Les sept migrations sources
ont leurs empreintes conservées pour comparaison après initialisation.

Les fixtures synthétiques `RECEPTION-PPT-20261105-{A,B,ORG-A,ORG-B}.pptx`
portent trois diapositives, un marquage et des couleurs distincts ; leurs tailles
et SHA-256 sont conservés pour corrélation avec CP, worker et stockage.
Aucun scénario utilisateur 1 à 7 n'est encore validé à ce stade.

Le premier essai a échoué avant SQLx : le Job `schema-init` héritait du montage
`processing-contract` sans son volume, créé uniquement dans le Deployment.
Correction ciblée : le template Deployment monte désormais lui-même ce volume
quand `workerContract.exportFromWorkerImage` est actif ; suppression du montage
explicite dans l'exemple et les valeurs Weaver de la factory. Aucun changement
applicatif ou de migration. Delta de cette reprise hors documentation : template
**+3/-0**, valeurs/exemple **+0/-7**, test **+28/-0**, soit **-4 lignes** de
configuration/template au total. Le test vérifie les références de volumes et
l'absence de chemins de montage dupliqués dans les Deployments et Jobs.

Après correction : quatre tests `PreparationWorkerChartTests` et le test du Secret
`schema-init` réussis, lint et rendu conformes, validation Kubernetes
`create --dry-run=server` du Job et des sept Deployments réussie. Reprise par le
même Helmfile avec `DIR` et le `K3D_IMAGE_VALUES` construit, sans reconstruire les
images. Release `fred-app`, chart/application `5.0.0`, révision **2**, déployée
le 5 novembre 2026 à 11:12 CET ; sept Deployments disponibles sans redémarrage
à l'observation. SQLx 0001 à 0007 appliquées, SHA-384 identiques aux sources ;
hook runtime/capabilities réussi.

| Image | Tag réellement déployé |
| --- | --- |
| Control Plane | `k3d-e3c02a088958be8c` |
| API et worker agents | `k3d-d5ef1437f5b8223e` |
| Frontend | `k3d-de4d783094182910` |
| Knowledge Flow API | `k3d-d8ed532c15f0e0d6` |
| Knowledge Flow worker | `k3d-e68472f44ce296c8` |
| Monitor | `k3d-a2316b36d365d5b8` |

API et worker ont le même digest exécuté
`sha256:2da23a5bb0bafb1c907647774a4525d44a095d9e227722755ced3fced0babd13`.
Claims workload observés sans conserver le jeton : issuer
`http://keycloak:8080/realms/app`, audience `app`, client `agentic`, rôle
`service_agent`. Le CP retourne l'installation
`0f7b2ff0-ec9f-4d9b-b969-e580a451e089` et sa file
`capability-0f7b2ff0-ec9f-4d9b-b969-e580a451e089-fred-agents` ; les pollers
workflow et activité du worker y sont visibles. LibreOffice `24.2.7.2` est présent.
La tentative de vérification directe de conversion s'est arrêtée avant conversion
car le script de diagnostic importait `fitz`, absent de l'image ; cela ne prouve
pas un défaut de la capability. Conversion réelle et aperçus restent non vérifiés.

Le navigateur a atteint Keycloak, puis l'écran de bootstrap connecté comme
`admin`. Aucun bootstrap, acceptation des CGU, agent de test, préparation,
conversation, appel d'inférence, contrôle de droits ou nettoyage fonctionnel
n'a été effectué. L'utilisateur reprend la réinstallation, le bootstrap et
l'ensemble de la réception. Le cluster est laissé déployé ; aucun reset,
effacement, commit ou push. Les fixtures et la sauvegarde sont conservées hors
checkout dans `../sauvegardes/reception-ppt-20261105/`. Leur existence ne constitue
pas une réception ; une réinstallation peut changer l'UUID et la file Temporal.

Correction ciblée après le retour `make test` du développeur : le contrôle CP
des aperçus PowerPoint construisait directement son en-tête d'authentification,
ce que le garde-fou `test_no_outbound_path_builds_an_authorization_header_of_its_own`
refusait. Le test reste inchangé. `WeaverCapabilityAuthorizer` réutilise désormais
`static_person_provider`, comme l'accès privé à l'historique, et désactive
l'authentification par défaut du client HTTP pour conserver le bearer utilisateur.
Le test des aperçus couvre `Bearer` et `bearer`, un client préconfiguré avec une
autre authentification, et le refus d'une référence étrangère ou obsolète.
Échec initial reproduit ; les fichiers `test_outbound_credential_paths.py` et
`test_capability_platform_ports.py` passent ensuite : **54 réussis**, sockets
interdits. `make code-quality` dans `libs/fred-runtime` est conforme, analyse de
types sans erreur ni avertissement. Delta propre à cette correction : production
**+5/-1**, tests **+7/-4** ; modifications voisines conservées. La suite complète
n'a pas été relancée et aucun build d'image, déploiement, commit ou push n'accompagne
cette correction. La réception fonctionnelle reste à la main du développeur.

### Tiroir Swift du modèle commun PowerPoint - 5 novembre 2026 (local, non reçu)

Base : branche `weaver`, HEAD `394a9150f7e5c6ac6abeb803775ca2a0a16377e8`,
checkout déjà modifié par les lots acceptés. Référence UI : Swift
`3d18384205a469f691bbf3ca3cb697911bc6b257` et les deux captures fournies.
Le checkout Swift courant ne contenait plus ces panneaux ; leur source Git a
été utilisée. Aucune borne de fusion déplacée, aucun commit ni push.

`FeaturesPage` retrouve l'engrenage Swift dans sa colonne Réglages, exclusivement
sur l'offre `ppt_builder`. La navigation Weaver par pod reste en place.
`CapabilityPlatformDrawer` et `PptBuilderPlatformPanel` reprennent le parcours
Swift : upload immédiat, template courant/intégré, état du remplacement, résumé,
`PatternReviewDialog`, PDF, aide, corrections à la fermeture, relance et
confirmation de réinitialisation. `TemplateGuideLink` et les composants/CSS Swift
sont réutilisés ; `OrganizationPowerPointTemplate`, son raccord au-dessus du
tableau et ses traductions inutilisées sont supprimés. Le formulaire agent reste
séparé. `PptBuilderVisionSettings` reste à sa place, verrouillé avec l'explication
Weaver existante. Aucun appel d'inférence hors tour ajouté.

La permission d'écriture de l'organisation remplace le rôle plateforme dans le
tiroir. Les arguments RTK et les routes incluent organisation/espace et pod ; les
aperçus reçoivent la route de l'offre. Une revue ouverte conserve le fichier
qu'elle corrige et refuse une sauvegarde si le modèle effectif a changé. Les
corrections restent affichées si la sauvegarde échoue.

**Schéma des fichiers conservé.** Lecture ciblée de 0006/0007, du dépôt, de
l'acceptation, de la confirmation et de la résolution : provenance organisation,
instance et pod, capability `ppt_builder`, candidat distinct de l'effectif et
préparation persistée sont cohérents avec le périmètre décidé. Les migrations
0001 à 0007 sont identiques à l'instantané initial ; aucune réécriture.

**Manque concret raccordé :** 0006/0007 ne stockaient pas les corrections du
modèle commun, notamment celles du template intégré sans fichier. La migration
additive `0008_powerpoint_template_settings.sql` crée uniquement ces réglages
organisation/pod, avec capability fixe, JSON validé par la bibliothèque, fichier
effectif facultatif, contraintes de rattachement et effacement lors du remplacement,
de la réinitialisation ou de la suppression de l'organisation. Aucun original ni
résultat de préparation existant n'est transformé. Le CP projette les corrections
communes dans le contexte admis ; les corrections propres de l'agent gardent leur
priorité. Les valeurs communes fournies par un client sont neutralisées par la
validation de la bibliothèque.

Le CP expose la lecture courant/candidat et l'écriture des réglages sous
`powerpoint-template/settings`, et la relance sous `powerpoint-template/prepare`.
La relance réutilise l'intention durable et le worker existants ; le résultat
courant reste utilisable jusqu'au succès. Pas de nouvelle orchestration, stockage
ou version métier. Validation de configuration et projection de préparation
réutilisent les fonctions existantes, étendues pour ces consommateurs.

Contrôles locaux :

- `make code-quality` : CP, frontend, bibliothèque PowerPoint et runtime conformes.
  Le warning Basedpyright préexistant sur `tests/builder_decks.py` reste présent.
- Frontend : 59 tests réussis dans les sept fichiers ciblés (page, navigation par
  pod, tiroir, panneau commun, formulaire agent, analyse et routage/cache RTK).
- Bibliothèque : `tests/test_builder_capability.py`, 19 réussis.
- Runtime : `tests/test_capability_platform_ports.py` et
  `tests/test_outbound_credential_paths.py`, 58 réussis ; warning LangChain beta
  préexistant. Python exécuté avec `--disable-socket --allow-unix-socket` : aucun
  réseau ; les sockets Unix sont nécessaires à la boucle asyncio.
- CP : `cargo test --test openapi`, 17 réussis. OpenAPI CP et capability exportés
  sans serveur, puis clients TypeScript régénérés depuis ces sources.
- Comparaison à l'instantané initial : production +746/-228 lignes (dont 370
  lignes de panneau Swift restauré), migration +42/-0, tests +435/-14,
  clients générés +87/-12. Documentation exclue ; travaux voisins non attribués.

**Limites et réception développeur :** aucun accès cluster, démarrage de service,
déploiement, migration sur base ni navigateur. L'exécution SQL de 0008 en base
neuve et en mise à niveau reste à valider ; le diagramme ER nécessitant PostgreSQL
n'a pas été régénéré. Les tests locaux ne prouvent ni la réception visuelle ni le
parcours complet. Après déploiement par le développeur : comparer les captures
Swift en FR/EN, déposer/remplacer puis observer préparation/échec/relance, corriger
et rouvrir les slides (intégré et uploadé), réinitialiser, vérifier deux pods et
deux organisations, les permissions et la priorité du modèle propre à l'agent.
## 13. Réconciliation des backports #3472 et #3473 - 5 novembre 2026

`origin/weaver` a reçu `1a42bb838` (#3472, depuis #3470) et `df5c45c9b` (#3473,
depuis #3471), alors que le merge local `394a9150f` contenait déjà ces deux commits
Swift. La borne Swift reste `3d18384205a469f691bbf3ca3cb697911bc6b257` : elle vient
de ce merge, pas des backports. Le code du CLI, le Makefile et `test_migrations.py`
sont identiques des deux côtés. Le texte du backport annonçant la borne `059ae1c91`
et #3473 non intégré décrivait l'état avant réunion ; il est remplacé par cette section.

Résolutions, examinées par rapport aux deux parents :

- **Trivy** : la fusion automatique doublait `Upload Trivy report`, avec le même nom
  d'artefact. Une seule étape reste, à la position du backport : juste après le scan,
  avant le contrôle d'import et la licence/SBOM. `fred-agents` reste dans les preuves
  de licence et SBOM, avec le délai de 15 minutes.
- **Downgrade** : `test_migrations_downgrade.py` garde le passage par étapes et le
  refus de `-1` sur une vraie base. Le retour traversant plusieurs révisions, visé par
  #3473, reste couvert par `test_downgrade_runtime_to_exact_older_revision`.
- **Notes opérateur** : `3469-trivy-sbom-timeout.md` réunit les deux textes.
  `weaver-exact-agent-migration-downgrade.md` est la seule note du downgrade ;
  `target-runtime-capability-downgrade.md`, non publiée et redondante, est retirée.

Preuves locales, sans recouvrement entre elles : `test_migrations_downgrade.py`
(fred-agents) **1 réussi**, `test_migrations.py` (fred-runtime) **11 réussis**,
`test_select_docker_images.py` **20 réussis**, YAML du workflow parsé. GitHub Actions
et rollback sur installation isolée non exécutés.

**Résolu le 6 novembre :** `weaver-powerpoint-file-ownership.md` a reçu sa section
`## Prerequisites` et `make migration-check` passe sur sa base par défaut `origin/swift`.


## 14. Tranche Swift vers 89baab5b6 - 6 novembre 2026

Cible figée : `89baab5b6`. Base Weaver : `7c29aede0`. Borne de départ : `3d1838420`.
Branche : `merge/swift-89baab5b6`. Quatre étapes, dans l'ordre de l'ascendance Swift. `f951e3438`,
`6f3b28478`, `6fae3a708`, `174a38854`, `9cdd1ac99`, `ad5a1d2d3` et `bef0098f4` (fetch du 7 novembre),
arrivés ensuite, restent hors de cette tranche.

| Etape | Commits Swift | Etat |
| --- | --- | --- |
| 1 | `b00551906` (#3460) tabulaire | Mergée en `d294b0e4e`, poussée sur `weaver`, non reçue |
| 2 | `a2ebfe48c` (#3476) Azure APIM | Mergée en `4830c58bc` sans changement de fichier, poussée sur `weaver`, non reçue |
| 3 | `d9eb3738f` (#3453), `303b7456e` (#3483) | Mergée en `f06d57650` et `e9d18c16b`, non reçue |
| 4 | `507866562` (#3475), `89baab5b6` (#3455) | Mergée en `735d818ef` et `04aee8fbb`, non reçue. Tranche vers `89baab5b6` terminée |

### Etape 1 : décisions

- **Repris :** colonnes compactes (`categorical_values`, bornes seulement sur les numériques), `table_names`,
  message explicite pour zéro ligne, diagnostic SQL limité aux tables montées, types temporels Excel, détail
  des échecs dans le panneau de traces, textes d'erreur Fred et prompt tabulaire.
- **Adapté à Weaver :** `read_query` devient `query_tabular_documents`, y compris dans `toolFailureTrace.ts` ;
  `TabularColumnSchema` reste dans `fred_knowledge` et perd `has_two_values` ; la note opérateur ne parle plus
  de données déjà ingérées.
- **Exclu volontairement :** `attachment_uids`, `owner_filter`, `team_id`, `include_*_scope` et
  `document_library_tags_ids` en arguments d'outil, car le périmètre vient du contexte serveur. Les corps de
  réponse HTTP restent hors des logs, et les messages SQL hors du log de rejet.
- **Suppressions Weaver maintenues :** `docs/swift`, `openspec`, le prompt `basic_react_sql_expert`,
  `tests/services/test_tabular_service.py` et `tests/test_mcp_v2_inventory.py`. Leurs cas de comportement sont
  repris dans `test_weaver_tabular.py` et `validation/knowledge_flow`, sans les assertions sur les libellés.
- **Conservé tel quel :** `has_two_values` reste lu par `tabularTrace.ts`, comme dans Swift. Ce champ est
  sans objet sur une installation neuve.

### Etape 1 : preuves locales, sans déploiement

- Knowledge Flow API : 186 réussis. Worker Excel : 186 réussis. Runtime ciblé : 106 réussis. Frontend ciblé :
  382 réussis. Ces suites ne prouvent pas le parcours déployé.
- `validation/knowledge_flow`, avec `--confcutdir=validation/knowledge_flow` : 57 réussis et 1 échec dû au
  blocage réseau ; ce dernier test réussit en autorisant seulement `127.0.0.1`.
- `make code-quality` : Knowledge Flow API et worker, `fred-knowledge`, runtime, frontend. `make migration-check`
  valide 32 déclarations. Tests de `fred-capability-mcp` non exécutés : ce paquet n'a pas de dossier de tests.

### Etape 1 : à recevoir sur déploiement

- Un agent décrit tout un classeur puis une seule table ; la colonne montre `categorical_values`.
- Une colonne de date Excel nouvellement ingérée a un vrai type temporel en SQL.
- Une requête sans résultat répond « 0 ligne », sans erreur.
- Une colonne inexistante produit un diagnostic qui ne cite que les tables de la requête, et le panneau de
  traces montre les arguments envoyés et la cause.

### Défauts d'outillage corrigés après l'étape 1

- `make generate-openapi` de Knowledge Flow ne touche plus de base : `VectorSearchService` ouvre son vector store
  à la première recherche, comme son modèle de reranking. L'API démarre donc sans vector store joignable, et la
  première recherche répond 503 `corpus_not_ready`.
- `make test-knowledge-flow-contracts` n'exige plus de Control Plane et n'autorise que `127.0.0.1` : 58 réussis.

### Etape 2 : décisions

- **Besoin Swift :** authentifier la découverte des modèles derrière Azure APIM. #3476 le fait dans le
  `catalog.py` du pod, que Weaver a supprimé.
- **Déjà couvert par Weaver (`8dc5dbc77`, `03e6f0d14`) :** le Control Plane possède les sources ; une source
  APIM utilise un inventaire déclaré. Le pod garde ses secrets Entra et de passerelle pour le seul appel
  d'inférence, et `test_model_discovery.py` vérifie qu'il ne fait aucune découverte.
- **Exclu volontairement :** `catalog.py`, le test Swift de découverte par le pod, la note de migration et
  `openspec/changes/azure-apim-model-discovery`.

### Etape 2 : preuves

- Le merge `4830c58bc` a pour parents `03e6f0d14` et `a2ebfe48c`, et son arbre est identique à celui de
  `03e6f0d14`. Il n'enregistre que l'ascendance. Aucune compilation ni aucun test n'a été lancé pour ce merge.
- **Non prouvé :** rien n'a été testé sur une vraie passerelle APIM ou un vrai tenant Entra.

### Etape 3 : décisions

- **Repris de `d9eb3738f` :** test React déplacé en suite d'intégration, étape CI et README. Les règles Makefile de
  Weaver qui préparaient les caches avant `make test` sont retirées, car elles répondaient au même besoin.
- **Repris de `303b7456e` :** consignes de référence exacte pour `read_document`, `summarize_document` et
  `search_documents`, et retrait du NUL à l'écriture des documents modifiables.
- **Adapté à Weaver :** `uid` reste le champ des résultats de recherche. `document_uid` reste seulement l'argument des outils.
  L'historique note le NUL `[U+0000]`, sans la métadonnée `history_text_normalization`, qu'aucun code ne lit.
- **Exclu volontairement :** le renommage `hits[].uid`, qui retirerait au panneau de traces le lien vers le document ;
  `docs/swift` et `openspec`.

### Etape 3 : preuves locales rapportées, sans déploiement

- Frontend : `make test` sans caches, 398 réussis et 1 ignoré (archive iframe, cache absent). Intégration : 1 réussi.
- `fred-core` historique : 40. Accès aux documents : 81. Documents : 66. Document modifiable : 96. Runtime `-k history` : 120.
- PostgreSQL 16 jetable : 3 réussis, 0 ignoré. `make code-quality` conforme sur les composants touchés.
  `make migration-check` : 34 déclarations.
- **Non prouvé :** aucun parcours déployé ni vrai modèle ; un NUL dans une édition navigateur ou une clé JSON ; le
  checkpoint LangGraph (`metadata_json` en JSONB) n'a pas été tracé.
- **Limite :** `weaver` n'a pas de CI, donc l'intégration React et l'installation iframe ne tournent que sur lancement manuel.

### Etape 3 : à recevoir sur déploiement

- Une recherche suivie d'un résumé trouve le bon document du premier coup.
- Dans les traces, une source de recherche garde son lien « ouvrir le document ».
- Un Markdown contenant un NUL s'ouvre comme document modifiable, le retrait est annoncé, et la conversation reste correcte
  après rechargement.

### Suite du rattrapage : besoins confirmés le 7 novembre

Les tests sont regroupés en une campagne complète jusqu'à k3d, une fois le rattrapage terminé. Le développeur confirme :
le modèle Zabbix (demande client, compatibilité Weaver exigée), les SBOM d'images (`9cdd1ac99`), le wiki d'équipe
(`bef0098f4`) et, en priorité, l'affichage des pièces jointes (`ad5a1d2d3`). Leur forme dans Weaver reste à décider
commit par commit.

### Etape 4 : décisions

- **Repris de `507866562` :** le modèle Zabbix, sans modification, et son README corrigé pour décrire les endpoints réels de Weaver.
  Le Control Plane n'expose pas de `/metrics`.
- **Exclu volontairement :** le guide SIEM de `89baab5b6`, qui décrit OpenFGA et des événements d'audit Swift. Un besoin SIEM
  demanderait un guide court écrit depuis les événements réels de Weaver.
- **Défaut corrigé en passant :** le Service de métriques du chart `fred` n'était jamais créé, car il exigeait une clé absente du chart
  (`5f29e4ba6`, `13cc6d4bb`). `metricsService` décide seul, et `values.yaml` lie les exporteurs concernés à `0.0.0.0`.

### Etape 4 : à recevoir

- Avec `fred-agents` activé, `kubectl get service` liste `fred-agents-metrics`, `knowledge-flow-backend-metrics` et `knowledge-flow-worker-metrics`, et `/metrics`
  répond depuis le cluster.
- **Non prouvé :** l'import du modèle dans un vrai Zabbix 7.0, et un vrai Prometheus.

### Rattrapage après `89baab5b6`

| Commit Swift | Etat |
| --- | --- |
| `f951e3438` (#3487) oauthlib | Mergé en `6aefa8684` sans changement de fichier : aucun verrou de Weaver ne le contient |
| `6f3b28478` (#3485), `6fae3a708` (#3486) UI-PORT | Mergés en `e8cb6dad9` et `d34f2f7e6`, non reçus |
| `174a38854` (#3498) test | Mergé en `57925ec07`, nettoyage automatique seul (`6c93c393f`) |
| `9cdd1ac99` SBOM | Mergé en `d0495bad0`, simplifié, non reçu |
| `ad5a1d2d3` (#3490) pièces jointes | Mergé en `298008ebd`, conçu pour Weaver, non reçu |
| `bef0098f4` (#3491) wiki | Mergé en `81198bc56`, adapté au wiki du Control Plane, non reçu |

- **Limite acceptée :** `metricsService.enabled: false` retire le Service, mais l'exporteur reste à l'écoute dans le pod.

### UI-PORT : décisions

- **Repris :** icônes, tokens et rayons, `::selection`, focus de `SettingsModal`, recherche prête à la souris, placement de `TaskDetailPopover`, rail et
  tiroirs du chat, puce d'agent supprimé.
- **Weaver garde :** logique, droits, espaces, contrats, seuil 1200 de `useChatNavPanel`, marge `--spacing-l`, `sendHint`, libellé « New conversation ».
- **Exclu volontairement :** `TeamDescriptionReminder` (champ absent du contrat), mode hover de `TaskIndicator` (aucun usage, retiré en `a79951012`), section
  « Pièces jointes » du tiroir (anticipation), notes de version Swift.

### UI-PORT : à regarder pendant la campagne

- Tiroir et barre du chat en FR et EN, y compris un agent supprimé.
- Les thèmes en clair et en sombre, surtout la sélection de texte et les rayons.
- Focus au clavier : `SettingsModal`, recherche des agents ; `TaskDetailPopover` seulement sur `dev/tasks`.
- Chat avec panneaux ouverts : badge et séparateur du rail, repli du panneau de navigation.

### SBOM : décisions et réception

- **Repris :** les rapports CycloneDX avec CVE aux tags de release, et `make sbom`.
- **Adapté à Weaver :** Trivy local uniquement par son conteneur épinglé, comme le scan de vulnérabilités existant ; usage court dans `deploy/README.md`.
- **A recevoir :** `make sbom` sur des images construites, y compris `knowledge-flow-worker-pymupdf`, et l'artefact d'un vrai tag de release si le CI est activé pour `weaver`. Le chemin de publication d'un tag de release combine push, sortie locale et provenance : à tester localement avant le premier tag, avec un builder docker-container et un registre local. Si cette étape échoue, la release n'est pas créée, et des images peuvent déjà être publiées.

### Pièces jointes : décisions et réception

- **Repris :** puces en lecture seule dans la bulle, apparence `tonal` de `Chip`, bouton d'envoi grisé sans texte.
- **Conçu pour Weaver :** l'affichage dérive de la liste du Control Plane, par la règle qui sépare déjà fichiers envoyés et en attente. Aucun contrat, écriture runtime ni donnée d'historique.
- **Exclu volontairement :** la liste déclarée par le navigateur, `TurnAttachment`, sa copie dans l'historique et le code de reprise associé.
- **Retiré :** l'envoi de fichiers sans texte, que le runtime refuse.
- **Limites acceptées :** l'association repose sur les dates. Un fichier ajouté pendant une réponse peut s'afficher après rechargement sur le tour en cours. Un fichier ajouté juste avant une réponse à une question de l'agent peut n'apparaître que dans le tiroir. Un fichier supprimé disparaît de la bulle.
- **A recevoir :** deux fichiers et un texte : les puces s'affichent aussitôt et après rechargement, et le composeur se vide. Un fichier ajouté au tour suivant s'affiche sur ce tour. Sans texte, le bouton reste grisé et Entrée n'envoie rien. Pendant une réponse, le composeur vide affiche Stop à côté d'Envoi grisé : à regarder.

### Wiki : décisions et réception

- **Repris :** arbre replié et mémorisé, dernière page rouverte, titre, parent et suppression dans l'éditeur, recherche et ancrage du `Select`.
- **Adapté à Weaver :** clé par utilisateur et par espace, identifiant de page plutôt que slug. L'URL porte toujours la page : déplacer une page ne peut pas fermer un brouillon.
- **Limite acceptée :** titre et parent sont enregistrés avant le texte. Un conflit sur le texte laisse le renommage appliqué. Une écriture atomique demanderait un changement de contrat.
- **A recevoir, avec la recette Wiki de la section 15 :** à la première visite, l'arbre est replié et une page à relire reste accessible par le filtre. La dernière page se rouvre, par utilisateur et par espace. Renommer et déplacer depuis l'éditeur, y compris en cas de doublon et de conflit, sans perdre le brouillon. Après une suppression, on ne reste pas sur la page supprimée. Le retour arrière reste normal.
- **Select :** recherche au clavier sur un long wiki, et comportement inchangé sur les autres écrans.

### A trancher en fin de rattrapage

- La CLI de `fred-runtime` lit encore `app.metrics_port`.
- `TaskIndicator` et `TaskDetailPopover` ne sont utilisés par aucun écran de production : leur seul consommateur est `TaskPlayground`, page limitée au mode développement (`dev/tasks`). Leur retrait est à décider.
- Inventaire des écrans qui utilisent encore `legacyControlPlane`, avant la campagne : un écran sans backend paraîtrait en panne pendant les tests.


### Wiki — premier lot implémenté, recette différée (7 novembre)

Base Weaver `404237a02`, branche `codex/weaver-conversation-files` ; source Swift
examinée `d7e7f99e7` (parcours Wiki, service et store). Aucun merge ni changement
de borne Swift intégrée. Les modifications PowerPoint/Deep préexistantes restent
conservées ; les raccords partagés sont limités au routeur, au nettoyage, au client
généré, au README et à la classe `TeamWikiAdapter`.

- **Repris :** arbre sur quatre niveaux, éditeur MDX et protection du brouillon,
  règles, noms uniques entre voisins, historique paginé de 50 révisions, diff,
  restauration comme nouvelle révision, validation éditoriale et publication HITL.
- **Adapté :** `0015_team_wiki.sql` et `src/wiki/` placent pages/révisions dans le CP
  PostgreSQL ; les propositions sont des révisions, pas une troisième autorité.
  Espace personnel ou équipe canonique, sans repli d'un projet sur son équipe.
  Droits `read`/`write` et autorisation des offres `team_wiki` réutilisés.
- **Confidentialité :** proposition créée par un runtime délégué, liée à la
  conversation privée et lisible/publiable seulement par son propriétaire.
  Retirer la conversation ferme immédiatement l'accès aux propositions privées ;
  leur purge utilise sa rétention. Les publications survivent à la conversation.
  Une suppression d'équipe/organisation purge son Wiki avec le worker existant.
- **Hors lot :** quotas éditoriaux globaux, catalogue de fichiers, pièces jointes,
  exports, miroir Markdown, indexation et migration des données Swift.
- **Chemins remplacés :** consommateurs UI et port agent vers `/spaces/{id}/wiki` ;
  suppression des hooks/cache Wiki manuels du client legacy et des lectures legacy
  séparées pour les noms d'auteurs et d'agents. Le vieux fichier TypeScript généré
  conserve ses définitions inactives : sa source OpenAPI n'est plus dans ce checkout ;
  il n'a pas été modifié à la main.

Contrats CP/TypeScript régénérés. Compilation, formatage, lint et analyse de types
ont été exécutés ; les fixtures existantes sont raccordées au nouveau contrat,
sans nouvelle campagne de tests. Aucun service, déploiement, sous-agent ou commit.
Les migrations n'ont pas été appliquées. Le diagramme SQL reste à régénérer avec
sa procédure PostgreSQL : celle-ci démarre un service et n'est pas autorisée ici.

Qualité : `make -o dev code-quality` sur le CP ; `make code-quality` sur le frontend ;
`UV_NO_SYNC=1 make -o dev code-quality` sur le runtime. Les dépendances installées
ont été réutilisées. La capacité Wiki utilise l'environnement du runtime pour ses
outils ; son analyse de types passe avec `basedpyright --venvpath ../../fred-runtime`.
La référence REST A12 a été régénérée et vérifiée sans PostgreSQL. Le contrôle de
liens du README signale un lien **préexistant** vers l'ancre absente
`09-quality.md#organization-supervision-read-budget`, laissé hors de ce lot.


**Recette restant à autoriser :**

1. Appliquer toute la chaîne SQL sur installation fraîche, puis vérifier les
   contraintes, conflits concurrents et reprise des lots de nettoyage.
2. En personnel et en équipe : créer/éditer/déplacer/renommer/supprimer une feuille,
   garder l'URL après renommage ; refuser doublon, cycle et cinquième niveau.
3. Préserver le brouillon en navigation et conflit ; lire les règles absentes sans
   écriture, enregistrer puis vider volontairement les règles sans réinsérer de modèle.
4. Lire plus de 50 révisions, afficher les auteurs, comparer, restaurer et valider
   la bonne révision ; refuser une validation devenue périmée.
5. Lecteur : consulter et approuver une proposition d'agent, sans édition directe ;
   rédacteur : éditer/valider. Refuser les accès étrangers, y compris à une
   proposition connue d'un autre membre/rédacteur et depuis un projet voisin.
6. Agent : lecture complète avant remplacement, proposition privée, refus/accord
   HITL, publication unique avec marque de revue ; aucune écriture des règles.
7. Désactiver/réactiver sans perte. Une admission nouvelle respecte la révocation ;
   un tour déjà admis conserve son autorité, sous réserve des ressources encore actives.
8. Supprimer la conversation avant/après publication et purger après rétention ;
   vérifier l'expiration des propositions ainsi que la suppression équipe/organisation.
   Refaire ensuite la recette PowerPoint/Deep sur ce même état intégré.

## 15. Intégration locale fichiers, Deep et premier Wiki - 7 novembre 2026

La consolidation part de `404237a02` sur `codex/weaver-conversation-files` :
`c65978740` conserve le catalogue CP, les livrables PowerPoint et le premier Wiki ;
`96ebad324` raccorde les livrables Deep à ce catalogue. Le lot est ensuite réuni,
sans rebase, avec Weaver local `da0fe9f558be984fbb42e141cac2099681e930c7`, également
pointé par `merge/swift-89baab5b6`. Aucun commit n'est pris directement depuis Swift.
La borne intégrée restait alors `ad5a1d2d3` ; `bef0098f4` a ensuite été traité (`81198bc56`, section 14).

Les deux conflits textuels sont résolus en conservant cette section 14 et le
rapport du premier Wiki, puis l'icône `folder` de Weaver avec le compteur sources
plus livrables du tiroir. Les adaptations automatiques de la navigation Wiki et de
la fixture runtime sont relues. Les pièces jointes des messages restent dérivées
de la liste CP, sans écriture dans l'historique ; l'envoi sans texte reste refusé.
Le champ `uid` des résultats de recherche et son consommateur de traces sont
préservés. Aucun retour de `docs/swift` ou d'`openspec`.

Les routes Wiki utilisent l'espace canonique personnel ou équipe, sans repli du
projet sur l'équipe. Les propositions restent privées à leur conversation ; les
révisions publiées lui survivent. Les livrables utilisent les contenus immuables,
les écritures conditionnelles, les compteurs de quota et le nettoyage existant du
CP. Les sources de conversation restent seules dans la liste des pièces jointes
et dans le parcours d'ingestion. Aucun nouvel arbitrage de droits ou de rétention.

Les migrations `0001` à `0013` sont identiques à Weaver et à la référence locale
`origin/weaver`. `0014_conversation_files.sql` et `0015_team_wiki.sql` n'ont aucune
collision et gardent leurs numéros. La chaîne complète a été initialisée par
`cargo run --quiet --locked -- initialize-schema` dans un PostgreSQL dédié jetable,
puis vérifiée par une seconde initialisation et comparaison des 15 empreintes
SQLx SHA-384 avec les sources. La ressource a été supprimée, sans accès aux bases
applicatives. Cela complète l'état historique du premier lot ci-dessus ; la recette
fonctionnelle de ses contraintes et parcours reste à faire.

Les clients CP/runtime ont été régénérés avec `make update-control-plane-api
update-runtime-api`, ainsi que le schéma de configuration CP et les références
SQL/API par `make -C docs/architecture generate`. Contrôles réussis :
- CP : `make -o dev code-quality` (rustfmt, Clippy et runtime Rust embarqué).
- Frontend et producteur `libs/frontend` : `make code-quality`, avec Node 24.22.2.
- SDK, runtime et PowerPoint : `UV_NO_SYNC=1 make -o dev code-quality`.
  PowerPoint conserve l'avertissement préexistant `reportUnsupportedDunderAll`
  de `tests/builder_decks.py:930` (zéro erreur).
- Wiki : lint, imports, formatage, Bandit et détection de secrets via le Makefile
  avec l'environnement runtime ; typage par
  `../../fred-runtime/.venv/bin/basedpyright --venvpath ../../fred-runtime`.
  L'essai avec l'environnement Wiki absent, puis sans chemin explicite pour le
  typeur, échouait sur l'outillage/imports ; le contrôle corrigé passe.
- `make -C docs/architecture check` : références, schéma et rendu des diagrammes.
- `git diff --check`, également sur l'index de fusion.

Aucun test fonctionnel, lancement applicatif, push ou déploiement n'a été exécuté.

**Relais du prochain lot Wiki :** repartir du Wiki réel de Weaver (`src/wiki/`,
`0015_team_wiki.sql`, routes `/spaces/{space_id}/wiki`, `TeamWikiAdapter` et
consommateurs frontend CP). Comparer le prochain delta Swift à ces contrats, sans
réintroduire le backend legacy, ses droits ou sa persistance. Le portage antérieur
n'a pas déplacé la borne Swift. La recette k3d commune fichiers/PPTX/Deep/Wiki reste
à faire, notamment confidentialité, conflits de révision, publication HITL,
suppression/rétention et pièces jointes par message.

## 16. Integration Swift du 9 novembre 2026

Fusion locale autorisée sur `weaver` dans `/home/dimi/Work/weaver/fred`, après
explication de la valeur produit et confirmation de conserver ces améliorations.
Références figées après fetch : base Weaver `e49f4cb79adf4b7727fca658232c1a43b8468917`,
ancienne borne Swift `bef0098f4fa37f21121f023725394c212b012604` (second parent du merge
`81198bc56`), cible `3ad093d3459768f0dec4d1deafdf8b83422f6e38`. Cette section appartient
au commit de fusion dont les deux parents sont la base Weaver et cette cible Swift.

| Source nouvelle | Décision et apport |
| --- | --- |
| `28d9ee7c7` (#3493) | Adaptation : les précisions envoyées pendant une réponse sont des messages persistants, visibles dans le fil avec leur état. ReAct/Deep les consomment à une frontière de modèle après persistance ; sinon elles ouvrent le prochain tour, y compris à la réouverture. Graph utilise ce repli. Une attente HITL conserve la priorité. |
| `74a2460f3` | Reprise directe du workflow : les PR en brouillon ne déclenchent plus de builds Docker ; leur passage prêt pour revue déclenche les images concernées. Exécution manuelle inchangée. Documentation portée dans le CONTRIBUTING racine. |
| `3ad093d34` | Exclusion des obligations Swift d'issue/Epic/PR et de nommage de branche : elles contredisent la collaboration incrémentale Weaver et ne sont pas nécessaires aux améliorations produit. AGENTS.md Weaver conservé. |

L'ancienne file, ses battements et son UI séparée sont remplacés par l'historique.
Les références à docs/swift, OpenSpec et au test d'ancien contexte agent ne sont
pas restaurées. Les différés des sections précédentes restent différés ; ce merge
n'établit aucune réception de ces lots.

Adaptations Weaver : `space_id` canonique contrôlé sur le message et ses retries,
autorité du tour et fin de délégation conservées, provenance et cascade PostgreSQL
inchangées, pièces jointes issues du catalogue CP, titres CP et configuration
refusée conservés. Les réponses HTTP et notifications tardives sont gardées par
l'identité et le contexte courant. La reprise d'un message conserve le brouillon
non envoyé. Ralph embarqué ne gagne pas de support steering.

Nouvelle révision runtime `d0e1f2a3b4c5` après `c9d0e1f2a3b4` : identité/état et
index sur `session_history`, suppression de `runtime_turn_steering`. Aucune migration
existante réécrite, aucune migration CP ajoutée. Le downgrade PostgreSQL est refusé
pour ne pas restaurer une table sans propriété de conversation. Installations
neuves seules ; aucune base applicative modifiée. Voir la
[note opérateur](deploy/release-notes/changes/weaver-in-thread-steering.md).

Contrats régénérés depuis le code réuni : `UV_NO_SYNC=1 make -o dev generate-openapi`
dans `libs/fred-runtime`, puis `npx --no-install @rtk-query/codegen-openapi
src/slices/runtime/runtimeOpenApiConfig.json` dans le frontend avec Node 24.22.2.
Le client conserve les contrats Weaver, remplace `steering_turn_id` par
`pending_message_id` sur le protocole Python et reçoit le message durable à l'envoi.

Vérifications locales ciblées :
- Runtime : `.venv/bin/pytest -q --disable-socket --allow-unix-socket
  tests/test_turn_steering.py tests/test_graph_steering.py tests/test_history.py
  tests/test_migrations.py tests/test_delegated_foreground_route.py` : 83 réussites,
  un avertissement LangChain beta. SQLite/mocks, dont deux connexions concurrentes,
  chaîne de migrations et nettoyage de délégation. Le blocage simulé avant première
  trame est placé dans l'initialisation du stream, après admission HTTP désormais
  synchrone, afin de conserver son scénario de déconnexion.
- Routes : sélection `managed or space or pending_opening or stream` dans
  `test_agent_app.py` et `test_delegated_foreground_route.py` : 35 réussites et le
  scénario ci-dessus initialement en échec, corrigé puis couvert dans les 83.
  Ces nombres se recouvrent et ne constituent pas deux suites cumulables.
- Frontend : `npx vitest run src/rework/core/hooks/useChatSse.test.tsx
  src/rework/components/pages/ManagedChatPage/useManagedChat.test.tsx
  src/rework/components/pages/ManagedChatPage/toThreadMessages.test.ts` : 274 réussites.
- Qualité : `UV_NO_SYNC=1 make -o dev code-quality` dans `libs/fred-core`,
  `libs/fred-runtime`, `libs/fred-sdk`, `apps/fred-agents` ; `make code-quality`
  dans `apps/frontend` avec Node 24.22.2.

Les contrôles qualité ci-dessus passent après les dernières corrections, ainsi que
`git diff --cached --check`, la syntaxe YAML du workflow, les liens Markdown modifiés
et `libs/fred-pod/.venv/bin/python scripts/migration_guides.py check-pr --base
 e49f4cb79adf4b7727fca658232c1a43b8468917 --worktree` (deux notes valides).
Diff de production : +1 569 / −1 114 lignes, soit +455. La file et son interface
supprimées financent une partie de la persistance et des accusés de livraison ;
l'ajout net sert ce comportement accepté. Hors production : tests +1 955 / −1 404,
client généré +22 / −7, documentation et CI comptées séparément.

La réception déployée reste à faire : installation PostgreSQL neuve, mise à jour
pendant modèle/outil, réouverture, HITL, suppression et pièces jointes. Les tests
hors réseau ne prouvent ni comportement PostgreSQL en production ni latence.
Aucun service démarré, reset, benchmark, push ou déploiement effectué.

## Auto-tests d'administration

Les auto-tests d'administration proposent onze familles de contrôles, des rapports dépliables et deux contrôles manuels.

Les contrôles utilisent les droits de la personne et de l'espace sélectionné. La recherche et l'expiration passent par l'agent de diagnostic. La campagne de rôles modifie uniquement un projet temporaire et reprend son nettoyage à partir du reçu de suppression. Les parcours qui n'ont pas d'équivalent intégré sont indiqués dans les résultats ou dans la [documentation opérateur](apps/frontend/README.md#weaver-self-tests).

Vérifications locales : garde d'accès et navigation, exécution séquentielle, rapports et copie, outils de l'agent de diagnostic, refus de suppression d'un dossier non vide et reprise d'un projet par son opérateur (tests HTTP avec PostgreSQL). Aucun stockage de rapports côté serveur.

La réception k3d requiert les images locales et un compte administrateur de plateforme également propriétaire d'au moins une organisation, équipe ou projet. Les contrôles de ressources nécessitent un espace de test accessible et, pour l'isolation, un second compte. La suite de validation en ligne de commande est indépendante.


## 17. Intégration Swift du 10 novembre 2026

Mise à jour locale demandée sur `weaver`. Base Weaver figée :
`58cc2ffe4261a2fcad4d40a5276b99e1662dbdd7` ; ancienne borne Swift :
`3ad093d3459768f0dec4d1deafdf8b83422f6e38` ; cible confirmée par fetch :
`49aaea6820556c63ff4e688dbfc7f8f702cad9e9`. Cette section appartient au merge
ayant la base Weaver et la cible Swift pour parents. Le checkout Swift distinct
reste intact sur sa branche de correction Unicode ; sa branche locale `swift`
pointait encore sur `d9e1b5d82` lors de l'inventaire.

| Source nouvelle | Décision et apport |
| --- | --- |
| `1471f1ff5` (#3503) | Reprise directe du style ChatList : espace réservé à la barre de défilement et retrait du padding droit redondant. |
| `d9e1b5d82` (#3517) | Déjà couvert : le test Weaver vérifie l'absence de l'ancienne table au head, son retour aux révisions antérieures SQLite et l'isolation des arbres. Conservation intégrale de ce test et des révisions propres à Weaver. |
| `49aaea682` (#3514) | Reprise directe de l'encodage UTF-8 du nom dans Content-Disposition et des tests d'export Word/Markdown. Conservation des contrôles d'accès et des métadonnées d'auteur Weaver. |

Les notes Unicode et barre de défilement sont reprises dans
`deploy/release-notes/changes/`. Les notes Swift de cutover/rollback du steering
ne sont pas réintroduites : la note `weaver-in-thread-steering.md` porte déjà
le contrat Weaver d'installation neuve et de refus de downgrade PostgreSQL.
Aucune migration n'est ajoutée ou modifiée. Les anciens portages et réceptions
différés restent distincts ; cette fusion ne les valide pas.

Les composants existants portent les deux corrections ; aucune abstraction ni
voie de compatibilité supplémentaire. Production : +13 / -4 lignes ; tests :
+65 / -0 ; deux notes opérateur : +75 / -0, hors présent suivi.

Vérifications locales :
- Frontend : `make code-quality` avec Node 24.22.2 réussi (TypeScript, Prettier, ESLint).
- `git diff --cached --check` réussi ; aucun conflit restant dans l'index.
- Capability documentaire : `UV_NO_SYNC=1 make -o dev code-quality` réussi
  (Ruff, formatage, Bandit, secrets et Basedpyright : zéro erreur/avertissement).
- `.venv/bin/pytest -q --disable-socket --allow-unix-socket tests/test_router.py`
  dans la capability : 49 réussites, avec contenu Word/Markdown, Unicode,
  noms nettoyés, document absent et accès étranger.
- Même commande sur `tests/test_migrations_downgrade.py` dans `apps/fred-agents` :
  une réussite ; SQLite temporaire uniquement.
- OpenAPI produit depuis `apps/fred-agents` par
  `.venv/bin/python -m fred_runtime dump-openapi writable_document`, puis client
  régénéré avec `npx --no-install @rtk-query/codegen-openapi
  src/rework/features/capabilities/writable_document/api/writableDocumentCapabilityOpenApiConfig.json`
  dans le frontend : aucun changement du client versionné.
- Notes opérateur : `libs/fred-pod/.venv/bin/python scripts/migration_guides.py
  check-pr --base 58cc2ffe4261a2fcad4d40a5276b99e1662dbdd7 --worktree` : deux
  déclarations valides.

La réception navigateur reste au développeur : barre de défilement sur une liste
longue et export Word/Markdown avec titre Unicode. Le navigateur conserve sa
règle existante de nettoyage du nom téléchargé ; le correctif porte sur l'en-tête
HTTP qui empêchait certains exports. Aucun service démarré, base applicative
modifiée, push ou déploiement.

## 18. Audit Swift et reprise KPI - 12 novembre 2026

Pilote : session Codex intégration Swift/Weaver de Dimi. Mission actuelle :
conseiller, attribuer les lots et maintenir le suivi ; premier lot HTML/CI confié
au sous-assistant `port_html_ci` après le choix explicite de Dimi. Aucun merge
global, commit ou push effectué ; le pilote ne réalise pas les edits applicatifs.

### Priorité et organisation confirmées avec Dimi

Dimi demande de traiter d'abord le merge, sujet par sujet, avec des échanges
courts sur les choix de portage. La reprise KPI reste un travail ultérieur : son
inventaire ci-dessous préserve les besoins mais ne doit pas élargir le merge.
Le chantier est isolé sur `codex/merge-swift-2026-11-12`, créée depuis la base
Weaver figée ci-dessous dans un worktree dédié attaché au chat du pilote. Le
checkout Weaver courant est libéré des seules modifications de suivi du pilote ;
aucun service ni environnement de démo n'a été touché. L'AGENDA central donne le
chemin local actif pour les autres assistants.

Pour chaque sujet : exposer l'apport Swift et le comportement Weaver actuel,
recommander reprise/adaptation/report, consigner le choix de Dimi, puis confier
une mission bornée à un exécutant identifié. Le pilote vérifie le résultat et
la réception restante avant de passer au sujet suivant. Un seul propriétaire de
l'index pendant le merge ; ne pas lancer plusieurs résolveurs dans ce worktree.

Ordre de discussion proposé, ajustable par Dimi :

1. Corrections HTML et CI, reprises directes pressenties.
2. Préparation PowerPoint et contrats SDK/runtime, risque principal de divergence.
3. Pièces jointes non envoyées et brouillons du chat.
4. Suggestions d'agents de l'accueil sans OpenSearch.
5. Analytics : sélectionner les apports compatibles et documenter les reports,
   sans réactiver les dashboards pendant le merge.
6. Documentation, notes opérateur, contrats générés et vérification d'ensemble
   par rapport aux deux parents avant intégration finale dans Weaver.

Le chantier peut être interrompu entre ces décisions. Un simple index en conflit
n'est pas un jalon validé : chaque interruption doit laisser les choix, chemins
traités, conflits restants et prochaine action explicites. Si Weaver avance en
parallèle, réexaminer son nouveau delta avant la livraison finale ; ne pas déplacer
silencieusement les SHA de cette tranche. Aucun merge lancé à ce point de préparation.

### Références figées et avis de merge

- Base Weaver : `f6e5af8e3239c56cf4b3b86847347abd237c2a80`.
- Borne Swift intégrée : `49aaea6820556c63ff4e688dbfc7f8f702cad9e9`, vérifiée comme
  second parent de `629b5f886d702003cc8ca48362746822244954e7` et merge-base actuelle.
- Cible Swift : `222bc60acda8b806c2186bd241dfbf3db180fac2`, confirmée par fetch ;
  branches locale `swift` et `origin/swift` alignées au moment de l'audit.
- Sept commits entrants, 413 fichiers modifiés dans le delta Swift.

Avis : intégrer cette ascendance dans un lot dédié, avec décision par comportement.
Conserver les suppressions du CP Python et d'OpenFGA, préserver les contrats Rust
et enregistrer les besoins analytics différés. La réactivation des dashboards
est un lot distinct. Pas de résolution globale ours/theirs ni de restauration
d'un backend historique pour satisfaire un import UI.

Si un nouvel écran Swift exige des endpoints absents, différer son raccord comme
un ensemble cohérent et conserver sa référence source ; ne pas ajouter de hooks
fictifs dans le client généré. Les composants visuels compatibles peuvent être
repris après vérification de leurs consommateurs. Les scripts de backfill Swift
ne sont pas requis pour les installations neuves Weaver.

La simulation `git merge-tree --write-tree --name-only --messages <base> <cible>`
n'a modifié ni index ni checkout : 183 chemins en conflit, dont 76 modify/delete,
68 content, 29 file location, huit rename/delete et deux add/add. Ces nombres
dépendent de la détection de renommages de Git, pas du nombre de décisions produit.
Attention : Git propose à tort des fichiers analytics dans
`apps/knowledge-flow-worker/knowledge_flow_worker/core/processors/input/email_processor/`,
et un modèle de préparation dans `fast_text_processor/`. Rejeter ces placements
et examiner aussi les nouveaux fichiers ajoutés sans conflit dans des arbres retirés.
Les notes opérateur proposées sous `deploy/release-notes/changes/` demandent,
elles, une adaptation au comportement réellement intégré.

| Commit entrant | Décision finale de portage pour cette tranche |
| --- | --- |
| `43a0d105e` (#3513) | Repris avec adaptation de la consigne HTML au contrat d'artefact Weaver ; pas de promesse d'ouverture automatique de l'aperçu. |
| `70fcc9a7b` (#3519) | Repris : contrôles CI déclenchés seulement quand la PR est prête. |
| `0579222db` (#3495) | Adapté : réutilisation de l'analyse, relance explicite, Owner du commun et nettoyage vision. CP Rust/Temporal/pod existants conservés ; préparation générique, vision KF, flags/backfills et contrats Swift concurrents exclus. |
| `2de825a21` | Exclusion du lot confirmée par Dimi après comparaison : conserver catalogue/cycle de vie Weaver ; tâche différée pour définir attribution exacte aux messages et éventuelle exclusion avant envoi. Aucune reprise applicative ; voir comparaison ci-dessous. |
| `332a5a6a3` (#3520) | Différé comme ensemble cohérent : refonte UI, lecteurs Python, nouvelles dimensions/mappings et outillage. Besoins UX, rôles et collecte à retrouver détaillés ci-dessous ; aucun demi-raccord aux endpoints absents. |
| `2b377b522` (#3501) | Archivage documentaire Swift : ne pas recréer le corpus OpenSpec retiré de Weaver ; garder la traçabilité Git. |
| `222bc60ac` (#3511), dernier commit | Différé : cinq suggestions SQL à porter vers Rust dans un lot dédié, avec espaces/accès/activité/préparation. Accueil courant conservé avec sa limite de raccordement legacy ; pas d'import de `useHomeAgentsQuery` sans endpoint Weaver. |

Le dernier commit sépare activité de conversation et modification du titre/contexte,
complète les agents récents par des suggestions accessibles et prévoit un repli
explicite lorsque l'historique est indisponible. Préserver ce besoin sans importer
ses migrations Alembic CP ni ses équipes par défaut comme modèle métier Weaver.

### Socle Weaver vérifié dans le code

| Contrat | Sources et consommateurs | Conclusion de l'audit |
| --- | --- | --- |
| Consommation modèles | `apps/control-plane/migrations/0001_schema.sql`, table `model_usage` ; `src/sessions/usage.rs` et `src/sessions/usage/read.rs` dans ce composant ; `libs/fred-runtime/fred_runtime/app/usage.py` et ses appels dans `agent_app.py` | Journal SQL, attribution serveur, rapports atomiques et idempotents ; lectures personnelles et d'espace déjà implémentées. Les tokens et le cache existent : ne pas créer une deuxième autorité dans OpenSearch. |
| API et génération | `GET /me/usage`, `GET /spaces/{space_id}/usage` ; `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts`, hooks `useMyUsageQuery` et `useSpaceUsageQuery` | Contrat déjà généré ; les contrôles du pipeline Weaver le consomment. Les dashboards historiques utilisent encore `legacyControlPlaneApiEnhancements`. |
| Droits de consommation | `apps/control-plane/src/authorization.rs`, `SpacePermission::ReadUsage` ; `docs/architecture/A7-action-role-matrix.md`, Consumption reads | Usage personnel pour la personne authentifiée ; collectif pour Owner/Analyst directs, pas Editor. Equipe : agrégation de ses projets, même retirés/purgés ; organisation non supportée par cette route. |
| Stockage et supervision | `apps/control-plane/migrations/0014_conversation_files.sql` ; `apps/control-plane/src/supervision/mod.rs` et ses modèles/store | Réutiliser les comptes de stockage et la supervision d'organisation ; ne pas sommer comptes locaux et total organisation qui se recouvrent. Ne pas confondre quota logique, réservations et octets physiques à purger. |
| Evénements outils et modèles | `libs/fred-runtime/fred_runtime/runtime_support/tool_execution.py` ; `libs/fred-core/fred_core/kpi/` | Emetteurs et stockage KPI Python conservés. Le delta Swift ajoute notamment `capability_id`, `cache_read_tokens` et `tool_count` au mapping ; cela ne prouve pas un suivi complet des connexions MCP gérées dans Weaver. |
| Dashboards | `apps/frontend/src/rework/components/pages/TeamUsagePage/TeamUsagePage.tsx` et `admin/AnalyticsPage/AnalyticsPage.tsx` ; `apps/frontend/src/common/router.tsx` | Ecrans et routes présents, lectures analytics historiques non raccordées au Rust. Présence des écrans et tests historiques ne vaut pas réception fonctionnelle. |

Limite à traiter selon l'usage voulu : `report_run_usage` effectue au plus deux
tentatives HTTP sous délai, puis peut journaliser `outcome=lost`. Le journal SQL
déduplique les rapports reçus mais ne garantit pas une livraison durable des
consommations. Avant facturation ou quota bloquant de tokens, décider et éprouver
la garantie de collecte ; ne pas annoncer une comptabilité exhaustive sur cette base.

### Fonctionnalités analytics à retrouver

Phare produit demandé : rester fidèle aux dashboards Swift et les compléter sur
les ressources Weaver. La référence du nouveau tableau est
`332a5a6a3:apps/frontend/src/rework/components/pages/admin/AnalyticsPage/AnalyticsView.tsx` ;
les définitions détaillées restent consultables dans les presets et tests de ce
commit, sans recopier le CP Python dans Weaver.

| Famille | Valeur à conserver ou compléter | Base et adaptation attendue |
| --- | --- | --- |
| Usage personnel | Tokens entrée/sortie/cache, séries, ventilation agent/modèle et estimations d'impact | Brancher les lecteurs Rust existants. Distinguer zéro, absence de données et service indisponible. |
| Vue d'ensemble et adoption | Visiteurs, utilisateurs actifs/nouveaux, entonnoir, rétention/cohortes, comparaison à la période précédente | Définir précisément événement et dénominateur ; un appel HTTP, un tour avec consommation et un tour terminé ne désignent pas la même activité. |
| Usage et espaces | Conversations, tours, intensité d'usage, comparaison des équipes/projets ; vues adaptées aux rôles | Reprendre espaces et droits Weaver ; ne jamais convertir un scope vide/interdit en scope global. |
| Agents et ressources | Agents disponibles/utilisés, popularité, capabilities équipées/utilisées, appels et échecs, skills | Joindre les identités stables et catalogues CP ; distinguer configuration disponible et usage observé. Prompts/marketplace : définir l'événement d'utilisation avant de promettre un indicateur. |
| Qualité, coûts et impact | Echecs, tokens/cache, coûts estimés en euros, ventilations modèle/agent, estimations environnementales | Réutiliser les faits de consommation ; expliciter tarifs, change, date et limites des estimations. Ne pas assimiler erreurs techniques à qualité des réponses. |
| Supervision technique | Stockage/quotas, réservations, état des traitements et recherche web si activée | Etendre les propriétaires actuels ; agrégats administratifs sans contenu ni identités individuelles. |
| Filtres et tendances | Périodes glissantes/calendaires/personnalisées, fuseau, jours comptés/exclus, période précédente, détails et courbes | Même sémantique dans API, UI et export. Les filtres d'attributs d'utilisateurs Swift demandent un contrat Weaver autorisé et borné. |
| Export Excel | Valeurs typées, explications, période/périmètre/filtres courants, FR/EN, cohérence avec les onglets autorisés | Reprendre la valeur produit de l'export Swift, pas son moteur CP Python par défaut ; aucune identité individuelle ni contenu de conversation dans l'export collectif. |
| MCP, extension Weaver | Appels par connexion et outil, succès/échecs/durée, espace/agent/pod ; répartition des usages | Réutiliser la frontière commune d'exécution et les UUID des connexions gérées. `capability_id` seul ne distingue pas forcément plusieurs connexions ; vérifier les voies ReAct/Graph et éviter le double comptage. Aucun secret, argument ou résultat d'outil dans les dimensions. |

**Orientation confirmée par Dimi le 12 novembre : rester fidèle aux droits Swift,
en réfléchissant à leur adaptation aux Owner organisation, équipe et projet.**
Cela remplace l'hypothèse initiale d'ouvrir les analytics collectifs aux éditeurs.
La dernière Swift réserve ces analytics à son rôle team-admin et aux observateurs
plateforme (`kpi/scope.py` et `TeamUsagePage.tsx` au commit KPI), tandis que Weaver
autorise actuellement Owner et Analyst pour la consommation d'espace.

Proposition à instruire dans K0, pas encore un nouveau contrat d'autorisation :

| Acteur Weaver | Transposition recommandée |
| --- | --- |
| Membre, Editor, Analyst sans rôle Owner | Usage personnel ; aucun nouveau droit collectif accordé par le raccord des dashboards. Le droit de consommation déjà détenu par Analyst demande une décision explicite, distincte du merge. |
| Owner projet | Analytics collectifs du projet dont il est directement responsable. |
| Owner équipe | Analytics de l'équipe et agrégats de ses projets, cohérents avec le lecteur de consommation actuel ; cela ne donne pas accès aux contenus de ces projets. |
| Owner organisation | Pilotage agrégé de l'organisation, à définir sans héritage implicite de rôles métier sur les équipes/projets ni accès aux contenus personnels. |
| Admin organisation/plateforme | Supervision technique agrégée dans son périmètre autorisé ; ne pas convertir le team-admin Swift en Admin technique Weaver ni lui ouvrir les contenus métier. |

Arbitrages restants : maintien d'un `ReadUsage` limité pour Analyst ou alignement
sur Owner seul ; profondeur et détail des agrégats de l'Owner organisation ;
frontière avec la supervision Admin. Aucune permission modifiée. Le raccord
personnel peut avancer indépendamment ; le collectif doit suivre le contrat
tranché, côté backend comme côté UI et export.

### Lots à distribuer et ordre recommandé

Les missions ci-dessous sont préparées, pas attribuées ni exécutées. Le pilote
maintient ce suivi et l'AGENDA ; chaque exécutant rapporte sources, décisions,
chemins possédés, contrôles réellement exécutés et réception restante.

| Lot | Périmètre et résultat attendu | Dépendances et critère de sortie |
| --- | --- | --- |
| M1 - Intégration Swift | Un intégrateur possède le merge et l'index ; traite les sept commits, garde la borne et les exclusions exactes. Réconciliation PowerPoint/SDK/runtime identifiée comme sous-lot, sans reconstruire un second mécanisme. | Lecture de cette section ; résultat comparé aux deux parents, zéro conflit, pas de faux déplacement ni backend retiré réintroduit, clients régénérés depuis les sources réunies, qualité des composants touchés. Merge/commit à exécuter seulement dans la mission explicitement autorisée. |
| K0 - Contrat produit KPI | Matrice acteur/périmètre/indicateur/source/unité, définition des absences et périodes ; transposition Swift vers les trois niveaux Owner, frontière Admin, droit Analyst existant et conservation après suppression. Pas de nouvel audit général du data model. | Peut se préparer pendant M1 en lecture seule ; chaque indicateur relié à un fait existant ou à une collecte manquante nommée. L'UI Swift sert de référence de réception. |
| K1 - Consommation visible | Raccorder usage personnel, puis équipe/projet, aux deux endpoints et hooks Rust existants ; reprendre cartes, courbes, sélecteurs et ventilations Swift. Retirer les dépendances legacy remplacées. | Après stabilisation du merge ; vérifier données API -> écran, rechargement, bornes temporelles, refus de scope et isolation des comptes. Personnel indépendant ; collectif après arbitrage K0, sans extension implicite des droits. |
| K2 - Supervision Admin | Compléter la vue d'organisation avec les faits de consommation et les compteurs/quota existants ; conserver séparation Admin/Owner et détail non nominatif. | Contrat K0 ; agrégats et export futurs respectent le périmètre, sans double comptage des budgets. Ne pas réutiliser la route équipe comme autorisation d'organisation. |
| K3 - Collecte MCP/capabilities/skills | Etendre les émetteurs partagés et leur attribution de manière bornée ; prouver événements réels pour un appel réussi, échoué, annulé et repris. | Contrat K0 et runtime stabilisé par M1 ; définition appels/tentatives, source et déduplication explicites. Peut avancer hors des fichiers UI de K1/K2. |
| K4 - Analytics étendus et Excel | Raccorder progressivement adoption, agents, qualité/coût et tendances, puis export des mêmes agrégats autorisés ; intégrer MCP après K3. | Un onglet et ses sources par incrément, pas un gros portage de presets. Affichage et export alignés, FR/EN, indisponibilité explicite ; réception par rôle avant arc42. |

Un seul propriétaire pour `controlPlaneOpenApi.ts`, les traductions partagées et
les composants de graphiques à un instant donné. Pendant M1, les autres assistants
préparent leurs analyses en lecture seule ; ne pas faire écrire plusieurs agents
dans un index en merge. Ensuite distribuer les lots selon leurs chemins réels.
Objectif de convergence : étendre lecteurs, supervision, émetteurs et composants
existants, supprimer les raccords legacy remplacés ; justifier tout ajout net
nécessaire à une donnée absente, plutôt que créer un service analytics concurrent.

### Preuves et limites de l'audit initial

Fetch, statut Git initial propre, inventaire/historique/parents, simulation de
merge, lecture ciblée des diffs et des contrats effectués. Pas de compilation,
test, service lancé ni réception navigateur : audit et documentation uniquement.
Le découpage des conflits est établi ; la correction de chaque branche du runtime,
des chemins PowerPoint et de chaque preset n'a pas été certifiée. Le prochain
exécutant doit compléter les preuves du lot effectivement réalisé, puis seulement
mettre à jour la borne Swift si un merge est réellement créé.

### Premier lot HTML/CI - reprise locale terminée le 12 novembre

Dimi a choisi ce premier sujet. Exécutant : `port_html_ci` ; relecture du diff
et des consommateurs par le pilote. Aucun stage, commit, merge ou push : la
borne Swift intégrée reste `49aaea682`. Les décisions du tableau des sept commits
ci-dessus sont désormais exécutées localement pour ces deux corrections seulement.

- `43a0d105e` : reprise de l'interdiction de liens inventés dans le résultat de
  `render_html_artifact`, avec renvoi vers la carte et le panneau. Adaptation
  Weaver : "preview is available" remplace la promesse d'ouverture automatique,
  conditionnelle dans `HtmlArtifactCardRenderer.tsx` (heuristique après cinq
  secondes, pas à la reprise de l'historique). Aucun changement du payload ou de
  l'UI ; README et note `html-artifact-link-guidance.md` alignés.
- `70fcc9a7b` : ajout des événements `ready_for_review` et `converted_to_draft`,
  et garde anti-brouillon sur `detect-changes`. Les dix autres jobs en dépendent
  directement, sans `always()`. Note `defer-pr-checks-until-ready.md` ajoutée.

Contrôles exécutés par l'assistant : `uv sync --locked --extra dev`, puis
`UV_NO_SYNC=1 make -o dev code-quality UV=/home/dimi/.local/bin/uv` dans
`libs/capabilities/fred-capability-html-artifact` : Ruff, imports, format, Bandit,
secrets et Basedpyright réussis, zéro erreur/avertissement. Environnement Python
local au worktree, sans modification du lockfile ni des autres checkouts.

Depuis la racine, avec le Python de cette capability :
`scripts/migration_guides.py check-pr --base f6e5af8e3239c56cf4b3b86847347abd237c2a80 --worktree`
valide les deux notes opérateur. Parsing YAML et dépendances des jobs contrôlés ;
`git diff --check` réussi, également revérifié par le pilote. Production :
+10/-1 lignes ; CI : +3/-1 ; documentation du lot : +87/-0, hors présent suivi.
Aucune génération de contrat nécessaire, aucun test ajouté ou lancé.

Réception navigateur et GitHub Actions restante. La consigne HTML réduit le
risque de réponse inventée sans garantir le comportement du modèle. Prochain
sujet avec Dimi : comparer la préparation PowerPoint Swift aux contrats durables
CP/Temporal/pod Weaver avant de décider la reprise des différences.

### Comparaison PowerPoint - avis avant modifications

Audit du pilote et des assistants `ppt_ui_compare` et `ppt_runtime_compare`, en
lecture seule, au 12 novembre. Weaver : `f6e5af8e3` ; apport Swift :
`0579222dbd26e5feeb5c8b646969a6a44b2e0ec3`. Aucun edit PowerPoint, test ou service
lancé ; seules la coordination et cette trace ont été actualisées.

**Conclusion proposée : conserver le socle Weaver, ne pas importer le framework
Swift en bloc.** Le document Swift
`openspec/changes/reusable-capability-preparation/design.md` au SHA ci-dessus cite
explicitement le worker Temporal et le dispatch Weaver comme référence. Il veut
dépasser le couplage PowerPoint et le slot unique de préparation par agent ; cela
ne démontre pas un manque pour le parcours PowerPoint actuel. Le commit touche
154 fichiers et ne fournit pas de nouveau moteur de composition/rendu des slides.

| Sujet | Constat comparé et preuve | Avis pour le merge, à confirmer avec Dimi |
| --- | --- | --- |
| Préparation durable | Weaver possède CP + Temporal + worker de pod, persistance avant confirmation et réutilisation du résultat après ack perdu (`libs/fred-runtime/fred_runtime/app/preparation_worker.py:129-173`, `builder/preparation.py:79-129` dans la capability PPT). Swift introduit un nouveau worker et un autre workflow pour son CP Python. | Conserver worker, workflow et contrats Weaver ; pas de second chemin. |
| Originaux, résultats et nettoyage | Weaver sépare original CP et résultats capability, protège les tentatives par leases/job ID et conserve les reçus de retrait (`builder/preparation.py:36-70`, `builder/analysis_job.py:499-524`). | Préserver ces garanties ; aucune justification identifiée pour remplacer stockage, nettoyage ou migrations. |
| Modèle commun | Weaver : organisation + pod logique, candidat séparé, ancien actif jusqu'au succès (`apps/control-plane/src/documents/powerpoint/acceptance.rs:123`, `capability_preparation/mod.rs:171-188`). Swift conserve son défaut global plateforme. | Conserver l'isolation organisation/pod et les règles de remplacement Weaver. |
| Copie, export, import | Weaver fige le modèle effectif propre ou commun, ses corrections et l'original, puis réimporte et prépare dans le nouveau périmètre (`apps/control-plane/src/marketplaces/agent.rs:116-174,230-250,471-514`, `documents/powerpoint.rs:208-220`). | Pas de manque constaté justifiant l'enveloppe générique `preparation_assets` Swift. |
| Upload, aperçu, revue, reset | Parcours existants dans `PptBuilderPlatformPanel.tsx:56-175` ; contrôle d'attente `expected_file_id`, résolution et erreurs déjà présents. | Garder les composants Weaver ; adaptations de libellés seulement si utiles. |
| Relance du modèle propre à l'agent | Swift ajoute une mutation retry et son bouton (`usePptBuilderAnalysis.ts:142,215` au SHA Swift). Weaver affiche échec/interruption sans bouton dédié (`PptBuilderTemplatePanel.tsx:210-242`) ; la relance du modèle commun existe déjà. | Petit lot utile : bouton explicite branché sur une relance CP Weaver, sans copier l'API/client Swift ni lancer l'analyse dans le navigateur. |
| Recalcul après édition | Weaver incrémente la révision générale sur nom/description/activation/tuning (`agent_instances.rs:196-197`) ; `saved_agent` exige cette même révision pour réutiliser une préparation (`documents/powerpoint/acceptance.rs:176-187`). Swift compare seulement règles, assets et config pertinente (`capability_preparations/admission.py:224-240`). | Reprendre le comportement utile : pas de nouvelle analyse pour un renommage ou une correction sans incidence sur l'analyse ; conserver le mécanisme existant. |
| Plusieurs capabilities préparées | Swift ajoute `PreparationSpec`, plusieurs fichiers, état par capability et readiness agrégée. Weaver ne couvre ici qu'une préparation PowerPoint par agent ; aucun second consommateur réel identifié dans ce périmètre. | Différer la généralisation jusqu'à un besoin concret, sans importer tables/états/interfaces préventivement. |
| Vision | Swift appelle le modèle configuré Knowledge Flow par port dédié ; Weaver refuse explicitement la vision hors tour (`builder/capability.py:699-703`, `useVisionAvailability.ts:19-20`). | Conserver l'analyse structurelle pendant ce merge ; vision reste un lot métier séparé avec autorité, modèles et consommation à définir. |
| Sélecteur vision inutilisé | Weaver construit encore options et sélecteur `labelling_model` dans `PptBuilderVisionSettings.tsx:47-103`, alors que ses consommateurs déclarent la vision indisponible. Swift retire ce sélecteur. | Simplification locale possible : enlever cette branche inatteignable et ses props/helpers propres, en conservant l'explication de l'analyse structurelle ; pas de suppression générale des contrats de modèles. |

Les chemins `builder/*` ci-dessus sont sous
`libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/` ; les
composants PowerPoint sous `apps/frontend/src/rework/features/capabilities/ppt_builder/`.
Les chemins de CP Swift désignent le contenu historique
`apps/control-plane-backend/control_plane_backend/` au SHA figé, pas des fichiers à restaurer.

**Limites de la généralisation Swift.** Le nouveau chemin coexiste avec
`preparation_mode=legacy/shared`. Il est désactivé par défaut dans les types de
configuration (`PodPreparationConfig.enabled_capabilities=()` et
`RuntimeCatalogSourceConfig.preparation_enabled=False`) ; les exemples prod
l'activent explicitement, pas toutes les valeurs Helm. La présence d'un worker
ne prouve donc pas une activation universelle. Ces flags, backfills et lecteurs
de transition ne répondent pas au contrat Weaver d'installation neuve.

Swift ajoute aussi un UUID secret propre à la préparation, envoyé dans les
arguments Temporal puis `X-Preparation-Token`, en plus du workload autorisé
(`dispatcher.py:172`, `api.py:373-409` au SHA Swift). Ce n'est ni un JWT ni un
secret OAuth ; aucune fuite observée n'est affirmée. Conserver l'authentification
workload Weaver et son historique Temporal limité à l'identifiant évite ce
mécanisme supplémentaire sans besoin démontré.

**Défaut Weaver distinct du portage : droits du modèle commun.** Le CP exige
`Permission::Write` dans `documents/powerpoint.rs:185-204` et les réglages communs.
Le tiroir utilise également `useSpaceAccess(organizationId, "write")`
(`apps/frontend/src/rework/components/pages/admin/FeaturesPage/CapabilityPlatformDrawer.tsx:37,69`).
Or `authorization.rs:19-20` attribue Write à Editor et Manage à Owner. Un Owner
seul ne peut donc pas gérer ce modèle commun, contrairement à la responsabilité
métier prévue pour l'organisation. Recommandation : correction ciblée du parcours
commun vers l'autorité Owner, en préservant les droits d'édition du modèle propre
à l'agent ; ne pas modifier la matrice générale Write ni donner ce droit à l'Admin
technique par transposition de Swift. Recommandation de l'audit initial ; la mise
en œuvre acceptée est suivie ci-dessous.

**Lots proposés à l'issue de l'audit initial :**

1. Préserver les implémentations Weaver lors du merge des conflits de ce commit ;
   éliminer de la reprise les nouveaux chemins Swift concurrents et les imports
   qui les rendraient nécessaires. Ne pas appliquer ours globalement à la tranche.
2. Si accepté, traiter relance explicite et réutilisation de l'analyse comme deux
   petits changements du cycle de vie existant. Conserver la révision d'admission
   de l'agent et les contrôles contre les résultats tardifs ; ne pas simplement
   supprimer le filtre de révision. La faisabilité sans nouveau framework est
   établie, pas le patch exact ni sa preuve de concurrence.
3. Si accepté, corriger les droits du modèle commun dans un lot séparé et retirer
   le sélecteur vision inutilisé dans un petit nettoyage UI. Ces sujets ne doivent
   pas entraîner une refonte des rôles ou du catalogue de modèles.

Validation à prévoir pour les lots autorisés : changement de nom pendant/après
préparation sans recalcul ; vrai changement de fichier relançant une analyse ;
résultat tardif refusé ; retry après échec sans réupload ni double job ; maintien
de l'ancien commun pendant remplacement ; Owner seul autorisé sur son commun,
Editor seul et autre organisation refusés sur ce parcours, droits agent préservés.
Préserver les tests existants de reprise/retrait/copie ; aucun exécuté par cet audit.

Bilan de cette comparaison : zéro ligne applicative modifiée. Aucun gain net de
code n'est encore mesuré pour les futurs lots. Les 154 fichiers Swift ne sont pas
un objectif de portage ; la suppression de branches UI inutilisées serait une
réduction réelle, l'ajout d'un autre framework ne l'est pas. Réception PowerPoint
actuelle non rejouée : conclusions sur le code et les contrats, pas une nouvelle
attestation de fonctionnement déployé.

### Mise en œuvre PowerPoint acceptée

Dimi a autorisé les petits correctifs proposés, dans le worktree isolé existant.
`ppt_runtime_compare` a réalisé backend et vérifications ciblées ; `ppt_ui_compare`
a réalisé UI et nettoyage vision ; Codex pilote a relu les diffs et consolidé ce
suivi, arc42 et la note opérateur. Lot prêt localement, aucun merge, commit ou push
exécuté : la reprise utile de `0579222db` est préparée, son ascendance Git n'est
pas encore intégrée.

- Backend : préparation du même fichier immuable réassociée à la nouvelle
  révision d'admission ; contrôles de résultat tardif conservés.
  Un PATCH agent sans changement effectif, notamment `{}`, relance un état failed ;
  pending/ready restent inchangés. Une édition descriptive réelle conserve failed.
- Bouton UI : mutation existante sans envoyer le brouillon ; relance proposée
  seulement pour l'échec canonique CP du modèle propre à l'agent.
  Une interruption rapportée par le pod seul ne prouve pas la fin du travail CP.
- Risque identifié : l'invalidation du détail agent démontait/réinitialisait le
  formulaire. Correction limitée incluse pour conserver les modifications non
  enregistrées pendant le rafraîchissement, avec changement d'identité et réouverture.
  Une révision de configuration différente observée bloque Save avec une notice,
  sans effacer le brouillon ; les erreurs de lecture apparaissent dans la modale.
- Commun d'organisation : Manage pour le modèle commun,
  y compris lecture/téléchargement et accès runtime aux aperçus ; Read/Write des
  modèles propres aux agents inchangés. Pas de modification de la matrice globale.
- Nettoyage UI : sélecteur vision inatteignable et ses seuls helpers retirés,
  état indisponible et analyse structurelle conservés. Vision et généralisation
  multi-capabilities restent différées.

**Validation finale locale :**

- CP : `CARGO_BUILD_JOBS=2 CARGO_PROFILE_DEV_DEBUG=0 make code-quality` réussi
  (Clippy, fmt, fred-rust-agent). Puis `CARGO_BUILD_JOBS=2 CARGO_PROFILE_DEV_DEBUG=0
  CARGO_PROFILE_TEST_DEBUG=0 RUST_TEST_THREADS=1 make test-integration
  CARGO_TEST_OPTS=powerpoint_` depuis `apps/control-plane` : 8 tests réussis,
  197 filtrés. Couvre réutilisation pending/ready/failed, résultat injecté après
  changement de révision, callbacks périmés, retries concurrents, droits Owner,
  ancien commun pendant remplacement, isolation et nettoyage. Fixtures
  PostgreSQL/SeaweedFS jetables supprimées.
- Runtime : `make code-quality` réussi depuis `libs/fred-runtime`, puis
  `.venv/bin/uv run pytest tests/test_capability_platform_ports.py
  -k test_prepared_preview_uses_current_cp_resolution_and_server_pod -q` :
  24 cas réussis, 7 désélectionnés ; référence courante, droits agent/commun,
  refus CP et référence étrangère contrôlés.
- Frontend : six fichiers ciblés, 74 tests réussis ; après dernière correction
  de visibilité de l'erreur dans la modale, deux fichiers concernés rejoués,
  38 tests réussis. `make -C apps/frontend code-quality` final réussi
  (TypeScript, Prettier, ESLint), Node 24.22.2/npm 11.19.1 locaux au worktree.
  Fichiers : `usePptBuilderAnalysis`, `PptBuilderTemplatePanel`,
  `AgentFormModal.pptBuilder`, `TeamAgentsPage.marketplace`,
  `CapabilityPlatformDrawer` et `PptBuilderPlatformPanel` (suffixes `.test.tsx`).
- `git diff --check` réussi. `scripts/migration_guides.py check-pr --base
  f6e5af8e3239c56cf4b3b86847347abd237c2a80 --worktree` valide les trois notes
  nouvelles, dont [celle de PowerPoint](deploy/release-notes/changes/weaver-powerpoint-preparation-reuse.md).

Code applicatif PowerPoint, traductions comprises : backend/runtime +44/-18,
frontend +118/-150, total +162/-168 (net -6). Tests +470/-93 dans sept fichiers ;
documentation et notes comptées séparément. Aucun endpoint, champ API, généré,
service, table ou migration ajouté. Les mécanismes génériques Swift, flags
legacy/shared, backfills et secret de préparation additionnel ne sont pas repris.

Limites : pas de réception navigateur ni de pod/worker Temporal réellement
déployé. La relance forcée d'une analyse réussie après changement des règles
reste hors lot ; sa promesse erronée dans l'UI a été retirée. La garde du formulaire
protège les changements de révision observés, sans nouveau protocole de concurrence
optimiste serveur. Ces limites ne sont pas des fonctionnalités Swift déclarées
intégrées. Prochain sujet à examiner avec Dimi : pièces jointes non envoyées
(`2de825a21`), puis autres sujets restant dans le tableau de cette tranche.

Incident de périmètre UI : l'assistant a lancé une commande `make test` à la racine
au lieu du composant, puis l'a arrêtée et a repris les seuls fichiers frontend
ciblés. Elle a exécuté des tests de scripts et préparé des environnements locaux
dans ce worktree ; aucun service Fred ni changement de fichier suivi constaté.
Ces exécutions hors périmètre ne constituent pas une preuve du lot PowerPoint.
Aucun parcours déployé n'est attesté par ce travail local.

### Pièces jointes non envoyées - comparaison et choix proposé

Audit demandé par Dimi avant toute modification : priorité à un modèle robuste et
simple, plutôt qu'à une reprise mécanique frontend/backend. Source Swift figée :
`2de825a21df59376c0118e6486a30addd75892a3` (#3502), comparée au socle Weaver
`f6e5af8e3239c56cf4b3b86847347abd237c2a80` dans ce worktree. Les changements locaux
HTML/CI/PowerPoint ne touchent pas le mécanisme de pièces jointes étudié.
Audits backend et UI délégués, relus par le pilote ; aucun code modifié, test,
service, fetch ou merge exécuté pour ce sujet. Seuls AGENDA et ce suivi sont mis à jour.

**Décision confirmée par Dimi : conserver Weaver et ne pas reprendre ce lot.** Son
apport UX est réel, mais il dépend d'une association fichier/message exclue
explicitement lors du précédent portage (section « Pièces jointes : décisions
et réception », lignes 1634 et suivantes au moment de cet audit). Ne pas rétablir
`TurnAttachment`, les listes déclarées par le navigateur ou leur copie en historique
sans rouvrir cette décision. Le merge Git reste à réaliser, aucune exclusion n'a
encore été exécutée dans un index de fusion.

| Sujet | Swift entrant | Weaver actuel / choix recommandé |
| --- | --- | --- |
| Retrouver les fichiers après navigation | Isole les entrées locales par conversation et reconstruit les non-envoyés depuis catalogue + historique. | Déjà couvert pour les fichiers acceptés par le catalogue CP, `currentData` et le journal d'upload acteur/espace/session. Les bytes d'un fichier local interrompu ne sont pas sauvegardés dans le navigateur. |
| Déterminer « envoyé » | Déduit des identifiants présents dans les messages ; ancien historique traité par dates. Le runtime conserve désormais aussi `attachments: []`. | Pas de liste par message : classement visuel par dates, limites déjà acceptées. Copier Swift réintroduirait un contrat absent, pas seulement une meilleure puce. |
| Tiroir et contexte envoyé | Masque les non-envoyés dans le tiroir et le texte de contexte, préserve les nouveaux fichiers lors d'un restart. | Les fichiers appartiennent à la conversation ; le tiroir présente le catalogue. Pas de garantie actuelle d'association immuable à un message. |
| Disponibilité pour l'agent | Le design Swift reconnaît l'indexation dès dépôt et la découverte possible par un tour actif. Le statut draft UI n'est pas une barrière serveur. | Le CP fournit les fichiers prêts de la conversation ; le runtime fige leur ensemble à l'admission du tour et de ses descendants. Un ajout ultérieur ne l'élargit pas ; un prochain tour peut utiliser le fichier même sans message qui le référence. |
| Stockage, quotas, abandon | Aucun nouveau modèle ni rétention propre aux brouillons. | Réutiliser uploads idempotents, réservations, traitement et nettoyage CP. Un fichier publié mais jamais envoyé demeure un fichier de conversation et consomme ses ressources. |

**Sources déterminantes.** Les chemins Swift ci-dessous sont à lire au SHA figé,
pas comme des fichiers à réintroduire :

- Swift `openspec/changes/keep-unsent-attachments-as-composer-drafts/design.md`,
  décisions et Known gaps ; `useChatAttachments.ts:141-181`,
  `useManagedChat.ts:653-678,959-989` dans ManagedChatPage ;
  `libs/fred-runtime/fred_runtime/app/agent_app.py:3818`.
- Weaver : `apps/control-plane/migrations/0001_schema.sql:87,123,552`
  (placement conversation/espace), `src/sessions.rs:134-155` (propriété et verrou),
  `src/documents/upload.rs:332-466` (rejeu, limites et réservation),
  `src/sessions/attachments.rs:71-110` (upload et traitement atomiques).
  Ces chemins `src/` sont sous `apps/control-plane/`.
- Disponibilité : `apps/control-plane/src/agent_instances/runtime.rs:322`,
  `libs/fred-runtime/fred_runtime/model_routing/turn.py:60-86` ; aucun renouvellement
  de droits par outil à ajouter. Historique Weaver : `agent_app.py:3092`.
- UI Weaver : `useManagedChat.ts:673-695,764-808`,
  `useChatAttachments.ts:46-85,131-184`, `toThreadMessages.ts:41-66`,
  `attachmentUploads.ts:30-59,99-123`, tous sous
  `apps/frontend/src/rework/components/pages/ManagedChatPage/`.

Le port brut risquerait aussi de rétablir fast-ingest Knowledge Flow et les routes
`/teams/` remplacées par le protocole CP, ou de mapper tous les fichiers rechargés
en `ready` comme Swift alors que Weaver distingue encore traitement et échec.
Swift n'ajoute pas de service satellite ; la complexité ici serait la coordination
d'un classement UI, d'un historique runtime et d'un catalogue CP sans fait métier
unique d'envoi.

**Tâche proposée, non lancée : définir dépôt, envoi et attribution des fichiers.**

1. Séparer deux besoins : rattacher exactement les fichiers au message qui les
   accompagne ; éventuellement garantir leur exclusion avant envoi. Ne pas supposer
   que la première exigence implique la seconde. Le contrat actuel « fichiers de
   conversation disponibles au prochain tour » peut rester le choix le plus simple.
2. Si l'association exacte est retenue, définir son propriétaire et sa preuve durable
   avec les identités existantes de conversation/message/échange ; validation serveur,
   envoi idempotent, échec/retry et suppression cohérents. Ne pas construire un second
   catalogue, une autorité localStorage ou un service de brouillons générique.
3. Si l'exclusion avant envoi est retenue, définir la transition métier et son effet
   sur le filtre d'admission existant avant de modifier API/UI. Réutiliser fichiers,
   quotas et nettoyage CP ; décider la durée de conservation des abandons seulement
   si un cycle de brouillon distinct est nécessaire. Aucun schéma exact prescrit ici.
4. Critères futurs ciblés : navigation/rechargement, deux onglets, ajout pendant un
   tour, HITL/restart, réponse d'envoi perdue et retry, suppression concurrente,
   absence de fuite entre conversations. Installations neuves : pas de fallback
   historique Swift ni backfill à importer par défaut.

**Petits sujets séparés, sans correctif dans cet audit.** Swift ferme drop/paste
pendant HITL ; cette cohérence UI peut se reprendre indépendamment du modèle de
brouillon. Deux limites Weaver préexistantes sont identifiées par lecture, à
reproduire avant intervention : le warning initial conserve les fichiers sans leur
conversation et confirme via le handler courant (`ManagedChatPage.tsx:586-595,1264-1268`),
donc une navigation de session du même agent peut changer la destination ; le
journal d'upload localStorage n'est pas synchronisé entre onglets et peut perdre des
indices de reprise locaux, sans effacer les fichiers acceptés du catalogue CP.
Ne pas transformer ce constat en refonte ou campagne non demandée.

Tests existants seulement lus : Weaver couvre notamment confirmation de session,
réponses tardives, reçus ambigus, retry et suppression refusée ; Swift couvre son
classement et plusieurs reprises avec hooks simulés. Aucun test exécuté ni parcours
réel multi-onglets ou d'exclusion avant envoi attesté par cet audit. Dimi a ensuite
confirmé l'exclusion du lot et demandé de terminer le merge ; la portée métier de
la tâche future reste à choisir avant toute implémentation.

### Finalisation du merge local

Dimi demande de terminer le merge après exclusion explicite des brouillons Swift.
Le travail reste sur `codex/merge-swift-2026-11-12` ; les commits préparatoires et
le merge local nécessaires à cette finalisation sont autorisés. Aucun push ni
déplacement de la branche `weaver` du checkout principal dans cette opération.
La cible reste `222bc60acda8b806c2186bd241dfbf3db180fac2`, sans ajout silencieux
d'une nouvelle arrivée Swift.

- HTML/CI : adaptations directes déjà validées ; PowerPoint : adaptations minimales
  déjà validées, architecture Weaver conservée.
- Pièces jointes `2de825a21` : exclusion acceptée, tâche métier tracée ci-dessus.
- Analytics `332a5a6a3` : différés, besoins et écarts de collecte/lecture conservés
  dans ce document ; ne pas réintroduire des contrats Python ou laisser entrer
  une moitié de refonte UI dépendant de ces contrats.
- Archives `2b377b522` : historique conservé dans Git ; aucun corpus OpenSpec retiré
  à restaurer dans Weaver.
- Accueil `222bc60ac` : différé retenu pour clore ce merge sans nouveau chantier.
  Le gain Swift est réel (sélection SQL de cinq agents et états vide/erreur), mais
  la route Rust manque ; l'accueil Weaver actuel repose encore sur un consommateur
  legacy. Ne pas présenter le maintien de cet écran comme un raccord fonctionnel
  ou une équivalence avec Swift. Le pilote a annoncé ce périmètre conservateur
  pendant la préparation, après avoir proposé le choix à Dimi.

Un seul assistant, `ppt_runtime_compare`, a réalisé les mutations Git. Les autres
assistants ont audité les familles de résolution, y compris les ajouts sans conflit,
puis relu le résultat frontend/HTML/CI/exclusions. Le pilote a consolidé les décisions,
vérifié l'arbre et tenu ce suivi et l'AGENDA.

**Traçabilité Git.** Le commit préparatoire
`c2359321e48a8b168851b7f586f99e30f105c5a4` contient les 34 chemins des adaptations et
de leur documentation validée. Cette section appartient au commit de fusion dont
le premier parent est ce commit préparatoire et le second
`222bc60acda8b806c2186bd241dfbf3db180fac2`. La nouvelle borne Swift intégrée est donc
ce second parent ; les fonctionnalités exclues/différées ne seront pas réappliquées
par un prochain merge et doivent rester des lots explicites.

Le merge normal `--no-commit --no-ff` a présenté 188 chemins non fusionnés, contre
183 dans la simulation antérieure aux adaptations. Les 413 entrées du delta source
ont toutes une provenance parmi les sept commits ; 30 chemins synthétiques ont
aussi été examinés, dont les faux déplacements vers `email_processor`,
`fast_text_processor` et `libs/fred-knowledge/uv.lock`. Les 390 chemins effectivement
touchés par la résolution se répartissent en 159 contenus Weaver préservés et
231 entrées Swift exclues. Les suppressions propres de `PieChart` ont également été
annulées car les dashboards Weaver le consomment encore. Aucune stratégie globale
ours/theirs ni édition manuelle de client généré.

**Preuve du résultat.** Après résolution, zéro entrée non fusionnée ; l'index et
l'arbre applicatif étaient identiques au commit préparatoire. Le merge ajoute
seulement ce bilan et sa note opérateur : tous les apports applicatifs choisis ont
été adaptés avant la fusion. La comparaison avec Weaver initial montre les seuls
lots HTML/CI/PowerPoint acceptés ; celle avec Swift s'explique par les décisions
du tableau. Aucun CP Python, OpenFGA, corpus OpenSpec ou `docs/swift` restauré.
Cinquante fichiers de migrations, workers, activités et préparation ont été
contrôlés par identité de contenu ; aucune migration ou inscription de worker
nouvelle dans cette résolution.

**Contrôles après résolution :** `make code-quality` réussi dans Control Plane,
fred-runtime et frontend ; qualité HTML réussie avec l'environnement local et
la cible sans resynchronisation déjà décrite. YAML CI vérifié : garde draft et
dix jobs dépendants conservés. `git diff --check` et contrôle des quatre notes
opérateur réussis. Les tests ciblés PowerPoint listés plus haut n'ont pas été
relancés : leur arbre applicatif est strictement identique, ce n'est pas une
nouvelle réception fonctionnelle.

La note [d'intégration](deploy/release-notes/changes/weaver-swift-integration-2026-11-12.md)
distingue l'ascendance Git des fonctionnalités réellement activées. Les preuves
temporaires détaillées sont dans `/tmp/weaver-swift-merge-*` sur la machine du
pilote ; les décisions durables sont ce tableau, les deux parents et le diff du
commit préparatoire, sans dépendance à ces fichiers temporaires.

Le checkout principal `~/Work/weaver/fred` est resté propre au SHA initial pendant
la clôture. Aucun push ni déploiement ; réception navigateur/worker réel encore à
effectuer. La promotion de cette branche isolée vers la branche de travail commune
reste une opération distincte des résolutions déjà effectuées.


### Résolution du merge Swift du 13 novembre 2026

Merge commencé par Dimi sur `weaver`, dans `~/Work/common/fred`, puis résolu
par Codex sans commit ni push. Base Weaver :
`5052116a7f20cfeb3e341d865f0d6d086aa29081` ; dernière borne Swift intégrée :
`222bc60acda8b806c2186bd241dfbf3db180fac2` ; cible du merge en cours :
`b7bf4412a38f991423713d96649a0a7c0994dc36`, également `origin/swift` au relevé.
La borne intégrée reste inchangée tant que le commit de fusion n'est pas créé.

| Arrivée Swift | Résolution Weaver |
| --- | --- |
| `77f799d5c` : préparation v3.11.0 | Versions de packages/charts Weaver 5.0.0, bornes `<6`, versions de contrats de capacités et locks conservés. Les changements entrants des locks sont exclusivement des versions Fred et une révision de format uv. Guides de migration Swift et annonces de fonctionnalités différées exclus ; aucune restauration de `docs/swift` ou de `platform-ops`. |
| `2270f27b7`, `743a0666b` : publication Docker | Export OCI avec provenance et entrée Trivy repris. Liste Weaver conservée : l'image PyMuPDF appartient au worker séparé. Le workflow existant ne reçoit pas de voie de récupération additionnelle. |
| `ed1b056fe` : faux échec PowerPoint | Les quatre écritures conservent les routes et droits CP Weaver. Retrait du `refetch` dans leur traitement de succès : le polling existant par organisation/pod rafraîchit sous trois secondes hors latence serveur. Les réponses Weaver ne sont pas les settings complets Swift ; le helper de cache Swift et son test ne sont donc pas importés. Assertions de non-régression adaptées dans le test Weaver existant. |
| `b7bf4412a` : TLS DuckDB | Champs portés dans `fred_knowledge.configuration.TabularQueryConfig`, propriétaire commun actuel ; exécution et tests Swift repris. Schémas API/worker/chart régénérés depuis les modèles, valeurs et documentation conservées. Aucun ancien modèle de stockage ou d'ingestion réintroduit. |

Les lots précédemment différés (analytics, accueil) et l'exclusion des brouillons
restent distincts de ces cinq arrivées. Aucun changement de migration ou de
registre d'activités Temporal dans ce delta. Les notes opérateur OCI, TLS et
PowerPoint sont dans `deploy/release-notes/changes/`.

Validation : zéro entrée non fusionnée ; `git diff --cached --check` réussi ;
`make code-quality` global réussi, frontend inclus (trois avertissements
`reportUnreachable` dans des fichiers worker inchangés). Génération des schémas
API/worker puis `make generate-chart-schema` réussie ; JSON/YAML et absence de
marqueurs contrôlés. `scripts/migration_guides.py check-pr --base HEAD --worktree`
réussi : quatre notes du merge et une note locale préexistante, non ajoutée à l'index.
Code applicatif Python/TypeScript : +15/-4 ; tests : +42/-1 ; configuration CI/chart,
générés et documentation comptés séparément. Pas de campagne de tests fonctionnels,
réception navigateur, publication ou redémarrage de service. Prochaine action :
validation fonctionnelle par Dimi puis commit du merge s'il l'approuve.

## 19. Photo de profil personnelle - 13 novembre 2026

Portage ciblé sur Weaver `74b5f3106`, comparé au parcours de Swift `b7bf4412a` ;
aucune nouvelle fusion et aucune modification de la borne Swift intégrée.
La carte d'import et son recadrage existants sont réutilisés. Rust expose GET,
PUT et DELETE sur `/control-plane/v1/users/me/avatar` ; le client est régénéré,
les réglages et avatars personnels ne dépendent plus du bootstrap Python pour
la photo. Le partage des avatars dans les annuaires d'autres utilisateurs reste
hors de ce lot personnel.

Le catalogue SQL (`0025_user_avatar.sql`) protège la publication et la suppression
concurrentes ; le stockage S3, ses limites de transferts et son nettoyage sont
réutilisés. Les images sont décodées et normalisées côté serveur. Un nouveau
catalogue de fichiers d'espace, des URLs publiques et un worker dédié ne sont
pas nécessaires. Les ajouts de code couvrent le contrat photo manquant et son
cycle de vie ; les composants d'import/recadrage et les traductions sont conservés.

Diff du lot : production +514/-27 lignes (migration comprise), tests +93/-28,
client généré et verrou de dépendances +130/-1 ; documentation comptée séparément.

Contrat OpenAPI et client RTK générés. Migration non appliquée, aucun service
redémarré, aucun commit ni push. Tests et code-quality non lancés à la demande de
Dimi ; réception import/remplacement/rechargement/suppression et vérification des
courses et droits à effectuer par le développeur avant validation du parcours.
