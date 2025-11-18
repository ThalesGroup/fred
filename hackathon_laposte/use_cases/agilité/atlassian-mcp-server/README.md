# README

Lancer un service Docker Compose pour MCP Atlassian

Ce guide explique comment configurer et lancer le service "mcp-atlassian" avec Docker Compose en utilisant le réseau de la machine hôte et un fichier .env.

## 0. TLDR

Se procurer le fichier `.env` avec les variables d'environnement dans le [dossier partagé "Agilité" sur Cryptobox](https://thales.cryptobox.com/#/public/jAWtT23gEwzQB-33oZzK-pm2vhifZs5RdntsIlqSwfY/file/CwjlaPkSBjX0hc0K2fXIuQ) et le sauvegarder ici même.

La clé d'accès sera partagée sur l'écran en séance.

```bash
cd hackathon_laposte/use_cases/agilité/atlassian-mcp-server

# Lancer le service
docker compose -f docker-compose-atlassian-mcp.yml up -d

# Vérifier les logs
docker compose -f docker-compose-atlassian-mcp.yml logs -f mcp-atlassian
```

## 1. Prérequis

- Docker installé
- Docker Compose installé

## 2. Fichier docker-compose.yml

Voici la configuration à utiliser située dans le ficher `docker-compose-atlassian-mcp.yml`:

```yaml
version: "3.8"
services:
  mcp-atlassian:
    image: ghcr.io/sooperset/mcp-atlassian:latest
    ports:
      - "8885:8885"
    env_file: ".env"
```

## 3. Fichier .env

Se procurer le fichier `.env` avec les variables d'environnement dans le [dossier partagé "Agilité" sur Cryptobox](https://thales.cryptobox.com/#/public/jAWtT23gEwzQB-33oZzK-pm2vhifZs5RdntsIlqSwfY/file/CwjlaPkSBjX0hc0K2fXIuQ) et le sauvegarder ici même.

La clé d'accès sera partagée sur l'écran en séance.

## 4. Lancer le service

Exécute la commande suivante à la racine du dossier contenant le fichier docker-compose.yml:

```bash
# Lancer le service en dehors du devcontainer
docker compose -f docker-compose-atlassian-mcp.yml up -d
```

Le service sera disponible sur le port défini, ici "8885".

## 5. Vérifier que tout fonctionne

Pour vérifier que le container tourne:

```bash
docker ps
```

Pour voir les logs:

```bash
docker compose -f docker-compose-atlassian-mcp.yml logs -f mcp-atlassian
```
