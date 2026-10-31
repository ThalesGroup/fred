---
name: fred
description: Démarrer les composants Fred locaux et, sur demande, un pod fred-samples et son serveur de test ; observer leurs logs pendant que le développeur teste dans l’UI. Utiliser pour une session locale de démarrage, arrêt ou diagnostic par les logs, sans campagne de tests ni collecte KPI.
---

# Fred — démarrage et observation locale

Le développeur pilote l’UI et gère Docker Compose (Keycloak, Postgres,
Temporal, OpenSearch et autres services d’infrastructure). L’assistant
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
| Control Plane API et tâches de fond | `apps/control-plane` | `make run` |
| Knowledge Flow API | `apps/knowledge-flow-backend` | `make run` |
| Knowledge Flow worker | `apps/knowledge-flow-backend` | `make run-worker` |
| Fred Agents API | `apps/fred-agents` | `make run` |
| Frontend | `apps/frontend` | `make run` |

Ce sont des commandes disponibles, pas une liste de processus obligatoires.
Respecter le profil et les composants demandés ; vérifier leurs dépendances dans
le checkout actuel.

## Configuration et authentification

Lire `AGENTS.md`, les README et Makefiles actuels des composants avant le lancement.
Le Control Plane Rust sert l'API et ses tâches de fond dans le même processus ;
ne pas chercher un ancien worker Python séparé. Le profil réellement choisi
détermine quels services Python sont utiles. Ne pas démarrer un composant seulement
parce qu'il apparaît dans un ancien scénario Swift.

Inspecter la configuration effective et les prérequis sans afficher les secrets.
Pour Control Plane, suivre `apps/control-plane/README.md` ; une migration de base
n'est pas un effet annexe autorisé par une demande de lecture de logs. Pour les
composants Python, vérifier leurs mécanismes actuels de délégation et d'identité.
Ne jamais assouplir audience, issuer, isolation ou contrôle d'accès pour démarrer.
Un refus d'authentification est à diagnostiquer, pas à contourner.

La collecte de KPI et les tests de renouvellement ne font pas partie du démarrage.
Sur demande, utiliser `live-observability-session` avec les émetteurs/exporteurs
actuels et les références d'exploitation arc42. Ne pas réactiver d'anciens réglages
ou scripts Swift sans vérifier leur compatibilité. Les modifications de durée de
jeton, publications, migrations et campagnes doivent appartenir au périmètre demandé.

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
