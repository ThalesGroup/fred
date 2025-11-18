# Guide Hackathon

## Mise en place et utilisation des ressources

## 1. Télécharger les ressources

Les ressources sont disponibles sur le SharePoint ou sur le lien Cryptobox fourni. Vous devez lancer le téléchargement avant de passer à l'étape suivante afin de ne pas être bloqué plus tard.

## 2. Accéder au Jira de test

Compte en lecture seule:

**Login**: laposte.jirauser@gmail.com
**Mot de passe**: <Demander à Simon Cariou>

## 3. Lancer le serveur MCP Jira

Déployer le serveur dans le devcontainer en suivant les étapes décrites dans le [README](./atlassian-mcp-server/README.md)

Source du serveur MCP utilisé: https://github.com/sooperset/mcp-atlassian

## 4. MCP Inspector

Dans le devcontainer:

```bash
npx @modelcontextprotocol/inspector
```

Connection type: Via Proxy
Addresse: http://127.0.0.1:8885/mcp

## 5. Observer la configuration du backend agentique

```yaml
mcp:
  servers:
    - name: "mcp-atlassian-jira-server"
      transport: "streamable_http"
      url: "http://localhost:8885/mcp"
      sse_read_timeout: 2000
      auth_mode: "no_token"
```

## 6. Ingestion des documents

Créer les librairies basées sur l'arborescence des données téléchargées puis ingérer les documents.

## 7. Créer un agent dynamiquement

Dans "Agent Hub", aller dans "Create".

Aller dans ses réglages et lui associer les serveurs MCP: `mcp-atlassian-jira-server` et `mcp-knowledge-flow-text`.

On peut aussi lui changer son rôle et sa description.

## 8. Tester

Poser des questions sur les documents et le Jira/Confluence pour vérifier le fonctionnement.

Exemples:

- Comment faire une bonne rétrospective de sprint ?
- Combien de story points ont été complétés dans le sprint 1 ? et combien en reste-t-il a finir ?
- Comment faire une bonne rétrospective de sprint ? Et basé sur les tickets du sprint 1 crée moi un plan de rétrospective
- En regardant les documents dans Confluence, peux tu me dire quels sont les points à aborder dans la rétrospective ?
- Quels sont les tickets en todo ?
- Passe le ticket xx à in progress et commente "Je peux prendre le point, estimation de travail: 2 story points"
