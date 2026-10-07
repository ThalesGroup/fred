# Native web research

Installing this package registers `web_research` through `fred.capabilities`.
This package holds only the two tools and their citations; like every other
capability it calls the typed SDK port (`ctx.services.web_research`). The engine
and search providers are runtime services in `fred_runtime/app/web_research_*.py`.
Deployment configuration and user identity stay outside model arguments.

Enable `web_research.enabled` and start Fred normally: no extra process, MCP
server, local certificate or service token. Without `proxy_url`, outbound access
is direct. An explicitly configured HTTP(S) forward proxy routes all research
traffic; its operator enforces the final DNS/destination policy.

See [activation, proxy and retention instructions](../../../docs/swift/ops/migrations/2980-native-web-research.md).
