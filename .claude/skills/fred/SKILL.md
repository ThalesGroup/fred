---
name: fred
description: Démarrer les composants Fred locaux et, sur demande, un pod fred-samples et son serveur de test ; observer leurs logs pendant que le développeur teste dans l’UI. Utiliser pour une session locale de démarrage, arrêt ou diagnostic par les logs, sans campagne de tests ni collecte KPI.
---

# Fred — démarrage et observation locale

Le développeur pilote l’UI et gère Docker Compose (Keycloak, Postgres,
Temporal, OpenSearch, OpenFGA et autres services d’infrastructure). L’assistant
lance les applications demandées, lit leurs logs et aide au diagnostic.

## Périmètre et accord

- Une demande de préparation ou de modification de ce skill ne lance rien.
- Avant un démarrage, annoncer les composants, commandes et répertoires. Une
  demande explicite de démarrage autorise ce périmètre ; sinon attendre l’accord.
- Vérifier que le développeur a terminé de démarrer son infrastructure. Ne pas
  lancer, arrêter, reconstruire ni réinitialiser son Docker Compose.
- Demander avant tout élargissement : tests, requêtes métier, publication de KB,
  modification de configuration/code, installation supplémentaire ou dépannage long.
  Ne lancer ni `make test`, ni `make code-quality`, ni campagne automatique.
- Pas de KPI pour cette première version. Le signal est stdout/stderr de chaque
  composant, avec les messages d’audit déjà présents dans ces logs.

## Répertoires et composants

Utiliser le checkout choisi dans la conversation, jamais un autre checkout
par commodité. Repères usuels : Fred `~/Fred/fred`, samples `~/Fred/fred-samples`.
Vérifier les chemins, la branche et les consignes du dépôt ; ne jamais supposer
que ces chemins désignent le checkout choisi.

| Composant | Répertoire relatif à Fred | Commande |
|---|---|---|
| Control Plane API | `apps/control-plane-backend` | `make run` |
| Control Plane worker | `apps/control-plane-backend` | `make run-worker` |
| Knowledge Flow API | `apps/knowledge-flow-backend` | `make run` |
| Knowledge Flow worker | `apps/knowledge-flow-backend` | `make run-worker` |
| Fred Agents API | `apps/fred-agents` | `make run` |
| Frontend | `apps/frontend` | `make run` |

Les « cinq backends » sont les trois API et les deux workers ; le frontend est
un sixième processus. Respecter le choix de la conversation ; s’il est inconnu,
clarifier une seule fois si le frontend doit aussi démarrer.

## Configuration commune avec délégation

La source versionnée de ce skill est `.claude/skills/fred/SKILL.md`, également
accessible via `.agents/skills/fred/SKILL.md`. Une copie personnelle doit rester
alignée sur le checkout utilisé. Lire `scripts/README-local-delegation.md` depuis
la racine du checkout pour la procédure complète et les diagnostics.

- Après le `make docker-up` du développeur, les trois API utilisent
  `CONFIG_FILE=./config/configuration_prod.yaml` dans leur `config/.env`.
- Préparer la délégation avec `make delegation` à la racine de Fred, sans
  modifier les YAML. Le helper utilise le secret M2M agentic existant, sans accès
  administrateur, et vérifie le jeton émis : rôle `delegation_caller` du client
  `fred-delegation` (claim `resource_access.fred-delegation.roles`), audience
  `fred-delegation` et issuer du realm. Aucun identifiant de compte de service
  n’est à recopier. `make delegation ARGS=--dry-run` diagnostique sans écrire.
- Si le rôle ou l’audience manque, relancer le post-install Keycloak de
  deployment-factory, qui crée `fred-delegation` et accorde le rôle à `agentic`,
  puis `make delegation`. Ne jamais assouplir les contrôles pour passer.
- Les fichiers ignorés `config/.delegation.local.json` activent seulement le bloc
  `security.delegation` du YAML de chaque application ; les autres réglages
  viennent du YAML. Chargés uniquement par `make run` / `make run-worker`. Les
  régénérer après recréation du realm (puis post-install), après modification
  de l’audience, du rôle ou du chemin de claim, ou si le chargement refuse un
  ancien fichier ; puis redémarrer les applications.
- Pour ce profil local, issuer utilisateur et M2M sont tous deux
  `http://localhost:8080/realms/app` ; C3 accepte l’une ou l’autre adresse de realm
  configurée. Ne pas contourner un refus C3 en désactivant les contrôles.
  L’audience utilisateur doit inclure `app` ; `azp=app` ne suffit pas. Le jeton
  agentic n’a pas besoin des audiences des récepteurs : `fred-delegation` et le
  rôle suffisent. Le post-install configure ces audiences.
