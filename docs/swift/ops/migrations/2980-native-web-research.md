---
schema: 1
title: "Enable internal web research with direct or proxy access"
impact: minor
configuration: production
configuration_reason: "Adds default-off internal web_research, optional forward-proxy configuration, and restricted retained activity."
---

## Applicability

Native `web_search` and `fetch_url` for ReAct, Deep and Graph.
The engine runs inside Fred Agents. No additional Fred process, MCP server,
listening port, local TLS certificate or egress service token is required.

## Prerequisites

Fred's usual local infrastructure and a configured model must be available.
Allow public DNS/HTTP(S) for direct mode; for proxy mode configure the operator's
proxy and final destination policy before activation.

## Configuration

### Local activation

In the Fred Agents YAML selected by `config/.env`'s `CONFIG_FILE`, add at root:

```yaml
web_research:
  enabled: true
```

Start the usual local infrastructure and run Fred normally (`make run` from the
repository root). Fred Agents startup applies the existing runtime migration,
including the restricted activity table. Its process must have
working DNS and public HTTP(S) access. Enable Web research for the team and select
it on the agent through the existing capability controls. Ask the agent to search
for a public topic and to read `https://www.python.org/`.

### Production configuration

Helm fields live under `applications.fred-agents.configuration.web_research`:

```yaml
web_research:
  enabled: true
  provider: brave
  provider_key_env: WEB_RESEARCH_PROVIDER_KEY # Brave Search API key secret
  proxy_url: https://proxy.dmz.example:3128
  proxy_auth_env: WEB_RESEARCH_PROXY_AUTH # Optional Basic username:password secret
  proxy_ca_file: /run/secrets/proxy-ca.crt # Optional private HTTPS proxy CA
  cost_per_1000_searches: 5 # Contract price for the admin cost estimate
  max_results: 5 # Results sent to the model per search
  max_chars_per_page: 6000 # Text sent to the model per read page
  activity_retention_days: 30
  max_searches_per_user_per_day: 50 # Optional daily cap per user (UTC day); omit for no quota
  max_fetches_per_user_per_day: 200 # Optional daily cap on page reads per user
```

`provider` selects the search engine: `duckduckgo` (SDK default, keyless, no
SLA, local use), `fixture` (offline results from `fixture_file` or built-in
samples, for development and CI) or `brave` (Brave Search API key read from the
variable named by `provider_key_env`). The chart defaults to `brave`, so enabling
it without the key fails Fred Agents startup. Providers never fall back to one
another; an outage returns `provider_failed`. The key reaches only the provider
endpoint, never logs, activity or model arguments.

Without `proxy_url`, research uses direct public access. With it, every provider,
page and redirect uses the configured HTTP(S) forward proxy; failures never fall
back to direct access. `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` environment
variables do not select or bypass this route. Proxy secrets belong in the existing
Fred secret/environment mechanism, not URLs or model arguments. For an HTTP proxy,
omit `proxy_ca_file`; Basic credentials require a suitably protected network,
preferably an HTTPS proxy. Public origin TLS is always verified independently.
TLS interception and client certificates are not configured by this feature.

The operator owns the proxy deployment, firewall, DNS and monitoring. In proxy
mode, permit the Fred host only proxy connectivity for research egress. The proxy
MUST reject private/non-global and metadata destinations at connection time,
including mixed IPv4/IPv6 records, DNS rebinding and redirects. Fred resolves no
names in this mode, so the Fred host needs no external DNS: it refuses locally
non-public IP literals, numeric hosts and local names (single-label,
`localhost`, `.local`, `.internal`, `.svc`) and forwards other names to the
proxy, which therefore carries name-based SSRF protection. A 403 answer to an
HTTPS tunnel is reported as `proxy_refused` (counted as blocked); a 407 or 5xx
answer stays `unavailable`. A refused `http://` page appears as `http_error`. Test these controls on the actual DMZ.
No Fred-specific API or service executable belongs on the proxy host.

## Limitations

