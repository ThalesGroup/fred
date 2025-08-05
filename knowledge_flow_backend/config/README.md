# Configuration Guide for Knowledge Flow Backend

This folder contains all the configuration files needed to run the Knowledge Flow backend in different environments.

## TL;DR – Which file do I use?

| Config File                  | Purpose                                                                 |
|-----------------------------|-------------------------------------------------------------------------|
| `configuration_dev.yaml`    | ✅ Default: local dev mode, in-memory vector store, local disk storage. |
| `configuration_prod.yaml`   | 🛠️ Production-style: uses MinIO + OpenSearch. Requires Docker Compose.  |
| `configuration_worker.yaml` | ⚙️ Worker mode: runs **only** as a Temporal worker (no FastAPI).        |
| `configuration.yaml`        | 🔁 Default entrypoint. Aliased to `configuration_dev.yaml`.             |

---

## Details

### `configuration_dev.yaml`

- Default for local development.
- Uses in-memory vector store and local file storage.
- **No data persistence** — restarting the app will wipe everything.

> Good for quick tests, debugging, and development without external dependencies.

---

### `configuration_prod.yaml`

- Production-style configuration.
- Uses:
  - 🗃️ **MinIO** for file storage.
  - 🔍 **OpenSearch** for metadata and vector index.
- Requires Docker Compose (or external services) to be running.
- Recommended for more realistic tests and production deployments.

---

### `configuration_worker.yaml`

- Runs the backend as a **Temporal worker** only.
- No FastAPI server.
- Use this when running the ingestion workers separately from the API.

---

### `configuration.yaml`

- Default entrypoint used by the app.
- Just an alias — by default it points to `configuration_dev.yaml`, but you can switch it.

---

## Environment Variables

Environment-specific secrets and credentials are **not hardcoded** in these files.

- Use `.env` to set environment variables.
- A sample is provided in `.env.template` — copy it to `.env` and fill in the required values.

```bash
cp .env.template .env
```

You’ll need to provide values for:

- LLM API keys / tokens
- Access credentials for MinIO, OpenSearch, Temporal, etc.

---

## Tips

- To run in **dev mode**, nothing external is needed — just launch the app.
- To run in **prod mode**, make sure you start the required services (e.g., via `docker-compose up`).
- To run the **worker**, use the appropriate entrypoint and make sure Temporal is reachable.

---

Happy hacking! 🧠📚
