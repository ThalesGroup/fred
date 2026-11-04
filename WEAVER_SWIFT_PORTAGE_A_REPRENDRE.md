# WEAVER - FONCTIONNALITÉS SWIFT À REPRENDRE

**Dossier de reprise du 3 novembre 2026, pour reprendre le travail le 4 novembre.**
Ce document est demandé explicitement pour garder le fil après la fusion. Il décrit
les reports et les pistes de portage, pas des fonctionnalités déjà disponibles.
Les pistes proposées restent à concevoir et à valider dans chaque prochain chantier.
Aucune issue GitHub supplémentaire n'a été créée.

**Mise à jour du 4 novembre 2026 :** le lot auteur DOCX est intégré dans Weaver
et clôturé pour le portage de code. Voir la section 5 pour le commit, les contrôles
effectués et la validation fonctionnelle qui reste à faire.

> **À retenir : les commits Swift différés deviennent des ancêtres de Weaver avec
> cette fusion. Un prochain `git merge` ne les réappliquera pas automatiquement.**
> Il faudra porter explicitement les comportements ci-dessous. Ne pas lancer un
> cherry-pick global de ces PR : certaines touchent le control plane Python retiré,
> d'autres réécriraient les adaptations Weaver du chat et de l'ingestion.

## 1. Reprendre demain en cinq minutes

1. Lire le tableau ci-dessous et choisir **un seul sujet**.
2. Lire sa fiche : apport Swift, frontière Weaver, sources et critères de fin.
3. Examiner le diff du commit Swift indiqué et les sources Weaver actuelles.
4. Définir le comportement voulu, puis réutiliser le propriétaire existant de la
   donnée ou de la décision avant de modifier les contrats, le backend et l'UI.
5. Mettre à jour ce document avec le commit de portage et la validation effective.
   Une case cochée doit désigner un comportement intégré, pas seulement un helper.