Default off; retention 30 days (1–365), purge every 60 seconds, four concurrent
operations and a 60-second operation deadline including queue/admission and
outbound I/O. Saturation returns `busy`; each activity write has its own 5-second
storage deadline. Defaults also bound pages to 5 MiB and ports 80/443. To limit
model context, at most `max_results` (default 5) results and `max_chars_per_page`
(default 6,000) characters per read page reach the model, whatever the tool
arguments request. For longer pages the model passes `focus` to get the relevant
passages, or reads without `focus` and continues with `offset` from the previous
`next_offset` (the two are mutually exclusive); each
continuation re-downloads the page and adds tokens, but is not billed by the provider. Optional per-user caps, `max_searches_per_user_per_day` and
`max_fetches_per_user_per_day` (unset by default: no quota), count the user's
requests per UTC calendar day from the activity table; any dispatched request
counts, whatever its outcome. Over a cap the tool returns `quota_exceeded`
before any network access, and each capped result shows the remaining count in
the trace detail. Erasing a user's activity also resets their quota for the day.
Configure these, `max_bytes`, `retries` and the `safesearch`
floor at deployment level. Direct access pins vetted public DNS addresses to connections.
All modes check redirects, refuse binary/compressed responses and isolate cookies.
Extraction/focus runs in bounded worker threads.

Before production enablement, approve raw-query storage and the chosen search
provider under deployment policy; DuckDuckGo HTML has no availability SLA and is
not intended for production load.
The restricted SQL sink must exist and SQL statement logging must be disabled.
Reads require `CAN_MANAGE_PLATFORM`. Account deletion keeps the activity until
expiry; to honour a right-to-erasure request, a user administrator
(`CAN_ADMINISTER_USERS`) calls
`DELETE /agents/web-research/activity/users/<opaque-id>` on Fred Agents, which
returns the number of deleted records.

## Validation

Platform admins see a "Web research" section on the Analytics page: tool calls
split into searches (billed) and page reads (not billed), estimated provider cost, blocked/saturated/failed requests by reason, p95 latency
and distinct users. Set `cost_per_1000_searches` to your provider contract price
(default 0) for the estimate; it counts successful searches only and excludes
retries, free tiers and LLM tokens. The section reads a content-free
`web_research.request` KPI event, so it requires the OpenSearch KPI store and
counts from the deployment of this version; restarts do not reset it.

In **Administration → Self-test**, run **Web research checks**: a deterministic
agent (no LLM) probes the deployment through the real port — refused URLs,
internal, metadata and encoded destinations, redirects, binary content,
SafeSearch floor, then a working search and page read — and reports each check.
It fails first when `web_research.enabled` is off. Probes needing an unreachable
third-party endpoint (httpbin.org, nip.io, example.com) are skipped, not passed;
in proxy mode they also show whether the proxy enforces the destination policy.
Each probe leaves a record in the restricted activity log.

Use Fred's existing Prometheus exporter and runtime dashboard: operation counts,
latency, failure/busy outcomes and activity-sink failures. Load the rules in
[deploy/web-research/alerts.yaml](../../../../deploy/web-research/alerts.yaml).
No extra `/health` or `/metrics` research server is exposed, and no periodic
public Internet probe runs; provider/proxy outages appear on attempted operations.

Using an authorized operator credential, inspect
`GET /agents/web-research/activity?user_id=<opaque-id>` after successful and failed
research. Check attribution/outcome, expiry and explicit erasure; no page bodies,
snippets, secrets or URL query/fragment are retained. Refuse private/metadata URLs
and redirects in both modes. Verify unavailable proxy returns a bounded failure
and there are no direct connections. Verify wrong HTTPS proxy trust is rejected.

## Upgrade

Remove `egress_url`, `token_env`, `ca_file`, `client_certificate`, `client_key` and
`WEB_RESEARCH_EGRESS_TOKEN`. Old YAML fields fail validation. Stop the draft Fred
egress process and retire its Compose/Kubernetes deployment; use direct access or
an operator-owned forward proxy instead. This revision reuses the activity schema;
no further SQL migration is required.

## Rollback

Disable `enabled` and deselect the capability before rollback. Keep the current
runtime available for purge/erasure until records expire, or erase them first.
Expiry is immediate for reads and physical deletion occurs on the next sweep.
Conversation-history retention remains governed by its existing separate policy.
