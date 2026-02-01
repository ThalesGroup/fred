# Workspace & Filesystem (v1)

## Overview
Dans Fred, la gestion des fichiers est une fonctionnalité centrale qui permet aux agents et aux utilisateurs de collaborer. Qu'il s'agisse d'analyser un PDF uploadé par un utilisateur ou de générer un rapport PowerPoint, le système doit garantir que les fichiers sont stockés de manière sécurisée, organisée et accessible.

Cette fonctionnalité repose sur une architecture en deux couches : le **Filesystem** (stockage physique) et le **Workspace** (logique d'organisation), permettant d'abstraire la complexité technique pour les agents.

## Usage
Le stockage est organisé en trois zones distinctes, définies dans la configuration (`workspace_layout`). Chaque zone répond à un besoin précis :

1.  **Zone Utilisateur (`users/<uid>/`) — *L'Espace Commun***
    *   **C'est quoi ?** Le dossier "Mes Documents" de l'utilisateur.
    *   **Pour qui ?** Partagé entre l'Utilisateur (via l'UI) et l'Agent (via MCP).
    *   **Scénario type :** L'utilisateur dépose un document de référence. L'agent le lit, l'analyse, et génère un rapport de synthèse dans ce même dossier que l'utilisateur peut ensuite télécharger.

2.  **Zone Config Agent (`agents/<agent_id>/config/`) — *Le Cerveau***
    *   **C'est quoi ?** Les ressources statiques de l'agent (Read-Only pour l'agent).
    *   **Pour qui ?** L'Agent (en lecture seule) et les Admins (en écriture).
    *   **Scénario type :** Stockage des templates PowerPoint, des fichiers de configuration JSON ou des bases de connaissances spécifiques à un agent.

3.  **Zone Mémoire Agent (`agents/<agent_id>/users/<uid>/`) — *Le Carnet de Notes***
    *   **C'est quoi ?** La mémoire privée de l'agent sur un utilisateur précis.
    *   **Pour qui ?** L'Agent uniquement.
    *   **Scénario type :** L'agent y stocke des préférences utilisateur, des brouillons ou des souvenirs à long terme pour personnaliser les futures interactions, sans polluer l'espace documentaire de l'utilisateur.

## Comprendre
L'architecture distingue l'ouvrier (Filesystem) de l'architecte (Workspace).

*   **Le Filesystem (L'Ouvrier)** : C'est la couche basse (MinIO, Disque Local). Il stocke des octets bêtement. Si on lui demande d'écrire dans un dossier qui n'existe pas, il échoue.
*   **Le Workspace (L'Architecte)** : C'est la façade intelligente. On ne parle jamais au Filesystem en direct ; on passe toujours par le Workspace.

**Pourquoi ce découpage ?**
1.  **Sécurité (Chroot)** : Quand un Agent écrit `/rapport.txt`, le Workspace traduit silencieusement ce chemin en `users/uid-123/rapport.txt`. L'agent est "enfermé" dans son espace et ne peut pas accéder aux fichiers des autres.
2.  **Robustesse** : Le Workspace gère les détails techniques pénibles. Par exemple, il effectue un `mkdir -p` implicite avant chaque écriture, évitant les erreurs "Path not found" typiques de MinIO sur des buckets vierges.

## Pour les développeurs

**Flux Technique**
Les deux points d'entrée principaux utilisent la même classe `WorkspaceFilesystem` :
*   `McpFilesystemService` : Pour les interactions de l'IA via le protocole MCP.
*   `WorkspaceStorageController` : Pour les interactions Web via l'API HTTP.

**Dépannage**
*   **L'agent ne voit pas un fichier ?** Vérifiez s'il a été uploadé dans la *Zone Utilisateur* et non dans la *Zone Mémoire Agent*.
*   **Erreur "Path not found" ?** Vérifiez que vous passez bien par la façade Workspace (`WorkspaceFilesystem.put()`) qui gère la création des dossiers parents.
*   **Fichiers clés :** `workspace_filesystem.py` (la logique intelligente), `mcp_fs_service.py` (l'exposition à l'agent), `workspace_storage_controller.py` (les endpoints HTTP).