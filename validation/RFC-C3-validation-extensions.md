# RFC - Extension de la validation C3 runtime/authz

Statut: proposition
Portee: `fred-deployment-factory/validation`
Audience: equipe Fred, homologation C3, exploitation sovereign/on-premises

## Resume

La suite `validation/` actuelle donne une premiere confiance end-to-end sur le modele sans grant: Keycloak porte l'identite, OpenFGA decide l'autorisation, le runtime revalide le JWT et refuse les appels inter-equipes. Cette RFC propose de l'etendre en suite de validation C3 exploitable: cas negatifs JWT/authz, API de prompts, canaux retour, multi-runtimes, et production d'un rapport attache a un tag git precis.

Objectif: pouvoir dire pour un tag donne: "ce binaire/configuration a ete teste sur ce setup, avec ces identites, ces versions, ces resultats, et voici l'artefact conservable".

## Non-objectifs

- Ne pas tester l'implementation interne de Fred par imports applicatifs.
- Ne pas reintroduire de dependance a `ExecutionGrant` ou a une racine de confiance proprietaire.
- Ne pas remplacer les tests unitaires/integration de `swift`; cette suite reste une validation black-box d'un stack deploye.
- Ne pas couvrir a elle seule les preuves infra Kubernetes C3: NetworkPolicies, TLS bout-en-bout et durcissement cluster doivent avoir leurs propres controles.

## Principes

1. Les tests agissent comme des utilisateurs reels de `configuration.yaml`.
2. Les dependances Python cote validation restent limitees aux librairies partagees: `fred-core`, `fred-sdk`, `fred-runtime`, plus les librairies de test/HTTP.
3. Toute absence de precondition d'un stack complet doit echouer clairement, pas produire un faux vert.
4. Les tests negatifs doivent verifier le code HTTP, le corps d'erreur quand il est stable, et l'absence d'effet de bord observable.
5. Le rapport de validation doit etre reproductible, horodate et lie a un commit/tag git non ambigu.


## Deployment modes and next task

The immediate validation path is hybrid: Docker provides the backing services and
the Fred apps are started manually from the `swift` checkout with
`configuration_prod.yaml`. This is acceptable for the current auth/security revamp
because the suite exercises real Keycloak tokens, real OpenFGA data, real
control-plane APIs and real runtime HTTP/SSE endpoints.

The full k3d path is a separate follow-up task. It should reuse the same tests and
reporting format, but run against a k3d ingress where all Fred apps and backing
services are deployed together. That effort is valuable for deployment evidence,
but it should not block the current code-level validation of the no-grant model.

Required future work for k3d:

- define the k3d ingress/public origin used for `/control-plane/...` and runtime
  prefixes such as `/fred/agents/v2/...`;
- ensure Keycloak, OpenFGA, Postgres, control-plane, runtimes and frontend are
  all configured from the same intended profile;
- capture Kubernetes manifests, image digests, pod readiness and NetworkPolicies
  in the validation report;
- keep the same test semantics so hybrid and k3d results are comparable.

## Extension A - Cas negatifs JWT et authentification

Ajouter un fichier `scenarios/test_authn_negative.py`.

Cas proposes:

- Absence de header `Authorization` sur control-plane: `401` attendu.
- Absence de header `Authorization` sur runtime SSE: `401` attendu.
- Header `Authorization: Bearer not-a-jwt`: `401` attendu.
- JWT signe par un mauvais issuer: `401` attendu.
- JWT avec mauvais `aud`: `401` attendu.
- JWT expire: `401` attendu.
- JWT `nbf` dans le futur: `401` attendu.
- JWT `alg=none` ou algorithme inattendu: `401` attendu.
- Token d'un utilisateur valide mais sans relation OpenFGA sur l'equipe cible: `403` ou `404` attendu selon la politique de non-enumeration.

Remarques de conception:

- Les tokens invalides ne doivent pas etre obtenus via Keycloak; ils peuvent etre generes localement pour tester le rejet.
- Les tests ne doivent jamais exiger que Fred accepte une cle de test; ils verifient uniquement le rejet.
- Pour `aud`/`iss`, preferer des tokens syntaxiquement valides mais cryptographiquement non conformes, afin de verifier que le runtime ne decode pas sans verifier.

Critere d'acceptation:

- Aucun endpoint protege ne traite une requete sans JWT Keycloak valide.
- Aucun endpoint protege ne fait confiance a un champ utilisateur fourni dans le corps ou un header proxy non authentifie.

## Extension B - Autorisation runtime et canaux retour

Ajouter `scenarios/test_runtime_channels.py`.

Cas proposes:

