## Context

See proposal.md. The SDK already resolves catalog resources, while runtime boot
injects their resolved servers into transport and capability registration.
Pod configuration already contains Knowledge Flow and optional control-plane URLs.
The developer authorized implementation and clarified that internal MCPs should
name their backend/service, without hardcoded URLs.

## Goals / Non-Goals

**Goals:** Retain the configured scheme, host, port and API prefix when appending
an MCP path. Keep capability packages independent of runtime imports.

**Non-Goals:** Network discovery, extra operational configuration, per-turn service
lookup, or changes to McpCapability and inprocess tool adapters.

## Decisions

- Add SDK `FredService` and `ServiceEndpointsPort.get_base_url(service)`. The URL
  includes its port and API prefix; a second port setting would duplicate config.
  Runtime `ConfiguredServiceEndpoints` reads `AgentPodConfig`'s existing URLs.
- Catalog-only `service` and `path` fields resolve before exposing the existing
  server model. Append the path without URL-join semantics that discard API prefixes.
  Reject unknown services, competing URLs, malformed references and missing addresses.
- Every packaged internal server names `knowledge_flow`. Inprocess entries omit
  `path` and retain no remote MCP URL; their existing adapter already uses runtime KF
  configuration. HTTP service references require a path.
- The local, unreleased `fred.mcp_catalogs` loader contract receives the SDK port as
  one argument. External catalogs can also use references; concrete URLs and override
  precedence remain intact. No signature introspection or compatibility registry.
- Helm internal defaults use the same references. Worktree tooling continues to
  patch pod configuration, so it no longer needs to rewrite internal package YAML.

## Risks / Trade-offs

- Incorrect reference → fail during boot with server/service context.
- API prefix loss → exercise trailing slash, custom prefix, non-default port and HTTPS.
- Existing deployment overrides → retain literal URL support and full replacement.

## Migration Plan

Deploy image and chart together. Existing literal-URL catalogs remain valid.
New symbolic catalogs require this runtime; revert the catalog when rolling back
to an older image. Update the existing migration note for this local MCP extraction.
