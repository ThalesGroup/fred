# Intégration des journaux Fred dans un SIEM

Ce guide s'adresse aux équipes qui collectent les journaux d'une installation Fred sur des VM avec Podman Compose et exploitent un SIEM. L'architecture retenue transmet les sorties des conteneurs à journald, puis à un relais syslog et à un agent de collecte qui les transmet au SIEM. Ce document décrit les sources à recevoir, les champs utiles et des scénarios de détection à construire. Il ne prescrit ni produit SIEM ni seuil universel.

Fred émet des **événements**, pas des alertes SIEM ni des règles exécutables. Un collecteur transmet les événements bruts au SIEM ; l'équipe de sécurité y définit les règles, les fenêtres de corrélation et le traitement des alertes. Les exemples ci-dessous sont des spécifications de détection à adapter au langage du SIEM retenu.

```text
Entra ID -------------------------------> SIEM
VM Podman -> journald -> syslog -> agent -> SIEM -> règles -> alertes
Entrée HTTP / WAF ----------------------> SIEM
```

## 1. Sources et responsabilités

| Source | Événements utiles | Acheminement attendu | Responsable de la source |
| --- | --- | --- | --- |
| `fred.security.audit` | Modifications de droits, accès à la plateforme, délégation, admission du runtime et invocations d'outils | Sortie standard JSON des conteneurs Fred, puis journald et relais syslog vers l'agent | Exploitant Fred pour l'émission ; exploitant SIEM pour la collecte |
| Logs applicatifs Fred | Réponses HTTP, refus d'autorisation, erreurs et diagnostics | Sorties des conteneurs, puis journald et relais syslog ; `app.log_format: json` sur chaque backend et worker concerné | Exploitant Fred |
| Proxy / frontend et entrée HTTP | Méthode, route, statut, volume et, selon le proxy d'entrée, IP source et décisions WAF | Journaux du proxy vers l'agent, via syslog si ce chemin est retenu | Exploitant de l'entrée HTTP |
| Microsoft Entra ID | Connexions utilisateur interactives et non interactives, connexions des principaux de service, changements de répertoire | Paramètres de diagnostic Entra vers la destination choisie par l'exploitant SIEM, par exemple Event Hubs | Administrateur Entra et exploitant SIEM |
| VM et Podman | Arrêts, redémarrages, erreurs du collecteur et absence de flux | Journaux système et supervision de l'agent | Exploitant des VM |

Fred écrit l'audit sur `stdout` en JSON avec `logger=fred.security.audit`. Ce flux est exclu du magasin de logs applicatifs Fred : **ne pas supposer qu'une requête OpenSearch sur ce magasin retrouve les audits**. L'acheminement durable, la rétention et la protection contre l'altération sont à établir dans l'infrastructure de collecte. Voir [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#5-stream-3--security--audit-trail).

La configuration Entra directe de Fred est décrite dans [Identity providers](IDENTITY-PROVIDERS.md#microsoft-entra-id-recipe). Entra remplace la source de connexion, mais les rôles applicatifs et les permissions Fred restent dans OpenFGA. Les journaux Entra ne prouvent donc pas qu'un rôle Fred a été accordé, et les audits Fred ne prouvent pas qu'une connexion Entra a réussi.

Par rapport à une installation Keycloak, cela change quatre choses pour le SIEM : aucune source Keycloak n'est à collecter ; les connexions humaines et des clients confidentiels viennent d'Entra ; les changements de configuration du tenant sont dans l'audit Entra, tandis que les changements de droits Fred restent dans l'audit Fred ; enfin, les identifiants des deux systèmes doivent être rapprochés et vérifiés. Cela ne change pas le format des audits Fred ni le principe de collecte sur les VM.

### Flux Entra à demander

Activer et acheminer au minimum les journaux de connexion utilisateur interactifs, non interactifs et des principaux de service, ainsi que les journaux d'audit du répertoire. Les premiers permettent de détecter les échecs, les succès, les conditions d'accès et l'usage des identités applicatives ; les derniers couvrent notamment les changements d'applications, d'utilisateurs et de groupes dans Entra. Ajouter les journaux d'identités managées si elles sont utilisées. Les catégories disponibles, les droits, les licences et la destination sont à vérifier avec l'administrateur du tenant. Microsoft décrit les [catégories exportables](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-diagnostic-settings-logs-options) et les [modes d'accès](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-access-activity-logs), dont les paramètres de diagnostic vers Event Hubs et l'API Microsoft Graph.

