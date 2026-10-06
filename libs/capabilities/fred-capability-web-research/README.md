# Native web research

Installing this package registers `web_research` through `fred.capabilities`.
The runtime executes search and extraction internally using the typed SDK port.
Deployment configuration and user identity stay outside model arguments.

Enable `web_research.enabled` and start Fred normally: no extra process, MCP
server, local certificate or service token. Without `proxy_url`, outbound access
is direct. An explicitly configured HTTP(S) forward proxy routes all research
traffic; its operator enforces the final DNS/destination policy.

See [activation, proxy and retention instructions](../../../docs/swift/ops/migrations/2980-native-web-research.md).
