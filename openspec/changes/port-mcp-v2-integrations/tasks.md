## 1. Client compatibility

- [ ] 1.1 Pin an MCP v2-compatible FastMCP client in the runtime and verify dependency resolution and imports in its locked environment.
- [ ] 1.2 Replace `MultiServerMCPClient` discovery and lifecycle with Fred-owned MCP tool wrappers; verify `streamable_http` and `stdio` tool listing and calls through focused runtime tests.
- [ ] 1.3 Move live person bearer refresh and one-time expiry retry to the call boundary; verify a token change after discovery and a 401 retry with targeted tests.
- [ ] 1.4 Preserve delegated grant, M2M auth, origin confinement, redirect refusal, and authority-loss handling; verify each with targeted security tests.
- [ ] 1.5 Preserve tool names, server metadata, structured results, and error mapping in ReAct and Graph consumers; verify affected runtime integration tests.

## 2. Knowledge Flow server compatibility

- [ ] 2.1 Capture existing enabled-server tool names, descriptions, and input schemas as comparison fixtures; verify fixtures against current Knowledge Flow mounts.
- [ ] 2.2 Replace `FastApiMCP` mounts with a FastMCP 4 OpenAPI projection at the same paths and tag filters; verify parity fixtures and disabled-server behavior.
- [ ] 2.3 Rebuild the verified-grant and inner FastAPI request bridge without `fastapi-mcp` private APIs; verify authorized calls, refusals, SQL 400 envelope, and redaction in security tests.
- [ ] 2.4 Remove the v1 session-manager patch and serve stateless MCP HTTP; verify alternating requests across two Knowledge Flow app instances.

## 3. Dependencies and rollout

- [ ] 3.1 Replace v1-only dependencies and MCP `<2` constraints in core, runtime, and Knowledge Flow; update all affected uv lockfiles and verify `uv lock --check` in each package.
- [ ] 3.2 Document SDK v2 and legacy peer interoperability, supported runtime transports, and rollout/rollback in the existing deployment documentation; verify examples against the catalog model.
- [ ] 3.3 Run v2 client-to-Knowledge Flow and legacy peer HTTP smoke tests, then the root `make code-quality` gate once the change is complete; record results in the PR.
- [ ] 3.4 Review the full branch against `swift`, obtain an independent read-only review, resolve findings, reconcile this change with implementation, sync the delta spec, and archive the change; verify the draft PR has no unresolved checks before requesting final review.
