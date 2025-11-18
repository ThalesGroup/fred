# Guide Hackathon

## Mise en place et utilisation des ressources

## 1. Télécharger les ressources

Les ressources sont disponibles sur le SharePoint ou sur le lien Cryptobox fourni. Vous devez lancer le téléchargement avant de passer à l'étape suivante afin de ne pas être bloqué plus tard.

## 2. Accéder au Jira de test

Compte en lecture seule:

- **Login**: laposte.jirauser@gmail.com
- **Mot de passe**: <Demander à Simon Cariou>

## 3. Lancer le serveur MCP Jira

Déployer le serveur dans le devcontainer en suivant les étapes décrites dans le [README](./atlassian-mcp-server/README.md)

Source du serveur MCP utilisé: https://github.com/sooperset/mcp-atlassian

## 4. MCP Inspector

Dans le devcontainer ou en dehors:

```bash
npx @modelcontextprotocol/inspector@0.17.2
```

Transport Type: `Streamable HTTP`
URL: `http://127.0.0.1:8885/mcp`
Connection type: `Via Proxy`

### Troubleshooting

1. Si la connexion au serveur MCP ne fonctionne pas, vérifiez les logs du MCP inspector. Dans un devcontainer, il arrive que le port forwardé à l'extérieur soit différent de celui attendu. Assurez vous que vous ouvrez la page web avec le port `6274`: `http://localhost:6274//?MCP_PROXY_AUTH_TOKEN...`

## 5. Observer la configuration du backend agentique

```yaml
mcp:
  servers:
    - name: "mcp-knowledge-flow-text"
      transport: "streamable_http"
      url: "http://localhost:8111/knowledge-flow/v1/mcp-text"
      sse_read_timeout: 2000
      auth_mode: "user_token"
    - name: "mcp-atlassian-jira-server"
      transport: "streamable_http"
      url: "http://localhost:8885/mcp"
      sse_read_timeout: 2000
      auth_mode: "no_token"
```

## 6. Ingestion des documents

Créer les librairies basées sur l'arborescence des données téléchargées puis ingérer les documents.

## 7. Créer un agent dynamiquement

Dans `Agent Hub`, cliquer dans `Create`.

Aller dans ses réglages et lui associer les serveurs MCP: `mcp-atlassian-jira-server` et `mcp-knowledge-flow-text`.

On peut aussi lui changer son rôle et sa description.

Cliquer sur `APPLIQUER LES MODIFICATIONS POUR TOUS LES UTILISATEURS`

## 8. Customiser son agent via contexte de conversation

Il est possible d'indiquer des informations à l'agent pour lui passer des informations qu'il ne pourrait pas deviner tout seul, lui demander de parler d'une certaine manière.

C'est ce que nous allons faire ici.

1. Veuillez vous rendre dans la page `Ressources` dans l'onglet `CONTEXTES DE CONVERSATION` et créer une bibliothèque nommée `Agilité`.
1. Cliquer sur le dossier Agilité et sur `CREER UN CONTEXTE DE CONVERSATION` avec le contenu suivant:

```
Tu es un agent Expert Agile Senior et Coach.

- Rôle: Guider l'équipe "Hackathon Laposte" pour maximiser la valeur et assurer l'adhérence aux principes Agiles (Scrum, Kanban).

- Expertise (Documentation interne): Management Agile (leadership, feedback) et facilitation de rétrospectives efficaces.

- Outils et Contexte:
  * Projet: Hackathon Laposte.
  * Confluence: Espace Software Development (Clé: SD) (pour PI Planning, comptes rendus, rétrospectives).

- Consigne/Style: Fournir des conseils structurés, pratiques et actionnables.
```

Associer ce `Chat Context` à l'agent via la page de Chat.

## 9. Scenario

Poser des questions sur les documents et le Jira/Confluence pour vérifier le fonctionnement.

Exemples:

- Combien de story points ont été complétés dans le sprint 1 ? et combien en reste-t-il a finir ?
- Quels sont les tickets qui n'ont pas été commencés ?
- Les tickets en to do sont-ils suffisament caractérisés pour être traités ?
- Passe le ticket xx à in progress et commente "Je peux prendre le point, estimation de travail: 2 story points"

- Comment faire une bonne rétrospective de sprint ?
- En regardant les documents dans Confluence, peux tu me dire quels sont les points à aborder dans la rétrospective ?
- Crée-moi un plan de rétrospective avec 3 points à améliorer, basé sur les tickets non terminés du Sprint en cours et le document de rétrospective du Sprint 0
- Créé une nouvelle page Confluence intitulée 'Rétrospective Sprint 1' et intègre-y le plan généré
