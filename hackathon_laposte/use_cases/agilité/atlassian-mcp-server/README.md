# README

Lancer un service Docker Compose pour MCP Atlassian

Ce guide explique comment configurer et lancer le service "mcp-atlassian" avec Docker Compose en utilisant le réseau de la machine hôte et un fichier .env.

## Prérequis

- Docker installé
- Docker Compose installé

## Installation du serveur MCP atlassian

### 1. Fichier .env

Vous avez 2 options, soit utiliser votre propre compte, soit utiliser un compte générique créé pour l'occasion.

#### Crédentials génériques

Se procurer le fichier `.env` avec les variables d'environnement dans `serveur mcp atlassian` du [dossier partagé "Agilité" sur Cryptobox](https://thales.cryptobox.com/#/public/jAWtT23gEwzQB-33oZzK-pm2vhifZs5RdntsIlqSwfY/file/CwjlaPkSBjX0hc0K2fXIuQ) et le sauvegarder ici : `hackathon_laposte/use_cases/agilité/atlassian-mcp-server`.

#### Votre propre compte

1. Rendez vous sur votre page Atlassian admin: https://id.atlassian.com/manage-profile/security/api-tokens et créez un Jeton API, copiez la soigneusement.

2. Rejoignez le projet via les liens d'invitation:
* [Confluence](https://id.atlassian.com/invite/p/confluence?id=sqJT6hLORkuPsZoI5A_tVA&cloudId=f76bb79a-1a14-4905-91c4-f0807b3e8a24)
* [Jira](https://id.atlassian.com/invite/p/jira-software?id=qIbBhYfhTaGhMMGW3sjtOQ)

---

La clé d'accès à cryptobox sera partagée sur l'écran en séance.

```bash
cd hackathon_laposte/use_cases/agilité/atlassian-mcp-server

# Lancer le service
docker compose up -d

# Vérifier les logs
docker compose logs -f mcp-atlassian
```

### 2. Vérifier le fichier docker-compose.yml

Voici la configuration à utiliser, située dans le ficher `docker-compose.yml`:

```yaml
version: "3.8"
services:
  mcp-atlassian:
    image: ghcr.io/sooperset/mcp-atlassian:latest
    ports:
      - "8885:8885"
    env_file: ".env"
```

### 3. Lancer le service

Exécute la commande suivante à la racine du dossier contenant le fichier docker-compose.yml:

```bash
# Lancer le service
docker compose up -d
```

Le service sera disponible sur le port défini, ici "8885".

### 4. Vérifier que tout fonctionne

Pour vérifier que le container tourne:

```bash
docker ps
```

Pour voir les logs:

```bash
docker compose logs -f mcp-atlassian
```