- Le flux SSE valide le JWT et OpenFGA a chaque ouverture.
- Le canal POST de follow-up/HITL/interruption revalide le meme modele d'authn/authz.
- Un utilisateur membre ouvre une session; un non-membre tente un follow-up sur cette session: refus.
- Un utilisateur membre A cree une session; un autre membre B de la meme equipe tente de reprendre la session: decision explicite a documenter et tester.
- Un utilisateur perd son droit OpenFGA apres ouverture; la requete suivante est refusee. Si le cache OpenFGA existe, documenter la TTL maximale et tester le comportement attendu.
- Un `runtime_context.user_id` forge est ignore ou rejete; il ne devient jamais l'identite effective.
- Un `team_id` absent ou inconnu est refuse.
- Un `agent_instance_id` d'une autre equipe est refuse meme si le `team_id` fourni est autorise.

Critere d'acceptation:

- Pas de demi-session authentifiee: SSE et POST retour appliquent les memes controles.
- Pas de confused deputy entre `team_id`, `agent_instance_id`, utilisateur JWT et relation OpenFGA.

## Extension C - API de prompts

Ajouter `scenarios/test_prompts_api_authorization.py`.

Risque vise:

L'API de prompts peut devenir un canal lateral de fuite ou de modification inter-equipe: lecture de prompts d'une autre equipe, creation sous une mauvaise equipe, injection de `owner_team_id`, modification d'un prompt partage sans droit, enumeration de noms/IDs.

Cas proposes:

- Un membre voit uniquement les prompts accessibles dans ses equipes et son espace personnel.
- Un non-membre ne peut pas lister les prompts d'une equipe cible.
- Un non-membre ne peut pas lire un prompt par ID direct si le prompt appartient a une autre equipe.
- Un non-membre ne peut pas creer, modifier, publier, archiver ou supprimer un prompt dans une equipe cible.
- Un membre simple ne peut pas modifier un prompt si la politique exige manager/owner.
- Un manager/owner peut creer et modifier un prompt de son equipe.
- Un utilisateur peut creer/modifier ses prompts personnels si le produit le permet.
- Un corps de requete qui forge `owner_user_id`, `owner_team_id`, `created_by`, `updated_by` ou `visibility` est ignore ou refuse selon le contrat API.
- La recherche/autocomplete ne fuit pas les titres ou extraits de prompts hors perimetre.
- Les versions/historique d'un prompt respectent les memes controles que le prompt courant.
- Les exports/imports de prompts respectent les memes controles que les routes CRUD.

Preconditions a clarifier avant implementation:

- Identifier les routes exactes de l'API prompts dans le control-plane.
- Documenter le modele d'autorisation attendu: personnel, equipe, public, lecture seule, edition manager-only, etc.
- Choisir une fixture de prompt deterministic creee par la suite et nettoyee en fin de test.

Critere d'acceptation:

- Aucune route prompt ne s'appuie sur un `team_id` ou un champ proprietaire fourni par le client sans check OpenFGA cote serveur.
- La non-enumeration est coherente: soit `403` documente, soit `404` documente, mais pas de fuite par messages d'erreur.

## Extension D - Surface OpenAI-compatible

Ajouter `scenarios/test_openai_compat_security.py` si la route est disponible dans le profil teste.

Cas proposes:

- Par defaut, la surface OpenAI-compatible est desactivee.
- Si activee hors C3, absence de JWT: `401`.
- Si activee hors C3, absence de `X-Fred-Team-Id`: `400` ou `403`.
- Si activee hors C3, utilisateur non membre du `X-Fred-Team-Id`: `403` ou `404`.
- Si activee hors C3, `agent_id` direct vers un agent d'une autre equipe: refus.
- Sous profil C3, route non montee ou fail-closed au demarrage si configuration incompatible.

Critere d'acceptation:

- La compatibilite OpenAI ne contourne pas le modele managed agent + team_id + OpenFGA.

## Extension E - Matrice multi-runtimes

Etendre `factory_config.py` avec une liste d'agents cibles au lieu d'un seul `FRED_TEST_AGENT_ID`.

Exemple de configuration:

```text
FRED_TEST_AGENTS=fred.github.test_assistant,dt.some_test_agent,rags.some_test_agent
```

Cas proposes:

- Rejouer prepare-execution et runtime direct-call denial pour chaque runtime connu: `fred-agent`, `dt-agent`, `rags-agent`.
- Verifier que chaque runtime valide son audience Keycloak attendue.
- Verifier qu'un token destine a un runtime ne peut pas etre reutilise contre un autre si des audiences distinctes sont configurees.

Critere d'acceptation:

- La separation en pods ne cree pas de divergence d'autorisation entre equipes runtime.

## Extension F - Rapport de validation attache a un tag git

Ajouter une commande dediee, par exemple:

```bash
make validation-report TAG=v3.3.0-c3-rc1 OUT_DIR=validation/reports
```

Artefacts a produire:

