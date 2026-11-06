# WEAVER - FONCTIONNALITÉS SWIFT À REPRENDRE

**Dernière tranche intégrée : Swift `3d18384205a469f691bbf3ca3cb697911bc6b257`.**
Le merge Swift `394a9150f` part de Weaver `e017f869ea5d5668a47d04da3c2de572e97af8b7` et
reprend quatre nouveaux commits ; voir la section 12. Cette borne sert à
inventorier les prochaines arrivées Swift. Les réceptions et portages différés
restent un inventaire distinct ; leur présence dans l'ascendance ne vaut pas
validation produit. Les repères `53e39f6f7` ci-dessous concernent la tranche initiale.

**Etat consolidé de la tranche initiale, le 4 novembre 2026.** Les portages DOCX, titres, skills et
métadonnées e-mail de la tranche initiale sont intégrés. Mistral #3321 est mis de
côté à la demande de l'utilisateur, sans validation fournisseur. Les réceptions
k3d/plateforme et les raccords arc42 correspondants restent à effectuer.

La [méthode de merge](docs/SWIFT_WEAVER_MERGES.md) décrit la procédure réutilisable.
Ce dossier conserve les sources Swift, les décisions et les preuves de la tranche
initiale ; ce n'est pas une liste de missions à relancer intégralement.

> Un comportement différé peut déjà avoir son commit Swift dans l'ascendance.
> Un nouveau merge ne le réapplique pas. Les portages adaptés ne déplacent pas
> à eux seuls la borne Swift. Celle de la tranche initiale était `53e39f6f7` ;
> la borne actuelle après les tranches suivantes est `3d1838420`.

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
  modèle Zabbix) et `89baab5b6` (#3455, SIEM). Aucun n'est intégré ni nécessaire pour
  recevoir le lot actuel.

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

Cible figée : `89baab5b6`. Base Weaver : `7c29aede0`. Borne intégrée : `3d1838420`.
Branche : `merge/swift-89baab5b6`. Quatre étapes, dans l'ordre de l'ascendance Swift. `6fae3a708`,
`6f3b28478` et `f951e3438`, arrivés ensuite, restent hors de cette tranche.

| Etape | Commits Swift | Etat |
| --- | --- | --- |
| 1 | `b00551906` (#3460) tabulaire | Fusion résolue et préparée, non commitée, en attente de relecture |
| 2 | `a2ebfe48c` (#3476) Azure APIM | Non commencée |
| 3 | `d9eb3738f` (#3453), `303b7456e` (#3483) | Non commencée |
| 4 | `507866562` (#3475), `89baab5b6` (#3455) | Non commencée |

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
