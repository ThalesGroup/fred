## Why

Fred has no first-party, governed web search capability. The attached `mcp_web_get.py` proves search and page extraction, but runs as an external MCP server and cannot by itself enforce Fred's user attribution, deployment egress policy, or retention. This change makes web research available to selected agents across deployment platforms while keeping outbound access controlled and observable.

Tracked by [GitHub issue #2980](https://github.com/ThalesGroup/fred/issues/2980).

## What Changes

- Add one Fred web research capability with `web_search`, `fetch_url`, and `search_and_fetch`, based on the V1 behavior and exposed through Fred's normal capability selection and tool execution path.
- Route all outbound search and page requests through a configurable HTTPS egress service. A deployment may place that service in a DMZ; local, Docker, Podman and Kubernetes deployments use the same protocol and configuration contract.
- Restrict destinations and response size, and treat retrieved content as untrusted tool output.
- Record searchable, user-attributed activity in a dedicated restricted store with a default 30-day retention policy; emit content-free metrics and standard tool audit events.
- Provide deployment configuration, health checks, dashboards/alerts and operator guidance for the egress path.

## Capabilities

### New Capabilities

- `web-research`: governed external search and page reading for Fred agents.

### Modified Capabilities

- Existing observability guidance: document the dedicated search activity record and its privacy boundary without putting query text into generic audit or metrics.

## Impact

- A Fred capability package, an egress adapter/service and deployment values/examples are required. The current V1 is a behavioral reference, not code or instructions to copy wholesale.
- Existing agent execution, capability authorization and tool audit mechanisms remain the entry point. Operators must configure an HTTPS endpoint and its trust/authentication material before enabling the capability.
- The proposed record of full search queries is a product/privacy contract change. Its 30-day default, access roles and deletion behavior are documented as operator approval prerequisites before production activation.

## Out of Scope

- General-purpose browsing, authenticated websites, arbitrary HTTP headers supplied by the model, binary downloads, crawling, indexing and a user-facing search history page.
- A Fred-specific WORM audit store or a universal outbound proxy for unrelated services.
