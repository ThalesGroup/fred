# Guide de Démarrage Rapide – Hackathon Agent Agile

## Introduction

Bienvenue à ce hackathon ! L'objectif de ces journées est de construire et de personnaliser un **Agent Conversationnel Expert Agile** capable d'interagir avec des ressources documentaires et un environnement Jira/Confluence.

Ce guide est votre feuille de route pour mettre en place rapidement l'environnement technique basé sur le **Model Context Protocol (MCP)** et la plateforme Fred. Suivez les étapes ci-dessous pour maximiser votre temps de développement.

---

## Prérequis : Ce Dont Vous Avez Besoin

Avant de commencer, assurez-vous que les outils suivants sont installés sur votre machine. Ils sont essentiels pour travailler avec l'environnement **Dev Container** recommandé.

- **Git**
- **Docker**
- **Visual Studio Code (VS Code)**
- **Extension VS Code :** `Dev Containers`

---

# Phase 1 : Installation et Démarrage de l'Infrastructure

## 1. Téléchargement des Ressources

Les ressources du hackathon (données & fichier contenant les variables d'environnement nécessaires au bon fonctionnement du serveur MCP Atlassian) sont disponibles via le SharePoint La Poste ou le lien [Cryptobox fourni](https://thales.cryptobox.com/#/public/jAWtT23gEwzQB-33oZzK-pm2vhifZs5RdntsIlqSwfY/file/CwjlaPkSBjX0hc0K2fXIuQ).

> **⚠️ IMPORTANT – Priorité !**
> Les ressources sont volumineuses (~ 200Mo). **Lancez le téléchargement immédiatement** avant de passer aux étapes suivantes. Cela vous fera gagner un temps précieux pendant que les conteneurs se construisent et que vous vous empariez du sujet.

## 2. Accès au Jira de Test

Pour vos tests manuels et la vérification des données source, vous avez accès à un compte Jira en **lecture seule**.

- **Login :** `laposte.jirauser@gmail.com`
- **Mot de passe :** _Disponible auprès de l'équipe support (Simon Cariou) ou sur le canal Teams dédié._

## 3. Lancement du Serveur MCP Jira

Nous allons utiliser un **Dev Container** pour isoler l'environnement du serveur.

1. **Ouvrir le Projet :** Dans VS Code, ouvrez Fred.
2. **Lancer le Dev Container :** Suivez l'invite pour rouvrir le projet dans un conteneur de développement ou tapez `Ctrl + Shift + P` et entrez `Reopen in container`
3. **Démarrer le Serveur :** Une fois dans le conteneur, suivez les instructions spécifiques pour lancer le serveur Jira MCP.
   Le guide détaillé pour cette étape se trouve ici : [README du Serveur MCP Atlassian](./atlassian-mcp-server/README.md)

---

# Phase 2 : Configuration de l'Agent et Connexion des Services

## 1. Tour d'horizon des outils fournis par le serveur MCP Atlassian avec `MCP Inspector`

Utilisez `MCP Inspector` pour confirmer que le serveur MCP est bien accessible.

Dans le terminal (à l'intérieur ou à l'extérieur du Dev Container), exécutez :

```bash
npx @modelcontextprotocol/inspector@0.17.2
```

Une fois la page web de l'interface utilisateur ouverte, configurez l'outil avec les paramètres suivants :

- **Transport Type :** `Streamable HTTP`
- **URL :** `http://127.0.0.1:8885/mcp`
- **Connection type :** `Via Proxy`

> **Conseil de Dépannage (Dev Container) :** Si la connexion échoue, vérifiez les ports forwardés dans VS Code. Il arrive que le port `6274` soit mappé sur un autre port externe (ex: `6275`). Si c'est le cas, vous devez utiliser l'URL affichée par l'Inspector dans votre navigateur, par exemple : `http://localhost:6274//?MCP_PROXY_AUTH_TOKEN...`

## 2. Ingestion des Documents (knowledge-flow)

Votre agent a besoin de connaissances. Utilisez l'interface d'administration des ressources pour les importer.

Rendez-vous dans l'onglet **Ressources** et:

1. **Créer les Bibliothèques :** Structurez les bibliothèques documentaires basées sur l'arborescence des données que vous avez téléchargées:

```bash

├── La Poste
│   ├── Assessments workshop
│   │   ├── ...
│   ├── Executive workshop
│   │   └── ...
│   ├── Facilitors guide
│   │   ├── ...
│   ├── Planning toolkit
│   │   ├── ...
│   └── VSAI toolkit
│       ├── ...

```

2. **Lancer l'Ingestion :** Importez les documents dans les bibliothèques correspondantes.

## 3. Création et Association de l'Agent

Créons maintenant votre Agent Agile dans l'**Agent Hub**.

1. Dans **`Agent Hub`**, cliquez sur **`Créer`** pour instancier un nouvel agent.
2. Accédez à ses **Réglages**.
3. Associez-lui les deux serveurs MCP pour qu'il puisse accéder aux données et à Jira :
   - `mcp-atlassian-jira-server`
   - `mcp-knowledge-flow-text`
4. Modifiez son rôle et sa description pour le personnaliser.
5. Terminez en cliquant sur **`APPLIQUER LES MODIFICATIONS POUR TOUS LES UTILISATEURS`**.

_Pour information : La configuration qui rend ces serveurs disponibles dans l'Agent Hub ressemble à ceci :_

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

## 4. Définition du Contexte de Conversation (Personnalisation de l'agent)

Pour garantir que l'agent se comporte comme un coach Agile, nous allons lui donner un profil clair.

1. Rendez-vous sur la page **`Ressources`**, onglet **`CONTEXTES DE CONVERSATION`**.
2. Créez une nouvelle bibliothèque nommée **`Agilité`**.
3. À l'intérieur, créez un nouveau contexte avec le contenu ci-dessous :

```
Tu es un agent Expert Agile Senior et Coach.

- Rôle: Guider l'équipe "Hackathon Laposte" pour maximiser la valeur et assurer l'adhérence aux principes Agiles (Scrum, Kanban).

- Expertise (Documentation interne): Management Agile (leadership, feedback) et facilitation de rétrospectives efficaces.

- Outils et Contexte:
  * Projet: Hackathon Laposte.
  * Confluence: Espace Software Development (Clé: SD) (pour PI Planning, comptes rendus, rétrospectives).

- Consigne/Style: Fournir des conseils structurés, pratiques et actionnables.
```

Vous pouvez jouer à le changer afin d'observer les changements de comportement de votre agent.

4. Associez ce **Contexte de Conversation** à votre agent via la page de Chat.

---

# Phase 3 : Validation et Scénarios de Test

Votre agent est prêt ! Posez-lui des questions et demandez-lui des actions pour vérifier l'intégration complète.

## 1. Testez l'Intégration Jira et Confluence

**Requêtes :**

- Combien de story points ont été complétés dans le sprint 1 ? et combien en reste-t-il à finir ?
- Quels sont les tickets qui n'ont pas été commencés ?
- Les tickets en "To Do" sont-ils suffisamment caractérisés pour être traités ?

**Actions :**

- Passe le ticket XX à "In Progress" et commente "Je peux prendre le point, estimation de travail : 2 story points".

## 2. Testez l'Intégration Documentaire (Knowledge Flow)

- Comment faire une bonne rétrospective de sprint ?
- En regardant les documents dans Confluence, peux-tu me dire quels sont les points à aborder dans la rétrospective ?

## 3. Testez les Capacités de Génération et d'Action

- Crée-moi un plan de rétrospective avec 3 points à améliorer, basé sur les tickets non terminés du Sprint en cours et le document de rétrospective du Sprint 0.
- Crée une nouvelle page Confluence intitulée 'Rétrospective Sprint 1' et intègre-y le plan généré.

---

# Ressources et Support

## Liens Utiles

Voici quelques liens qui pourraient vous être nécessaires pendant le hackathon :

- **Site vitrine :** [https://fredk8.dev/](https://fredk8.dev/)
- **Tableau de Bord Jira :** [Jira](https://hackathon-laposte.atlassian.net/)
- **Tableau de Bord Confluence :** [Confluence](https://hackathon-laposte.atlassian.net/wiki/spaces/SD)
- **Dépôt GitHub du serveur MCP :** `https://github.com/sooperset/mcp-atlassian` (pour référence et investigation)

## Aide et Support Technique

En cas de problème technique ou de question sur le contexte, n'hésitez pas à solliciter les organisateurs.

- **Canal d'Aide Principal :** Canal Teams créé pour l'occasion
- **Contact Direct :** [Simon Cariou] (ou l'équipe d'encadrement présente sur place).

---

# Conclusion et Prochaines Étapes

Félicitations ! Vous avez suivi les étapes avec brio. Vous avez maintenant toutes les clés en main pour créer un agent coach Agile et expérimenter par vous-mêmes les capacités de Fred.

S'il vous reste un peu de temps vous pouvez imaginer intégrer un autre serveur MCP en cherchant sur des pages telles que [MCP Market > Collaboration tools](https://mcpmarket.com/categories/collaboration-tools) ou une autre catégorie pour surcharger les capacités de votre agent.
