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
