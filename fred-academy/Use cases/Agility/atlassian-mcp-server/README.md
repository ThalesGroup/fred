# README

Start a Docker Compose service for MCP Atlassian

This guide explains how to configure and launch the **“mcp-atlassian”** service with Docker Compose using the host machine’s network and a `.env` file.

## Prerequisites

- Docker installed
- Docker Compose installed

## Installing the MCP Atlassian server

### 1. `.env` file

Copy paste the `.env.template` in a `.env` file and use your variables to enable the atlassian server access to your jira.

### 2. Check the docker-compose.yml file

Here is the configuration to use, located in the `docker-compose.yml` file:

```yaml
version: "3.8"
services:
  mcp-atlassian:
    image: ghcr.io/sooperset/mcp-atlassian:latest
    ports:
      - "8885:8885"
    env_file: ".env"
```

### 3. Start the service

Run the following command at the root of the folder containing the `docker-compose.yml` file:

```bash
cd hackathon_laposte/use_cases/agilité/atlassian-mcp-server

# Start the service
docker compose up -d
```

The service will be available on the port defined, here **8885**.

### 4. Check that everything is working

To verify that the container is running:

```bash
docker ps
```

To view the logs:

```bash
docker compose logs -f mcp-atlassian
```
