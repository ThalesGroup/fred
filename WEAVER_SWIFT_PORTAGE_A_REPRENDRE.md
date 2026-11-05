# WEAVER - FONCTIONNALITÉS SWIFT À REPRENDRE

**Dernière tranche intégrée : Swift `059ae1c91b959692f6a0fb61ddc9824c67c90355`.**
Le merge suivant part de Weaver `6adc65bf41d10e56202797a529443a67f8dbe191` et
reprend deux nouveaux commits ; voir la section 11. Cette borne est celle à utiliser
pour inventorier les prochaines arrivées Swift. Les repères `53e39f6f7` ci-dessous
restent ceux de la tranche initiale et de ses portages différés.

**Etat consolidé de la tranche initiale, le 4 novembre 2026.** Les portages DOCX, titres, skills et
métadonnées e-mail de la tranche initiale sont intégrés. Mistral #3321 est mis de
côté à la demande de l'utilisateur, sans validation fournisseur. Les réceptions
k3d/plateforme et les raccords arc42 correspondants restent à effectuer.

La [méthode de merge](docs/SWIFT_WEAVER_MERGES.md) décrit la procédure réutilisable.
Ce dossier conserve les sources Swift, les décisions et les preuves de la tranche
initiale ; ce n'est pas une liste de missions à relancer intégralement.

> Un comportement différé peut déjà avoir son commit Swift dans l'ascendance.
> Un nouveau merge ne le réapplique pas. Les portages intégrés ci-dessous ne
> déplacent pas la borne Swift fusionnée : `53e39f6f7`.

## 1. Reprendre en cinq minutes

1. Lire cet état et la méthode ; vérifier branche, statut et travail concurrent.
2. Actualiser les références Swift sans merge automatique et figer la nouvelle cible.
3. Inventorier les nouveaux changements depuis la borne intégrée, séparément des
   validations restantes et des décisions mises de côté.
4. Expliquer les apports produit puis attribuer des lots bornés, avec propriétaires
   Weaver, dépendances et contrôles proportionnés.
5. Mettre à jour ce dossier après chaque intégration, sans présenter du code isolé
   ou des tests simulés comme une validation déployée.

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

### Repères Git et limites de ce dossier

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
- [ ] Validation fonctionnelle humaine de l'export depuis l'interface et du déploiement.

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

## 12. Arrivées Swift après la borne 059ae1c91

Inventaire initial fixé sur Weaver `e71bc96ac1d0ac94043b47bf7f0c762f69228e79`
et Swift `541f3275d9908732a4b7c5d99a7302756fce2171`, puis complété par le
portage ciblé de `3d18384205a469f691bbf3ca3cb697911bc6b257`. La borne intégrée
reste `059ae1c91b959692f6a0fb61ddc9824c67c90355` : un cherry-pick isolé ne la déplace pas.

| Commit Swift | Apport | Etat Weaver |
| --- | --- | --- |
| `de9192157ea898fe9bb8873362b858fca3e7295d` (#3290) | Construction de présentations depuis un modèle, avec administration et catalogue de capacité | Adaptation requise : le commit modifie le Control Plane Python retiré ; examiner le contrat dans le Control Plane Rust et les mécanismes de capacités avant portage. |
| `d850bdce63a69854ecc77d13ebb7fdb98fa33187` (#3470) | Conserver le rapport CVE et laisser 15 minutes au SBOM Trivy de l'image PyMuPDF | Intégré via #3472 : matrice Weaver et contrôle d'import conservés, note opérateur déplacée. |
| `541f3275d9908732a4b7c5d99a7302756fce2171` (#3436) | Préparation de la version Swift 3.10.0 | Exclu du backport fonctionnel Weaver : versionnement propre à Swift. |
| `3d18384205a469f691bbf3ca3cb697911bc6b257` (#3471) | Cibles exactes pour le retour des migrations Agent Pod | Portage en PR #3473, non intégré ; voir ci-dessous. |

### Cibles exactes pour le retour des migrations Agent Pod

Source Swift : `3d18384205a469f691bbf3ca3cb697911bc6b257`, après la
borne intégrée `059ae1c91b959692f6a0fb61ddc9824c67c90355`. Base Weaver du
portage : `e71bc96ac1d0ac94043b47bf7f0c762f69228e79`. La
[PR #3473](https://github.com/ThalesGroup/fred/pull/3473) ne déplace pas la
borne Swift fusionnée.

Le CLI `fred_runtime downgrade` et le Make target Agent Pod acceptent une
révision complète ou `base` pour un seul arbre runtime/capability. Les cibles
relatives comme `-1` sont refusées avant Alembic. Weaver garde ses propres
histoires Alembic, dont la révision d'espace `a7b8c9d0e1f2`, et la vérification
du portage cible un retour traversant plusieurs révisions. Aucun nouveau schéma
ni ancien dossier OpenSpec Swift n'est repris. La note opérateur est dans
`deploy/release-notes/changes/weaver-exact-agent-migration-downgrade.md`.

La qualité `make code-quality` passe pour `fred-runtime` et `fred-agents` ; la
déclaration de note opérateur passe `scripts/migration_guides.py check-pr`. Le
développeur garde la validation fonctionnelle d'un rollback sur installation
isolée ; aucun retour de données réelles n'est lancé par ce portage.