Filtrer les événements Entra sur les identifiants d'application de l'UI et de l'API Fred, ainsi que sur les clients confidentiels Fred. Une connexion du principal de service est un événement d'authentification de l'application, pas une connexion utilisateur. Ne pas mélanger leurs seuils.

## 2. Contrat de collecte sur VM

1. Vérifier le chemin `conteneur -> Podman -> journald -> relais syslog -> agent -> SIEM` et le pilote des conteneurs avec `podman info --format '{{ .Host.LogDriver }}'` et `podman inspect`. Podman ne liste pas `syslog` comme pilote natif de logs de conteneur : la configuration prévue utilise `journald`, puis un relais syslog sur la VM. Valider ces deux étapes avec la version et la configuration déployées. L'option globale `podman --syslog` concerne les messages de Podman et ne remplace pas l'acheminement de `stdout`/`stderr` des conteneurs. Voir la [documentation des pilotes](https://docs.podman.io/en/latest/markdown/podman-run.1.html) et celle de [`podman --syslog`](https://docs.podman.io/en/latest/markdown/podman.1.html).
2. Transmettre `stdout` et `stderr` de tous les backends, workers, runtimes d'agent, du frontend et du proxy. L'agent reçoit les messages syslog et doit extraire le JSON Fred du champ message, sans perdre l'enveloppe syslog. Conserver le JSON original de l'audit. Ajouter `host`, `container`, `service`, environnement et horodatage de réception, sans écraser les champs producteurs. Vérifier le découpage, la taille maximale et l'encodage d'un événement JSON long.
3. Router après décodage JSON par le champ structuré `logger`, pas par le texte de `msg` ni par le préfixe syslog. Réserver une destination et des droits d'accès adaptés aux événements `fred.security.audit`. Séparer les logs applicatifs, plus volumineux et moins durables. Éviter qu'un même événement soit ingéré deux fois par plusieurs chemins.
4. Prévoir une file locale bornée et un renvoi après interruption du relais ou du SIEM, une limite d'espace disque et une alerte en cas d'échec ou de silence du collecteur. Vérifier les redémarrages, la rotation des journaux Podman et la politique de transport syslog retenue. Mesurer les pertes et le délai entre émission et disponibilité dans le SIEM.
5. Transporter les journaux jusqu'au SIEM sur des canaux authentifiés et chiffrés lorsque le transport quitte la VM. Définir la rétention et les droits d'accès selon la politique de sécurité locale. Ne pas ajouter tokens, en-têtes d'authentification, URL signées, corps HTTP, messages utilisateur ou contenu documentaire aux événements.

Les accès JSON du frontend ne contiennent pas l'IP ni le chemin brut. Les diagnostics natifs sur `stderr` peuvent être du texte libre et demandent un traitement de confidentialité distinct. Pour une détection de scans, de blocages WAF ou de source réseau, utiliser les journaux du proxy d'entrée plutôt que d'inférer ces données des logs Fred. Voir [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#63-frontend-pod-logs).

## 3. Normalisation minimale

| Sens | Audit Fred | Log applicatif Fred | Entra / entrée HTTP |
| --- | --- | --- | --- |
| Temps de l'événement | `ts` (secondes Unix) | `timestamp` ou temps structuré du producteur | Temps de l'événement source |
| Provenance | `service`, `logger` | `service`, `logger`, `role` si présent | Tenant, application, hôte ou proxy |
| Type d'action | `extra.audit_event` | `message`, `route`, `http_method` ou `denial_cause` selon l'événement | Type d'opération source |
| Résultat | `extra.outcome`, `extra.reason` si présents | `outcome`, `http_status`, `denial_cause` si présents | Statut de connexion ou de décision |
| Acteur et cible | `extra.actor_uid`, `extra.user_id`, `extra.subject`, `extra.resource`, `extra.team_id` ou `extra.link_id` selon l'événement | `user_id` et références admises si présentes | Identifiant utilisateur, application ou principal de service |
| Corrélation | Champs `extra.*` explicitement émis | `request_id`, `correlation_id` si présents | Identifiants propres à Entra ou au proxy |

Un audit de relation peut ressembler à ceci. Les valeurs et certains champs varient selon l'appelant ; `actor_uid` peut manquer.

```json
{"ts": 1700000000.0, "level": "INFO", "logger": "fred.security.audit", "service": "control-plane", "msg": "[SECURITY] authz.relation.granted", "extra": {"audit_event": "authz.relation.granted", "actor_uid": "<actor-uid>", "subject": "user:<target-uid>", "relation": "platform_admin", "resource": "organization:fred"}}
```

Avec la recette Entra actuelle, Fred prend le claim `oid` du jeton d'accès comme identifiant utilisateur ; un identifiant non UUID est transformé en UUIDv5 à partir de l'émetteur et de la valeur. Pour une jointure Entra/Fred, valider sur un compte de test que le `oid` du même tenant correspond au `user_id` Fred observé. La clé de rapprochement doit inclure le tenant et l'application visée. Les `correlation_id` Entra et Fred sont générés séparément : **ne pas les joindre comme s'ils étaient communs**. Quand l'identité manque, conserver l'événement sans inventer d'acteur.

## 4. Catalogue initial des détections

Les fenêtres et seuils ci-dessous sont des points de départ à régler sur les volumes du site. Une action d'administration isolée peut être légitime ; le SIEM doit conserver l'événement même lorsqu'il ne déclenche pas d'alerte.

| ID | Priorité | Règle proposée | Sources | Disponibilité et limite |
| --- | --- | --- | --- | --- |
| D01 | Haute | Toute attribution de `platform_admin` sur `organization:fred` ; autres relations d'administration selon la matrice locale de rôles | `authz.relation.granted` | Immédiate. `actor_uid` peut manquer ; relier la cible par `subject`. |
| D02 | Haute | Attribution d'un droit élevé, suivie sous 30 minutes d'un changement de politique ou d'une action d'administration par la cible | Audit de relation + `platform.access.*` | Corrélation par identifiant Fred quand les deux événements le portent. |
| D03 | Haute | `platform.access.filtering.updated` avec `filtering_enabled=false`, ou toute modification de politique et tout octroi d'exception d'accès | `platform.access.filtering.updated`, `platform.access.policy.updated`, `platform.access.user.granted`, `platform.access.users.granted`, `platform.access.team.updated` | Immédiate. L'audit de politique donne sa révision, pas son contenu ; investiguer l'état autorisé séparément. |
| D04 | Haute | Ajout d'un secret ou certificat, changement de permission ou de consentement, ou modification d'une politique d'accès concernant les applications Fred | Audit du répertoire Entra | Les noms d'opération et champs exacts dépendent du flux Entra reçu ; filtrer sur les identifiants d'application enregistrés. |
| D05 | Haute | Plusieurs échecs de connexion Entra, puis un succès du même compte, puis une action D01-D04 | Connexions Entra + audits Fred et Entra | Exige l'export Entra et la validation de la jointure `oid`/tenant. Éviter de compter un renouvellement silencieux comme une nouvelle connexion interactive. |
| D06 | Moyenne | Une origine tente plusieurs comptes, ou un compte échoue depuis plusieurs origines, dans une fenêtre courte | Connexions Entra | Exige IP et statut Entra. Ajuster les seuils et exclure les causes applicatives connues ; les proxys/VPN partagent parfois une IP. |
| D07 | Moyenne | Échecs ou nouvelle provenance de connexion d'un client confidentiel Fred | Connexions des principaux de service Entra | Corréler par application, statut et IP. Ces événements peuvent être agrégés par Entra ; vérifier les horodatages et comptes avant de fixer un seuil. |
| D08 | Moyenne | Tentatives répétées d'accès aux sessions d'autrui ou à des ressources refusées | `session_owner_mismatch`, diagnostics `denial_cause=permission_refused` | Le refus de session est explicite ; avec la délégation activée, son audit perd les identifiants. Les refus génériques n'ont pas toujours une identité exploitable. |
| D09 | Moyenne | Plusieurs grants délégués rejetés, notamment `caller_not_trusted` ou `caller_not_allowed` | `delegation.grant.rejected` | Compter par service et motif. Cet audit ne porte pas d'identité ou d'IP pour attribuer seul la tentative. |
| D10 | Moyenne | Révélation d'un lien Free suivie d'adhésions, ou régénération d'un lien d'équipe suivie d'adhésions inhabituelles | `platform.access.link.revealed`, `platform.access.free.enrolled`, `team.join_link.regenerated`, `team.join_link.joined` | Joindre les événements Free par `link_id`. La régénération du lien d'équipe ne porte que `team_id` : corréler à ce niveau. |
| D11 | Moyenne | Pic de 401/403/404/5xx sur une route ou une origine, avec blocages WAF ou erreurs applicatives proches | Entrée HTTP + logs Fred | Le proxy apporte l'IP et le chemin ; Fred apporte la route bornée et le résultat. Une rafale seule ne prouve pas une intrusion. |
| D12 | Exploration | Invocation d'un outil rare, forte hausse de volume ou échecs répétés pour un compte ou une équipe | `agent.tool.invocation.started` et `.completed` | Les identités et noms d'outils peuvent être absents selon les réglages de délégation ; aucun contenu ou destination d'exfiltration n'est journalisé. |

Ne pas présenter comme couvertes la détection fiable d'exfiltration documentaire, les révocations de toutes les relations OpenFGA ou l'attribution d'une tentative déléguée à une IP. Ces cas demandent un inventaire et, éventuellement, de nouveaux événements bornés. Aujourd'hui, l'audit `authz.relation.revoked` est émis sur la révocation des rôles de plateforme, tandis que le point central d'écriture des relations audite les grants. Les événements du runtime et de délégation peuvent se limiter à l'événement, au résultat et au motif lorsque la délégation est activée. Voir [Observability and Audit](OBSERVABILITY-AND-AUDIT.md#5-stream-3--security--audit-trail).

Pour livrer D01 à un SIEM particulier, l'équipe sécurité traduit la spécification en requête native : sélectionner `logger=fred.security.audit`, `extra.audit_event=authz.relation.granted`, `extra.resource=organization:fred` et `extra.relation=platform_admin`, puis créer une alerte par événement avec `subject`, `actor_uid`, `service` et `ts`. Le langage exact, le format d'import et la politique de notification dépendent du SIEM. Les autres lignes du catalogue se traduisent de la même manière, avec agrégation temporelle lorsqu'elle est indiquée.

## 5. Recette de validation et critères d'acceptation

Sur un environnement de test représentatif, effectuer des actions autorisées et refusées sans utiliser de données réelles : connexion Entra réussie et échouée, connexion d'un client confidentiel, grant d'un rôle puis révocation, modification de la politique d'accès, accès à une session non possédée, grant délégué rejeté et invocation d'un outil de test.

Pour chaque action, vérifier dans le SIEM : événement brut consultable, enveloppe syslog et JSON conservés, source et horodatage corrects, champs normalisés typés, absence de secret et de contenu, absence de doublon, délai d'arrivée acceptable et règle déclenchée ou volontairement silencieuse. Puis interrompre temporairement le relais ou la destination SIEM et redémarrer un conteneur pour vérifier le rattrapage, les limites de file et l'alerte de collecte. Mesurer le taux d'alertes sur du trafic normal avant d'activer une notification opérationnelle.

L'exploitant SIEM doit confirmer avant mise en service : relais et format syslog effectifs, protocole de transport vers l'agent, accès au tenant Entra et catégories exportées, identifiants d'application Fred, politique de rétention, séparation d'accès aux audits, seuils et fenêtres, plage de maintenance, destinataire des alertes et procédure d'investigation. L'exploitant Fred fournit les versions, les noms de services et les scénarios de test ; l'équipe sécurité possède les règles SIEM et leur réglage dans le temps.
