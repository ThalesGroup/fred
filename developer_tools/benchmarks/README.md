## Mock OpenAI server + Agentic benchmark quickstart

### 1) Clone and run the mock server
```bash
git clone https://github.com/freakynit/mock-openai-server.git
cd mock-openai-server
npm install
npm run server
```

Expected output:
```
> mock-llm@1.0.0 server
> node src/server.js

Delaying all responses by 1933 milliseconds
Mock OpenAI API server is running at http://0.0.0.0:8383
```

The server reads `config.yaml`. Example settings:
```yaml
publicFilesDirectory: "public"
server:
  host: 0.0.0.0
  port: 8383
apiKeys:
  - "key-1"
  - "key-2"
  - "key-3"
organizationName: "my sample org"
responseDelay:
  enable: true
  minDelayMs: 10000
  maxDelayMs: 10100
```

### 2) Point Agentic to the mock server
Edit `agentic-backend/config/configuration_benchmarks.yaml` (or your chosen config):
- `ai.default_chat_model.settings.base_url: "http://localhost:8383/v1"`
- `ai.default_language_model.settings.base_url: "http://localhost:8383/v1"`

Set `OPENAI_API_KEY` to one of the `apiKeys` in the mock server `config.yaml`.

Example:
```bash
# DO NOT FORGET TO CHANGE THE OPENAI URL IF YOU USE THE MOCK SERVER
#export OPENAI_API_KEY=key-1
# export base_url=http://localhost:8383/v1
export CONFIG_FILE=./agentic-backend/config/configuration_prod.yaml
export OPENAI_API_KEY=key-1
```

Start Agentic:
```bash
cd agentic-backend
uv run uvicorn agentic_backend.main:create_app --factory --host 0.0.0.0 --port 8000 --log-level info
```

### 3) Run the Go benchmark client
From `developer_tools/benchmarks`:
```bash
AGENTIC_TOKEN=<bearer-token> make run ARGS='-clients=20 -requests-per-client=5'
```

When Agentic runs inside the local `k3d` cluster instead of directly on your
host, do not target `localhost:8000`. Use the Traefik ingress address exposed
by the cluster, for example `ws://172.19.0.2/agentic/v1/chatbot/query/ws`.
You can confirm the ingress address with:
```bash
kubectl get ingress -n fred
```

Defaults:
- Sessions are prepared per client before measuring.
- Sessions are deleted after the run.
- The benchmark target defaults to `ws://localhost:8000/agentic/v1/chatbot/query/ws`.
- The benchmark expects a bearer token via `AGENTIC_TOKEN` (or `-token`).
- When backend auth is disabled for local development, any placeholder such as `fake-token` is enough.

To benchmark a real RAG path, use the public `Rico` agent. By default, if you
do not pass `-document-library-ids`, Rico searches across all document
libraries the current user is allowed to access:

```bash
AGENTIC_TOKEN=<bearer-token> make run ARGS='\
  -url ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent Rico \
  -message "Quelle est la fréquence recommandée des sprints ?" \
  -search-policy=hybrid \
  -search-rag-scope=corpus_only \
  -clients=20 \
  -requests-per-client=5 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -read-limit-bytes=8388608'
```

Example with a local dev token placeholder:

```bash
AGENTIC_TOKEN=fake-token make run ARGS='\
  -url ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent Rico \
  -message "Quelle est la fréquence recommandée des sprints ?" \
  -search-policy=hybrid \
  -search-rag-scope=corpus_only \
  -clients=20 \
  -requests-per-client=5 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -read-limit-bytes=8388608'
```

For local v2 bench runs, the two canonical `make run` commands are:

Mode `existing-agent`:
```bash
AGENTIC_TOKEN="$TOKEN" make run ARGS='\
  -url ws://172.19.0.2/agentic/v1/chatbot/query/ws \
  -agent-uuid=2f2e7e9f-6df4-4df1-8b5f-4d9af1e8c111 \
  -message "Quelle est la frequence recommandee des sprints ?" \
  -clients=20 \
  -requests-per-client=5 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -read-limit-bytes=8388608'
```

Mode `normal`:
```bash
AGENTIC_TOKEN="$TOKEN" make run ARGS='\
  -url ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent basic.react.v2 \
  -ensure-v2-definition-ref=v2.react.basic \
  -ensure-agent-name="Bench Basic ReAct" \
  -message "Quelle est la frequence recommandee des sprints ?" \
  -clients=20 \
  -requests-per-client=5 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -delete-created-agent=true \
  -read-limit-bytes=8388608'
```

If `-agent-uuid` is set, the benchmark reuses that existing agent and ignores
`-ensure-v2-definition-ref` / `-ensure-v2-profile-id`.

Mode `rag`:
```bash
AGENTIC_TOKEN="$TOKEN" make run ARGS='\
  -url ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent basic.react.v2 \
  -ensure-v2-profile-id=rag_expert \
  -ensure-agent-name="Bench RAG Expert" \
  -message "Quelle est la frequence recommandee des sprints ?" \
  -search-policy=hybrid \
  -search-rag-scope=corpus_only \
  -clients=20 \
  -requests-per-client=5 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -delete-created-agent=true \
  -read-limit-bytes=8388608'
```

To simulate many users sending requests at the same time, increase `-clients`
and keep `-ramp-duration=0s` so they all start together:

```bash
AGENTIC_TOKEN=<bearer-token> make run ARGS='\
  -url ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent Rico \
  -message "Quelle est la fréquence recommandée des sprints ?" \
  -search-policy=hybrid \
  -search-rag-scope=corpus_only \
  -clients=100 \
  -requests-per-client=10 \
  -create-session=true \
  -prepare-sessions=true \
  -delete-session=true \
  -prepare-concurrency=50 \
  -ramp-duration=0s \
  -read-limit-bytes=8388608'
```

Useful RAG/load flags:
- Omitting `-document-library-ids` lets Rico search across all libraries the current user can access.
- `-document-library-ids=a,b` populates `runtime_context.selected_document_libraries_ids` when you want to restrict the run to specific libraries.
- `-document-uids=a,b` restricts retrieval to specific documents.
- `-search-policy=semantic|hybrid|strict` forwards the retrieval policy.
- `-search-rag-scope=corpus_only|hybrid|general_only` steers whether corpus retrieval should be used.
- `-clients` controls how many users are simulated concurrently.
- `-requests-per-client` controls how many sequential asks each simulated user sends.
- `-prepare-sessions=true` creates one session per user before measurement, which is usually the cleanest setup for RAG load tests.
- `-ramp-duration=0s` starts all clients at once; use `30s` or more for a gentler ramp-up.
- `-read-limit-bytes=8388608` avoids client-side read failures when RAG answers or source payloads are large.

### 4) Container + Helm (run inside Kubernetes)
Build and push the benchmark image:
```bash
cd developer_tools/benchmarks
docker build -t <registry>/agentic-bench:latest .
docker push <registry>/agentic-bench:latest
```

Deploy as a one-off Job with the provided chart:
```bash
helm upgrade --install agentic-bench deploy/charts/agentic-bench \
  --set image.repository=<registry>/agentic-bench \
  --set image.tag=latest \
  --set bench.url=ws://agentic-backend:8000/agentic/v1/chatbot/query/ws \
  --set tokenSecret.name=agentic-bench-token \
  --set tokenSecret.key=token
```
Create the token secret first (the client reads `AGENTIC_TOKEN`):
```bash
kubectl create secret generic agentic-bench-token \
  --from-literal=token=<bearer-token> \
  -n <namespace>
```
The chart does not mint a token from Keycloak. It expects a bearer token to be
provided up front through `tokenSecret`.

The chart now supports two modes through `bench.mode`:
- `rag` (default): creates a temporary v2 Basic ReAct agent from `profile_id=rag_expert`, sends RAG websocket requests with `search_policy=hybrid`, and forces `search_rag_scope=corpus_only`.
- `normal`: creates a temporary classic v2 ReAct agent from `definition_ref=v2.react.basic` and runs the same load pattern without RAG-specific retrieval flags.
- `existing`: reuses `bench.common.agentUUID` and skips any agent bootstrap.

Values are split between:
- `bench.common` for shared benchmark settings such as URL, concurrency, session lifecycle, message, and optional `agentUUID`.
- `bench.modes.normal` / `bench.modes.rag` / `bench.modes.existing` for mode-specific agent bootstrap and retrieval settings.

Adjust `bench.clients`, `bench.requestsPerClient`, or pass
`bench.tokenInQuery=true` if the server expects the token in the query string.

For `bench.mode=existing`, set the values explicitly so the Job targets an
already-created agent instead of bootstrapping one. The minimal values look
like this:

```yaml
bench:
  mode: existing
  common:
    # Inside the cluster, prefer the service DNS name exposed by the ingress or service.
    url: ws://agentic-backend/agentic/v1/chatbot/query/ws
    agentUUID: "6451efbb-2a9b-4792-8e3a-9bee05af7dd0"
    message: "Bonjour"
    clients: 1
    requestsPerClient: 1
    createSession: true
    prepareSessions: false
    deleteSession: true
    timeoutSeconds: 30

tokenSecret:
  name: agentic-bench-token
  key: token
  optional: false
```

Create the secret with a user token that is allowed to create sessions and read
the target agent:

```bash
kubectl create secret generic agentic-bench-token \
  -n <namespace> \
  --from-literal=token="$TOKEN"
```

Notes for `existing` mode:
- `bench.common.agentUUID` is required.
- `bench.modes.existing` can stay as-is; no `ensureV2DefinitionRef`, no `ensureV2ProfileID`, and no `deleteCreatedAgent`.
- The token must belong to a user who can both create a session and access that agent UUID.
- If the benchmark runs inside Kubernetes, use the in-cluster websocket URL, not `localhost:8000`.

Examples:

```bash
helm upgrade --install agentic-bench deploy/charts/agentic-bench \
  -n <namespace> \
  --set image.repository=<registry>/agentic-bench \
  --set image.tag=latest \
  --set tokenSecret.name=agentic-bench-token \
  --set bench.mode=rag
```

```bash
helm upgrade --install agentic-bench deploy/charts/agentic-bench \
  -n <namespace> \
  --set image.repository=<registry>/agentic-bench \
  --set image.tag=latest \
  --set tokenSecret.name=agentic-bench-token \
  --set bench.mode=normal
```

```bash
helm upgrade --install agentic-bench deploy/charts/agentic-bench \
  -n <namespace> \
  --set image.repository=<registry>/agentic-bench \
  --set image.tag=latest \
  --set tokenSecret.name=agentic-bench-token \
  --set bench.mode=existing \
  --set bench.common.agentUUID=2f2e7e9f-6df4-4df1-8b5f-4d9af1e8c111
```