- `validation/reports/<tag>/<timestamp>/report.md`
- `validation/reports/<tag>/<timestamp>/pytest.xml`
- `validation/reports/<tag>/<timestamp>/pytest.json` si plugin disponible
- `validation/reports/<tag>/<timestamp>/environment.json`
- `validation/reports/<tag>/<timestamp>/sha256sums.txt`

Contenu minimal de `environment.json`:

```json
{
  "validated_tag": "v3.3.0-c3-rc1",
  "deployment_factory_commit": "...",
  "deployment_factory_dirty": false,
  "swift_commit": "...",
  "swift_dirty": false,
  "validation_commit": "...",
  "started_at_utc": "...",
  "ended_at_utc": "...",
  "control_plane_url": "http://localhost:8222/control-plane/v1",
  "keycloak_realm_url": "http://localhost:8080/realms/app",
  "test_team": "fredlab",
  "test_agents": ["fred.github.test_assistant"],
  "users": ["alice", "bob", "liam"],
  "python": "3.12.x",
  "fred_core_version": "...",
  "fred_sdk_version": "...",
  "fred_runtime_version": "...",
  "docker_images": {
    "control-plane": "image@sha256:...",
    "fred-agent": "image@sha256:..."
  }
}
```

Regles de validation du tag:

- `TAG` est obligatoire.
- Le tag doit exister dans le repo applicatif concerne, ou le rapport doit marquer explicitement `tag_resolved=false`.
- Le commit teste doit etre capture par SHA complet, pas seulement par nom de branche.
- Par defaut, refuser de produire un rapport officiel si `deployment_factory_dirty=true` ou `swift_dirty=true`.
- Autoriser un mode explicite `ALLOW_DIRTY=1` pour les essais non officiels, avec mention visible dans `report.md`.

Contenu minimal de `report.md`:

- tag valide et commits associes;
- profil teste: docker-compose local, k3d, Kubernetes, etc.;
- configuration de securite importante: no-grant, Keycloak realm, OpenFGA store, agents cibles;
- resume des resultats: passed/failed/skipped/error;
- liste des echecs avec scenario, acteur, equipe, endpoint;
- interpretation courte: conforme/non conforme pour la matrice testee;
- liens ou chemins vers les artefacts bruts.

Retention recommandee:

- Ne pas committer les rapports volumineux par defaut.
- Stocker les rapports officiels dans un artefact CI, un bucket interne souverain, ou un depot d'homologation dedie.
- Conserver au minimum `report.md`, `pytest.xml`, `environment.json`, `sha256sums.txt`.
- Signer ou horodater les artefacts si le processus d'homologation le demande.

## Proposition d'implementation

Phase 1 - Rapport et hygiene:

- Ajouter `validation/reporting.py` ou `validation/tools/generate_report.py`.
- Ajouter `make validation-report`.
- Produire `pytest.xml` via `pytest --junitxml`.
- Capturer commits, dirty state, versions Python/libs, variables de test, hash des artefacts.

Phase 2 - Cas negatifs authn/authz:

- Ajouter `test_authn_negative.py`.
- Ajouter helpers de tokens invalides et appels runtime/control-plane sans authentification.
- Verifier les codes `401/403/404` attendus.

Phase 3 - Canaux runtime:

- Ajouter tests follow-up/HITL/interruption selon les routes effectivement exposees.
- Ajouter tests session ownership/resume.

Phase 4 - API prompts:

- Cartographier les routes prompts.
- Ajouter fixtures create/read/update/delete avec nettoyage robuste.
- Ajouter tests de non-enumeration et champs proprietaires forges.

Phase 5 - Multi-runtimes et profil C3:

- Generaliser la configuration a plusieurs agents.
- Rejouer la matrice sur `fred-agent`, `dt-agent`, `rags-agent`.
- Ajouter les assertions OpenAI-compatible selon profil.

## Questions ouvertes

- Quelle est la politique produit exacte pour un membre B de la meme equipe qui reprend une session creee par A ?
- Les prompts d'equipe sont-ils editables par tous les membres, ou seulement manager/owner ?
- Le profil C3 doit-il exiger des audiences Keycloak distinctes par runtime dans cette validation ?
- Les rapports officiels doivent-ils etre conserves dans le repo, dans CI, ou dans un espace d'homologation separe ?
- Faut-il capturer les digests Docker/Kubernetes de tous les pods ou seulement des composants Fred ?

## Definition of done

- `make validation` reste rapide et lisible pour le developpeur.
- `make validation-report TAG=...` produit des artefacts conservables et relie les resultats a des commits exacts.
- Les cas negatifs critiques echouent si un endpoint accepte un JWT absent/invalide, un mauvais `aud`/`iss`, un utilisateur hors equipe, ou un champ proprietaire forge.
- Les API prompts et canaux runtime appliquent les memes controles que le flux principal.
- La suite peut etre rejouee sur un tag release pour constituer une piece d'evidence C3 exploitable.