- Les workers utilisent le même CONFIG_FILE que leur API. Le worker Knowledge
  Flow expose ses métriques locales sur 9112, l'API sur 9111.
- Ne pas confondre un échange court réussi avec un test de renouvellement de
  jeton. Sur les échanges, rechercher `delegated_run_admitted` côté Fred Agents
  et `delegation.grant.accepted` côté récepteurs. Refus : `delegation.grant.rejected`
  avec `caller_not_trusted` (jeton sans le rôle), `caller_not_allowed` (rôle
  présent mais audience, issuer ou client refusé) ou `invalid_parameters` (grant
  incomplet) ; 403 `delegated_person_required` ou `workload_caller_not_allowed` ;
  401 pour un jeton adressé seulement à `fred-delegation` sans le rôle.
- Évaluateur, samples et serveurs MCP externes ne font pas partie des six
  composants par défaut. Signaler leurs indisponibilités sans les démarrer
  implicitement. Exécuter `make validation-report` seulement sur demande.

## Observation de l’authentification, sur demande

Lire la section « Authentication operational signals » de
`docs/swift/platform/OBSERVABILITY-AND-AUDIT.md`. Après redémarrage des API,
les séries `fred_auth_m2m_*` et `fred_auth_delegation_decisions_total` sont sur
leurs endpoints Prometheus. Le compteur IAM distingue operation=initial/renewal.
La seconde reprend les raisons d’acceptation et de refus ci-dessus
(`grant_validated` pour une acceptation).
Docker et GCP partagent le dashboard Application KPIs ; vérifier les Targets
Prometheus avant de conclure à zéro erreur. `make check-auth-dashboard` dans
deployment-factory vérifie les noms/labels contre le checkout Fred. Le développeur
lance `make grafana-up` pour l’infrastructure locale.
Ne pas confondre cache miss et appel IAM : plusieurs
appelants peuvent partager un renouvellement. La console navigateur émet
`browser_token_refresh` sans secret ; ce n’est pas de la télémétrie centralisée.
Ne pas prétendre prouver un refresh navigateur avec les seuls logs backend.

## Test de renouvellement rapide, sur demande

Dans deployment-factory : `make keycloak-token-status`, puis
`make keycloak-token-short` (app 60 s, agentic M2M 120 s) ou
`make keycloak-token-normal` (300 s pour les deux).
Ces commandes modifient uniquement la durée des nouveaux jetons des clients
`app` et `agentic` dans le Docker local. Demander une reconnexion avant le test ;
attendre 90 s sans rechargement. Pour le M2M, redémarrer Fred Agents ou attendre
l’expiration du jeton déjà en cache, puis tester plus de deux minutes avec un
appel protégé après ce délai. Les sessions/grants ne sont pas modifiés. Garder trace du mode appliqué et restaurer explicitement
le mode normal en fin de campagne ; un redémarrage de Fred ne le restaure pas.
Voir le guide commun pour les limites et les preuves à observer.

## Avant de lancer

1. Lire les cibles Makefile et leurs prérequis. `make run` peut installer des
   dépendances, et le worker Knowledge Flow peut télécharger des modèles.
   Signaler un coût de préparation important avant de le déclencher.
2. Vérifier `config/.env` et le fichier désigné par `CONFIG_FILE`, puis les
   éventuels overrides du Makefile.
   Lire uniquement les valeurs nécessaires ; ne jamais afficher les secrets ou
   recopier le `.env` entier dans une réponse. Vérifier les destinations locales,
   l’authentification et la cohérence API/worker ; ne rien réécrire silencieusement.
   Pour le frontend, vérifier son Makefile, sa configuration Vite et ses proxies.
3. Repérer les ports occupés et les processus existants avec une inspection
   locale en lecture seule. Un port occupé n’est pas une preuve de disponibilité
   du bon checkout. Ne pas tuer un processus inconnu ; demander s’il faut le
   conserver ou le remplacer. Ne pas utiliser un nettoyage global « kill-stale ».

## Lancement et logs

- Un processus supervisé par composant, lancé depuis son propre répertoire, avec
  le mécanisme persistant de l’outil utilisé : sessions `exec_command` /
  `write_stdin` dans Codex, commande Bash en arrière-plan dans Claude Code. Lire
  ensuite les fichiers de log ; ne pas supposer un outil propre à l’autre agent.
