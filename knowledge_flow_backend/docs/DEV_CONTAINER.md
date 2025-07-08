# VS Code Dev-Container Guide

This project ships a **Dev Container** that launches Knowledge-Flow plus its dependencies (OpenSearch, MinIO, etc.) in one command. You get a ready-to-code IDE without installing Python, uv, or extra services on your machine.

---

## Prerequisites

| Tool | Purpose |
|------|---------|
| **Docker** / Docker Desktop | Runs the container stack |
| **VS Code** | Primary IDE |
| **Dev Containers extension** (`ms-vscode-remote.remote-containers`) | Required to open the repo in a container |

---

## One-time OpenAI key

```bash
mkdir -p ~/.fred
echo "OPENAI_API_KEY=sk-..." > ~/.fred/openai-api-key.env
```

This file is mounted into the `devcontainer` service via `env_file` in the main `docker-compose.yml`.

---

## Opening the Dev Container

1. **Clone** the repo (or open your existing clone) in VS Code.  
2. Press <kbd>F1</kbd> → **Dev Containers: Reopen in Container**.  
3. VS Code reads `.devcontainer/devcontainer.json` which refers to two compose files:  
   - `deploy/docker-compose/docker-compose.yml` (core stack)  
   - `.devcontainer/docker-compose-devcontainer.yml` (Dev-only overrides)  
4. The `devcontainer` image is built from `.devcontainer/Dockerfile-devcontainer`. Once running you’ll see “Knowledge-flow Dev” in the VS Code status bar.

---

## What’s Running

| Service        | Port | Notes |
|----------------|------|-------|
| **Knowledge-Flow API** | 8111 | FastAPI backend |
| OpenSearch      | internal | Available inside the stack |
| MinIO           | internal | Bucket storage |
| OpenSearch Dashboards | internal | Depends on health check |

The container forwards port **8111** to your host so Swagger is reachable at `http://localhost:8111/knowledge/v1/docs`.

---

## Using the Container

Open a terminal in VS Code (it’s already logged in as `dev-user` at `/app`):

```bash
# (inside container)
make run      # start the FastAPI server
```

If you prefer VS Code’s debugger:

1. Open the **Run & Debug** panel.  
2. Choose **Launch FastAPI App** (defined in `.vscode/launch.json`).  
3. Hit ▶ to start; breakpoints now work.

---

## Rebuilding / Updating

- **Rebuild image:** <kbd>F1</kbd> → *Dev Containers: Rebuild Container*  
- **Stop stack:** Close VS Code or run `docker compose down` from `deploy/docker-compose/`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Port 8111 already in use | Stop other processes or change exposed port in `docker-compose-devcontainer.yml`. |
| Missing OpenAI key errors | Verify `~/.fred/openai-api-key.env` exists and contains `OPENAI_API_KEY`. |
| Dependencies outdated | Rebuild the container to refresh `make dev` install. |

---

You’re now ready to develop Knowledge-Flow with a fully provisioned environment—no local Python or database setup required.
