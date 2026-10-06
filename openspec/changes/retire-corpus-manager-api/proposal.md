## Why

The corpus-management HTTP facade was retained when its MCP transport was retired, leaving an unused public API, generated client surface, and dedicated maintenance code. The user has confirmed that this whole facade, including its real revectorization and vector-metadata repair endpoints, should be removed.

## What Changes

- **BREAKING** Remove every `/corpus/*` corpus-manager HTTP endpoint, its controller, service, request/response models, generated frontend client methods, and endpoint authorization inventory.
- Remove maintenance workflows and activities that are reachable only through those endpoints, plus their dedicated tests and stale operational guidance.
- Keep the independent `/documents/tree` corpus listing, ordinary ingestion and vector-search APIs, and the direct HTTP `/fs` filesystem API.
- Document upgrade implications for callers and any in-flight maintenance tasks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-capabilities`: The retired corpus MCP no longer leaves a corpus-manager HTTP API behind; native document listing and other independent APIs remain supported.

## Impact

Knowledge Flow routes, scheduler registrations, tests, OpenAPI and generated frontend types, authorization endpoint matrix, active contract documentation, and the current draft PR migration note.
