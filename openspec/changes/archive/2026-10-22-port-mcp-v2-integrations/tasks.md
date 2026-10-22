## 1. Client compatibility

- [x] 1.1 Pin `langchain[mcp]` with FastMCP 4 and MCP SDK v2 in the runtime; verify dependency resolution and imports in its locked environment.
- [x] 1.2 Replace `MultiServerMCPClient` discovery and lifecycle with the first-party `MCPAdapter`; verify `streamable_http` and `stdio` tool listing and calls without a Fred-owned tool wrapper.
- [x] 1.3 Move live person bearer refresh and one-time expiry retry to the call boundary; verify a token change after discovery and a 401 retry with targeted tests.
- [x] 1.4 Preserve delegated grant, M2M auth, origin confinement, redirect refusal, and authority-loss handling; verify each with targeted security tests.
- [x] 1.5 Preserve tool names, server metadata, structured results, and error mapping in ReAct and Graph consumers using adapter results; verify affected runtime integration tests.

## 2. Knowledge Flow server compatibility

- [x] 2.1 Compare existing enabled-server tool names, descriptions, and input schemas against the current Knowledge Flow mounts during the migration.
- [x] 2.2 Replace `FastApiMCP` mounts with a FastMCP 4 OpenAPI projection at the same paths and tag filters; verify selected tools, callable arguments, and disabled-server behavior.
- [x] 2.3 Rebuild the verified-grant and inner FastAPI request bridge without `fastapi-mcp` private APIs; verify authorized calls, refusals, SQL 400 envelope, and redaction in security tests.
- [x] 2.4 Remove the v1 session-manager patch and serve stateless MCP HTTP; verify alternating requests across two Knowledge Flow app instances.

## 3. Dependencies and rollout

- [x] 3.1 Replace v1-only dependencies and MCP `<2` constraints in core, runtime, and Knowledge Flow; update all affected uv lockfiles and verify `uv lock --check` in each package.
- [x] 3.2 Document SDK v2 and legacy peer interoperability, supported runtime transports, and rollout/rollback in the existing deployment documentation; verify examples against the catalog model.
- [x] 3.3 Run v2 client-to-Knowledge Flow and legacy peer HTTP smoke tests, then the root `make code-quality` gate once the change is complete; record results in the PR.
- [x] 3.4 Review the full branch against `swift`, obtain an independent read-only review, resolve findings, reconcile this change with implementation, sync the delta spec, and archive the change; verify the draft PR has no unresolved checks before requesting final review.