- Conserver stdout ET stderr complets dans un fichier par composant, sous un
  répertoire de session unique tel que `/tmp/fred-live-<session>/`. Éviter de
  filtrer à la capture : les lignes d’activités Temporal sont utiles à l’ingestion.
- Tenir un petit journal de session dans ce répertoire : composant, checkout,
  commande, identifiant de session/processus, log, état constaté. Cela permet
  de reprendre l’observation sans démarrer de doublons après une interruption.
- Démarrer les processus autorisés, puis lire chaque log. Vérifier le message
  de disponibilité et que le processus reste vivant ; pour les API/front, vérifier
  aussi les ports attendus. Un worker n’a pas nécessairement de port HTTP : sa
  connexion Temporal et son message de polling sont les preuves recherchées.
- Après environ deux minutes sans disponibilité, donner l’état et la dernière
  erreur utile plutôt que multiplier les relances. Ne pas masquer un échec par
  une boucle de redémarrage ni changer la configuration sans accord.
- Donner au développeur un tableau court : prêt / en démarrage / bloqué, URL UI
  lorsqu’elle est connue, et emplacement des logs.

## Observation pendant les essais UI

Lire les nouvelles lignes de TOUS les processus de la session avec des curseurs,
par petits lots pendant les tours actifs et à chaque signal du développeur.
Ne pas relire tout l’historique, ni surveiller seulement le dernier backend lancé.
Les fichiers continuent de recevoir les logs entre les tours ; ne pas prétendre
les analyser en continu lorsque l’assistant n’est plus actif.

Pour chaque action rapportée dans l’UI, corréler les horodatages et les identifiants
présents (task_id, document_uid, workflow_id, run_id). Rapporter brièvement :
ce qui a été observé, le composant, l’extrait utile expurgé de secrets, puis
l’hypothèse éventuelle et la prochaine action proposée. Une absence de log ne
prouve pas que l’action n’a pas eu lieu. Lire le code ciblé si cela aide à expliquer
les traces ; demander avant de corriger ou de reproduire soi-même l’action.

## Samples, uniquement sur demande

Pour WebDAV, travailler dans `~/Fred/fred-samples/knowledge-bases/webdav` :

- Pod KB : `make run`, avec son `config/.env` et son YAML. C’est un worker
  Temporal sans port entrant. Vérifier également le SDK réellement installé et
  le checkout visé par une installation editable, sans le réinstaller par défaut.
- Avec ou sans délégation, le pod KB lit le contexte de son run avec sa propre
  identité (compte de service du client lié à la définition) et écrit dans sa
  bibliothèque via le droit créé avec l’instance ; aucun grant n’est attendu.
  Un 403 sur le contexte signale un mauvais client ou un rôle de service absent.
- Serveur de test : lire la cible actuelle `make share-run` avant de la lancer.
  Elle peut construire une image et remplacer un conteneur existant : annoncer
  ces effets et demander avant remplacement. Le serveur de test demandé est
  distinct de l’infrastructure Docker Compose gérée par le développeur.
- Observer aussi `make share-logs`, les logs du pod, Knowledge Flow API/worker
  et Control Plane. Ne pas exécuter `make sync` / `make watch` automatiquement.
- `make publish` modifie le catalogue Fred : le proposer si la déclaration doit
  être créée ou actualisée, puis attendre l’accord. Ne pas changer d’identité
  M2M pour contourner un refus.

Pour un autre compagnon, lire son README/Makefile et ajouter seulement les
processus demandés au même journal de session. Ne pas ajouter l’évaluateur
ou d’autres services par défaut.

## Arrêt

Une instruction d’arrêt annule immédiatement les démarrages/redémarrages encore
prévus. Si des processus viennent déjà de repartir, les arrêter et le dire ; ne
pas reprendre la relance sur la base d’une autorisation antérieure. À la reprise
d’une session, vérifier les PID, groupes, ports et destinations de logs actuels :
un ancien journal ne prouve pas qu’un processus tourne encore. Les sessions
existantes peuvent avoir leurs logs sous `~/.local/state/fred-live/logs` ; vérifier
le checkout et la propriété des processus avant de les réutiliser ou remplacer.

À la demande du développeur, interrompre proprement seulement les processus
lancés par cette session et vérifier leur arrêt, y compris leurs enfants.
Pour un serveur de test, n’arrêter que le conteneur créé par cette session et
inclus dans la demande. Ne pas arrêter l’infrastructure ni les processus du
développeur. Conserver les logs et annoncer explicitement ce qui reste actif.
