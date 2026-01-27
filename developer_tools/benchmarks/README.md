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
export CONFIG_FILE=./agentic-backend/config/configuration_benchmarks.yaml
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
make run ARGS='-clients=20 -requests-per-client=5'
```

Defaults:
- Sessions are prepared per client before measuring.
- Sessions are deleted after the run.
- The benchmark target defaults to `ws://localhost:8000/agentic/v1/chatbot/query/ws`.

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
Adjust `bench.clients`, `bench.requests`, or pass `bench.tokenInQuery=true` if the server expects the token in the query string.