| Sujet                                                 | Décision de cette fusion                                | Première action utile                                                          |
| ----------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [Skills : politique, catalogue et traces](#skills)    | PR #3342 entièrement différée, décision confirmée       | Définir la portée de la politique et sa transmission dans le contexte admis    |
| [Titres automatiques et modèle configurable](#titles) | PR #3351 entièrement différée, décision confirmée       | Définir le choix autorisé du modèle et la protection serveur du renommage      |
| [Nom d'auteur des exports DOCX](#docx)                | Portage intégré le 4 novembre, lot code clôturé         | Validation humaine de l'export Word/Markdown restante                         |
| [Mistral Large 4](#mistral)                           | Entrée du catalogue local Swift non reprise             | Vérifier le besoin, puis utiliser le catalogue de modèles Weaver               |
| [Métadonnées e-mail structurées](#mail)               | Partie de #3317 non reprise ; extraction worker reprise | Définir les champs utiles et leur publication par le propriétaire du catalogue |
| [E-mail joint à une conversation](#mail-chat)         | Parcours intégré non établi par cette revue             | Tracer le parcours Weaver actuel avant de décider s'il manque du code          |
| [Erreurs MCP brutes et anciens services](#excluded)   | Exclusions volontaires                                  | Conserver les frontières Weaver ; aucun rétablissement à l'identique           |

Ordre pratique proposé, sans priorité produit imposée : Mistral si c'est un besoin
immédiat de configuration ; auteur DOCX pour un chantier délimité ; titres ensuite ;
skills comme chantier coordonné plus large. Les métadonnées e-mail méritent une
question préalable : quel usage concret, au-delà du texte déjà extrait, les exige ?

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

**État : report intégral confirmé.** Ce n'est pas seulement un panneau d'administration
retiré de la fusion. Les règles d'invocation, le catalogue, les défauts de configuration,
les contrats runtime et les affichages associés sont différés ensemble.

### Ce que Swift apporte

- Une politique globale d'activation/désactivation des skills empaquetés, gérée dans
  le control plane Python et persistée dans une table dédiée. Absence de ligne = actif.
- Un inventaire indiquant les runtimes disponibles, indisponibles ou incompatibles
  avec la politique, et une administration qui peut réactiver un nom même si sa
  source de métadonnées est hors ligne.
- Une configuration absente ou `{}` qui active le catalogue empaqueté ; `skills: null`
  le désactive explicitement ; les répertoires personnalisés gardent leur sens.
- Un catalogue de sept skills : `analyze-data`, `compare-options`, `grounded-research`,
  `summarize-document`, `meeting-minutes`, `grill-me`, `graph`.
- Les quatre premiers sont chargeables par le modèle mais ne sont plus des commandes
  directement sélectionnables par l'utilisateur. `meeting-minutes` et `grill-me`
  demandent une sélection explicite pour un nouveau chargement. `graph` autorise les
  deux voies.
- `graph` réunit diagrammes, graphiques de données et tableaux ; les exemples Mermaid
  deviennent une référence conditionnelle. L'ancien nom empaqueté `mermaid` n'est
  plus annoncé. `data-visualization` et `verify-answer` sont retirés sans alias.
- Titres/descriptions localisés à partir d'une provenance empaquetée fiable, affichage
  du chargement réel des skills et adaptation des sélecteurs/commandes/traces.
- Les anciens messages gardent leurs noms historiques. Les anciennes exclusions
  `mermaid`/`data-visualization` ne sont pas transférées automatiquement à `graph`.

Swift coordonne ces couches avec `X-Fred-Skill-Policy: 1`, une lecture
`/platform/skills/policy` pour l'exécution directe et une version de métadonnées du
catalogue. Sa note exige un déploiement coordonné des replicas ; l'inventaire d'une
URL derrière un répartiteur ne prouve pas que chaque replica est à jour.

### Pourquoi ne pas le fusionner tel quel

Les endpoints, la table et les mécanismes de résolution de cette politique ciblent
le control plane Python supprimé. Importer seulement le runtime activerait des
lectures de politique sans propriétaire Rust correspondant. Importer seulement les
nouveaux noms/menu laisserait catalogue, commandes et exécution incohérents.
Le comportement actuel des skills Weaver est donc conservé dans cette fusion.

### Sources à ouvrir

- [docs/swift/ops/migrations/platform-skills-evolution.md](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/docs/swift/ops/migrations/platform-skills-evolution.md)
- [apps/control-plane-backend/control_plane_backend/platform_skills/service.py](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/apps/control-plane-backend/control_plane_backend/platform_skills/service.py)
- [apps/control-plane-backend/control_plane_backend/platform_skills/schemas.py](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/apps/control-plane-backend/control_plane_backend/platform_skills/schemas.py)
- [libs/fred-sdk/fred_sdk/contracts/skills.py](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/libs/fred-sdk/fred_sdk/contracts/skills.py)
- [libs/fred-runtime/fred_runtime/skills/native.py](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/libs/fred-runtime/fred_runtime/skills/native.py)
- [libs/fred-runtime/tests/test_skill_policy.py](https://github.com/ThalesGroup/fred/blob/29c01c68131a31309b659842f22d4637dd215075/libs/fred-runtime/tests/test_skill_policy.py)

Côté Weaver : [résolution runtime Rust](apps/control-plane/src/agent_instances/runtime.rs),
[catalogue des agents](apps/control-plane/src/agents/catalog.rs),
[contrats des skills](libs/fred-sdk/fred_sdk/contracts/skills.py),
[catalogue runtime](libs/fred-runtime/fred_runtime/skills/catalog.py),
[chargements natifs](libs/fred-runtime/fred_runtime/skills/native_reads.py),
[commandes du composeur](apps/frontend/src/rework/components/pages/ManagedChatPage/useComposerCommands.ts).

### Démarche proposée pour Weaver

1. Confirmer le besoin et la portée : politique plateforme sur le catalogue empaqueté,
   traitement des répertoires personnalisés, droits d'administration et diagnostic
   quand un runtime manque. Ne pas déduire une nouvelle politique par organisation
   du seul fait que Weaver possède des organisations.
2. Chercher le support de configuration existant approprié. Si une persistance
   nouvelle est nécessaire, la concevoir côté Rust/PostgreSQL avec contraintes et
   migration immuable. Garder un seul propriétaire des décisions.
3. Relier cette politique au contexte serveur admis et couvrir tous les points
   d'entrée encore actifs, y compris les reprises. Ne pas copier un appel HTTP
   supplémentaire vers un endpoint Swift inexistant.
4. Définir la fraîcheur à la nouvelle admission, le comportement en cas de source
   indisponible et la compatibilité des replicas. Ne pas retirer rétrospectivement
   des instructions déjà chargées dans un tour ou un checkpoint.
5. Porter ensemble le catalogue, ses règles d'invocation, les validations du SDK,
   le chargement runtime et les commandes UI. Documenter explicitement les noms
   retirés et le devenir des anciennes exclusions ; ne pas migrer silencieusement
   une préférence vers un skill dont le périmètre est plus large.
6. Porter la trace du chargement réel et les traductions ; régénérer les contrats.
   Préserver les vieux messages même si le skill n'existe plus dans le catalogue.
7. Définir un ordre de déploiement et un retour arrière propres aux composants Rust
   et runtime. La migration Alembic Swift n'est pas une procédure Weaver.

### Critères de fin à vérifier

- [ ] Activation/désactivation cohérente entre inventaire, menu et nouveau chargement.
- [ ] Invocation utilisateur/modèle conforme pour les sept skills ; refus des vieux brouillons incompatibles sans perte du texte.
- [ ] Comportement explicite si la source de politique manque ; pas de catalogue vide inventé.
- [ ] Même décision sur les replicas et à la reprise selon les règles d'admission convenues.
- [ ] Historique et anciens noms lisibles ; exclusion historique de visualisation traitée explicitement.
- [ ] Les traces correspondent à un chargement effectif, pas à une simple mention dans le texte.
- [ ] Configuration absente, vide, nulle et personnalisée testée ; contrats et deux locales cohérents.

<a id="titles"></a>

## 4. Titres de conversation générés et modèle configurable

**Références :** [issue #3346](https://github.com/ThalesGroup/fred/issues/3346), [PR #3351](https://github.com/ThalesGroup/fred/pull/3351), [commit 5ba132152](https://github.com/ThalesGroup/fred/commit/5ba132152b745ef338a7c493a4ec28588ebae5b2).

**État : PR entièrement différée.** Weaver conserve ses titres actuels et le
renommage manuel ; le sélecteur du modèle, `auto_title` et l'événement `session_title`
Swift ne sont pas activés par cette fusion.

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

### Démarche proposée pour Weaver

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

### Critères de fin à vérifier

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

**État : entrée du catalogue local Swift non reprise.** Ce n'est pas une suppression
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

### 7.1 Métadonnées structurées non reportées

Swift enrichit `title`, `author`, `created` à partir du sujet, de l'expéditeur et de
la date du mail. Son override `process_metadata` ajoute `extensions.email` avec
`to`, `cc`, `message_id`, `in_reply_to` ; pas de `bcc`. Cette écriture utilise l'ancien
chemin d'enrichissement des métadonnées pendant l'ingestion.

Dans Weaver, les helpers de parsing ne constituent pas une publication de ces
champs dans le catalogue. L'override Swift n'est pas restauré : le manager et le
control plane possèdent l'identité, le placement, les métadonnées et la publication.
**Avoir le sujet dans le Markdown ne signifie pas qu'il existe comme champ filtrable
ou interrogeable dans le catalogue.**

- [apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/email_processor/email_markdown_processor.py](https://github.com/ThalesGroup/fred/blob/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e/apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/email_processor/email_markdown_processor.py)
- [apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/fast_text_processor/fast_email_processor.py](https://github.com/ThalesGroup/fred/blob/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e/apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/fast_text_processor/fast_email_processor.py)
- [apps/knowledge-flow-backend/knowledge_flow_backend/features/ingestion/ingestion_controller.py](https://github.com/ThalesGroup/fred/blob/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e/apps/knowledge-flow-backend/knowledge_flow_backend/features/ingestion/ingestion_controller.py)
- [docs/swift/ops/migrations/3306-email-file-ingestion.md](https://github.com/ThalesGroup/fred/blob/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e/docs/swift/ops/migrations/3306-email-file-ingestion.md)

Côté Weaver : [processeur e-mail](apps/knowledge-flow-worker/knowledge_flow_worker/core/processors/input/email_processor/email_markdown_processor.py),
[parseur et helpers](apps/knowledge-flow-worker/knowledge_flow_worker/core/processors/input/email_processor/email_message_parser.py),
[modèles documentaires](apps/control-plane/src/documents/models.rs),
[publication](apps/control-plane/src/processing/publication.rs),
[enregistrements de traitement](apps/control-plane/src/processing/models.rs).

Démarche proposée :

1. Définir les usages : affichage, filtrage, recherche, regroupement par fil ?
   Ne pas créer un schéma métier complet de messagerie si le besoin est seulement
   de lire les en-têtes déjà présents dans le texte.
2. Séparer les faits extraits du mail et les faits de gouvernance du document.
   Un expéditeur ou destinataire de mail n'accorde aucun droit d'accès Weaver.
   Un `message_id` externe n'est ni l'identité du document ni une clé de tenant.
3. Examiner le contrat de sortie d'extraction et le propriétaire actuel des
   métadonnées. Ajouter les champs nécessaires dans ce contrat et leur publication
   autorisée, avec bornes et validation ; ne pas laisser le parseur écrire le catalogue.
4. Décider de la provenance et des conflits : métadonnée extraite face à une valeur
   métier existante, réingestion, remplacement, donnée manquante ou malformée.
5. Adapter les projections/recherches seulement si le besoin les exige, sous les
   mêmes contrôles de document publié. Toute évolution de schéma doit être additive.

- [ ] Extraction et publication reliées dans un cas réel, pas seulement un test de helper.
- [ ] Valeurs absentes/malformées et listes longues bornées ; Cci exclus des champs dédiés.
- [ ] Identité, espace, droits et publication du document inchangés.
- [ ] Remplacement et réingestion ne restaurent pas des champs obsolètes.
- [ ] Les champs annoncés dans l'UI ou les recherches existent effectivement dans le catalogue.

<a id="mail-chat"></a>

### 7.2 E-mail directement joint à une conversation : parcours à établir

Swift ajoute également `FastEmailProcessor` et adapte son ancien contrôleur
d'ingestion pour les extensions e-mail. Le helper est disponible dans le worker
Weaver, mais l'API d'ingestion synchrone retirée n'est pas restaurée.

**Ce point est une incertitude d'intégration, pas la preuve que le parcours est
absent ou cassé.** Les tests de processeurs ne suffisent pas à conclure. L'aide a été
limitée au parcours bibliothèque pour ne pas présenter ce chemin comme établi.

Commencer par [les pièces jointes de session](apps/control-plane/src/sessions/attachments.rs),
[la préparation de conversation](apps/control-plane/src/agent_instances/preparation.rs)
et [le helper e-mail](apps/knowledge-flow-worker/knowledge_flow_worker/core/processors/input/fast_text_processor/fast_email_processor.py).
Tracer le dépôt, l'admission, le stockage, la sélection du processeur, le résultat
visible par le runtime et le nettoyage. Selon ce constat, terminer soit par une
validation du parcours existant, soit par une adaptation minimale de ce parcours.
Ne pas recréer l'ancien endpoint Python pour brancher le helper.

- [ ] `.eml` et `.msg` atteignent le bon extracteur via la voie de pièces jointes actuelle.
- [ ] Les droits de conversation sont contrôlés ; aucune pièce jointe ne devient un document partagé implicitement.
- [ ] Les attentes, annulations et erreurs suivent les états existants ; pas de nouvelle file parallèle.
- [ ] L'agent reçoit le contenu attendu ; la documentation ne promet que le parcours validé.

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

### Matrice des 25 commits entrants

| Commit Swift                                                                                     | Sujet du commit                                                                                                              | Traitement dans Weaver                                                   |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| [7a2bbcbc5](https://github.com/ThalesGroup/fred/commit/7a2bbcbc5c8cc34f0eb7d9472715d57ca7faf35f) | fix(tabular): restore tabular SQL compatibility and trace panels (#3365)                                                     | Repris et adapté aux publications/droits Weaver                          |
| [5ba132152](https://github.com/ThalesGroup/fred/commit/5ba132152b745ef338a7c493a4ec28588ebae5b2) | feat(#3346): name new conversations with a generated title and choose its model (#3351)                                      | Différé intégralement : titres                                           |
| [fa363690e](https://github.com/ThalesGroup/fred/commit/fa363690ebac5d438904d1538450cacff3c48d56) | fix(#3344): show the agent description on the chat welcome card (#3345)                                                      | Repris : description de bienvenue                                        |
| [c05b1a590](https://github.com/ThalesGroup/fred/commit/c05b1a59086ef91f3653e4100d7cf0494ff4f986) | fix(#3403): raise the per-turn tool call limit to 100 (#3404)                                                                | Repris : plafond 100                                                     |
| [2ddc6870b](https://github.com/ThalesGroup/fred/commit/2ddc6870b44485573bed693c51420158a7c8303e) | chore(#3320): add Mistral Large 4 to local text models (#3321)                                                               | Non repris : catalogue local retiré                                      |
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
| [2b6bf4e16](https://github.com/ThalesGroup/fred/commit/2b6bf4e168bad2216dd614c5d2a6fd3ef147a54e) | feat(#3306): ingest Outlook .msg and .eml mail files (#3317)                                                                 | Partiel : extraction worker reprise ; métadonnées/parcours chat à suivre |
| [a997ee4b3](https://github.com/ThalesGroup/fred/commit/a997ee4b3f8ff3053477c0d2399c2f79abadd580) | chore(deps-dev): bump minimatch from 10.2.4 to 10.2.6 in /apps/frontend in the npm_and_yarn group across 1 directory (#3423) | Repris : minimatch                                                       |
| [55de29845](https://github.com/ThalesGroup/fred/commit/55de298455ffabf3a14b8eadc946553a4045a725) | fix(#3421): use the authenticated user in generated docx metadata (#3422)                                                    | Différé intégralement : auteur DOCX                                      |
| [bcc65f39b](https://github.com/ThalesGroup/fred/commit/bcc65f39b5ca47c9b74d3cbd08e8ec2b11808b29) | chore(#3424): centralize the Node.js toolchain in .nvmrc (#3425)                                                             | Repris : baseline Node centralisée                                       |
| [29c01c681](https://github.com/ThalesGroup/fred/commit/29c01c68131a31309b659842f22d4637dd215075) | feat(#3299): evolve platform skills and native load visibility (#3342)                                                       | Différé intégralement : skills                                           |
| [8c5faa604](https://github.com/ThalesGroup/fred/commit/8c5faa6049d105f880304acdb4d5b5ade76a8936) | fix(#2603): keep a streamed chat turn running across in-app navigation (#3418)                                               | Adapté : arrière-plan, autorisation de l'historique avant adoption       |
| [d93037008](https://github.com/ThalesGroup/fred/commit/d93037008bfcdc225cfc206b42002ed041ccdb38) | fix(#3322): show the deployment's site name instead of "Fred" in user-facing text (#3323)                                    | Repris : nom du site                                                     |
| [53e39f6f7](https://github.com/ThalesGroup/fred/commit/53e39f6f77e63bbc8238b881df38686df5be452e) | fix(#3427): preserve queues and clarify background chat status (#3429)                                                       | Adapté : files/statut arrière-plan, événements liés à l'identité         |

## 10. Suivi à compléter lors des prochains portages

| Sujet                      | État après cette fusion                                | Commit Weaver de réalisation / validation |
| -------------------------- | ------------------------------------------------------ | ----------------------------------------- |
| Skills #3342               | Différé intégralement                                  | À renseigner                              |
| Titres #3351               | Différé intégralement                                  | À renseigner                              |
| Auteur DOCX #3422          | Portage intégré, lot code clôturé le 4 novembre         | `c784b3b71` ; qualité et 57 tests offline réussis ; validation fonctionnelle restante |
| Mistral #3321              | Configuration non reprise ; besoin à confirmer         | À renseigner                              |
| Métadonnées e-mail #3317   | Extraction reprise, publication structurée non reprise | À renseigner                              |
| E-mail joint au chat #3317 | Parcours à établir avant de conclure à un manque       | À renseigner                              |

Pour chaque réalisation, noter le comportement effectivement intégré, les sources
modifiées, les contrats éventuellement régénérés, les vérifications exécutées et
les limites restantes. Garder la référence Swift et la décision initiale même après
réalisation. Une mise à jour de ce document suffit ; ne pas multiplier les tableaux
de suivi concurrents.
