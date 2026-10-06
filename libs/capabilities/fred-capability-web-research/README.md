# Native web research

Installing this package registers `web_research` through `fred.capabilities`.
The agent uses `web_search`, `fetch_url` and `search_and_fetch` through the typed
SDK port; deployment policy, service credentials and user identity are never
model arguments. Fred Agents installs the package, with the egress extra, so
the same Fred image can also run the egress process in a DMZ.

Deployment, monitoring and retention instructions are in
[the operator note](../../../docs/swift/ops/migrations/2980-native-web-research.md).
No MCP server registration is involved.
