---
schema: 1
title: "Enable native web research through authenticated HTTPS egress"
impact: minor
configuration: production
configuration_reason: "Adds default-off Fred Agents web_research configuration, a restricted activity table, and a separately operated HTTPS egress process."
---

## Applicability

Fred deployments adding the native `web_research` capability. The change is
default-off and does not register an external MCP server. The three tools are
`web_search`, `fetch_url` and `search_and_fetch` on ReAct, Deep and Graph agents.

## Prerequisites

Agree the storage of raw search queries under the deployment's confidentiality
policy before activation. Restrict access to activity records to platform
operators (`CAN_MANAGE_PLATFORM`); user administrators can erase a user's
records (`CAN_ADMINISTER_USERS`). Provision the normal Fred runtime PostgreSQL
database, a TLS certificate/trust chain and a service token of at least 32
characters in the operator secret store. Confirm the DuckDuckGo HTML provider
is permitted and reliable enough for your workload; it has no availability SLA.

## Configuration

The Fred Helm configuration lives at
`applications.fred-agents.configuration.web_research`. Set `enabled: true`,
`egress_url: https://<dmz-host>:8120` and supply `WEB_RESEARCH_EGRESS_TOKEN` in
the existing runtime secret/environment mechanism. For a private CA, mount it
and set `ca_file`. Optionally configure `client_certificate` and `client_key`
for mTLS, and `tls_client_ca` on the egress process. Never disable verification.
The endpoint is deployment configuration and cannot be changed by an agent.

Defaults: 30 days of activity retention, a 60-second purge/health interval,
4 concurrent runtime requests, and a 60-second deadline covering outbound queue wait and HTTPS.
Each activity write has a separate 5-second storage deadline.
Omitted configuration disables the transport. Activity retention continues
after disablement while the current runtime remains deployed. Expired records
are immediately hidden from reads and physically purged on the next sweep.

The egress process uses `ENV_FILE` and `CONFIG_FILE` with the usual defaults.
Its non-secret configuration is [deploy/web-research/configuration.yaml](../../../../deploy/web-research/configuration.yaml).
It requires the same service token and TLS key/certificate. DuckDuckGo receives the documented `kp` SafeSearch parameter through the same
DNS-pinned transport as page fetches; redirects from the provider fail closed.
The service clamps SafeSearch
to the configured floor, limits each page to 5 MiB and 50,000 returned characters,
and accepts only HTTP(S) destinations on ports 80/443. HTML extraction uses
trafilatura; focus selection is lexical, as in the V1.

## Upgrade

1. Run the existing `python -m fred_runtime migrate`/Helm migration hook before
   enabling the capability. It creates `runtime_web_research_activity` with
   user and expiration indexes. Boot fails closed when enabled without its table
   or service credentials.
2. Deploy the egress process from the same reviewed Fred Agents image, with
   command `python -m fred_capability_web_research.egress`. For local execution,
   use the capability package's virtual environment and the supplied
   `configuration.yaml`, with mounted TLS material and `CONFIG_FILE` set.
   A VM can run that command under its existing service manager. Docker and
   Podman can use [the Compose example](../../../../deploy/web-research/compose.yaml);
   [the Kubernetes example](../../../../deploy/web-research/kubernetes.yaml)
   supplies Deployment, Service and network policy for a separate DMZ namespace.
3. Permit the Fred Agents host to reach the DMZ HTTPS port. Permit the DMZ only
   public web destinations and its trusted DNS resolver; deny internal,
   link-local, metadata and transition addresses. The Kubernetes policy requires
   a CNI that enforces it. Adapt namespace labels, DNS selectors and routes to
   the actual platform. Apply equivalent firewall rules to VM/container hosts.
   Keep Fred's existing LLM/model routes; web research itself only uses the gateway.
4. Enable the deployment configuration and restart Fred Agents. Enable the
   capability for the selected team and select it on the agent through the
   existing Fred capability controls. No knowledge-flow route is required.

## Validation

Enable the existing Fred Prometheus exporter and scrape authenticated egress
`/metrics` with a bearer token stored in Prometheus secret configuration.
Check authenticated `GET /health` on the egress service and
`fred_web_research_egress_up == 1` on Fred's existing Prometheus endpoint.
The Kubernetes TCP readiness probe checks listening only; Fred's health polling
checks service authentication and TLS. Ask the selected agent to search and read
a public page; inspect `GET /agents/web-research/activity?user_id=<opaque-id>`
using an authorized operator credential. Each logical request has one record,
with its request/session correlation, query or sanitized URL, outcome and count.
Page text/snippets, tokens, headers and URL query/fragment are excluded.

Verify an internal/metadata URL and a redirect to it are refused, DMZ outage
returns a bounded tool error, and user deletion erases records on every enabled
runtime before identity-provider deletion. A runtime erasure failure blocks
account deletion for retry; suspension already prevents new authorized requests.

Import the web panels in [the Fred runtime dashboard](../../../../deploy/grafana/fred-agent-runtime.json)
and [the alert rules](../../../../deploy/web-research/alerts.yaml). Collect the
existing runtime metrics and optionally authenticated egress `/metrics`.
No monitoring label contains user identity or query text.

## Rollback

Disable `web_research.enabled` and remove it from selected agents before stopping
the egress process. Keep the current runtime available for activity purge and
user erasure until retained records expire, or erase those records using the
authorized user-erasure endpoint first. Downgrading the SQL revision deletes
the activity table permanently; export it only under an approved restricted
storage policy if evidence must be retained. Queries also exist in conversation
history under its own existing policy; this migration does not change it.

## Limitations

Operators own DMZ placement, certificates, secrets, firewall/CNI policy, metrics
collection and data-access policy. This is a restricted product activity store,
not an immutable security evidence store. No browser scripting, authenticated
websites, binary downloads, crawling or search history UI are included. Search
and extraction provider logs are suppressed to keep content out of diagnostic
streams. The Python HTTPX pool seam used for the vetted network backend is
covered by connection tests and must be checked when upgrading HTTPX/httpcore.

User erasure also persists a SHA-256 subject marker without the original identity
or query. It prevents late writes from requests already running in other replicas;
retain this fence while the deployment could accept requests for that subject.
Provider SafeSearch values follow [DuckDuckGo's documented parameters](https://duckduckgo.com/duckduckgo-help-pages/settings/params).
