# Web Research Specification

## Purpose

Provide native, governed web research for Fred agents through internal direct or proxy access, with restricted activity retention and content-free monitoring.

## Requirements

### Requirement: Governed web research tools

Fred SHALL expose bounded `web_search` and `fetch_url` tools only to agents for which the web research capability is enabled and authorized. Search SHALL support result count, SafeSearch, region and freshness; fetch SHALL return bounded main text and source metadata, with optional focus. The same behavior SHALL work across supported agent execution models.

#### Scenario: Authorized search
- **WHEN** an authorized agent invokes `web_search` with a query and valid filters
- **THEN** Fred returns bounded titles, public URLs and snippets with source attribution
- **AND** the call is recorded with its user and outcome

#### Scenario: Reading the rest of a long page
- **WHEN** a page read without focus holds more text than the per-page ceiling
- **THEN** the result marks it truncated and gives the next offset, and a call with that offset and no focus returns the following part within the same ceiling
- **AND** a call combining focus and offset is rejected, because the offset is a position in the full page

#### Scenario: Deployment context ceilings
- **WHEN** a tool call requests more results or page text than the deployment `max_results` or `max_chars_per_page` allows
- **THEN** Fred returns at most those ceilings to the model and cites only the returned pages

#### Scenario: Disabled or unauthorized capability
- **WHEN** the capability is disabled or the current user loses permission
- **THEN** Fred does not dispatch an outbound request

### Requirement: Controlled external egress

Fred SHALL execute research internally, directly or through an explicitly configured HTTP(S) forward proxy, with no proxy-to-direct fallback. It MUST reject unsafe URLs, redirects and excessive/non-text responses. Direct connections MUST pin public DNS results. In proxy mode Fred MUST NOT resolve names locally and the proxy MUST enforce public-only final destinations. Origin TLS MUST remain verified and proxy credentials MUST NOT reach origins.

#### Scenario: Split-VM deployment
- **WHEN** Fred runs on an application VM configured with a forward proxy on a DMZ VM
- **THEN** every research request uses that proxy, origin TLS remains verified, and the proxy enforces public-only final destinations

#### Scenario: Redirect to an internal address
- **WHEN** a public page redirects to an internal or non-global destination
- **THEN** Fred refuses the fetch before dispatch, and a configured proxy independently enforces its destination policy

#### Scenario: Egress unavailable
- **WHEN** the provider or configured proxy times out or rejects the request
- **THEN** the tool returns a bounded failure without exposing transport credentials or raw exception text

#### Scenario: Local direct research
- **WHEN** web research is enabled without a proxy and Fred starts normally
- **THEN** the tools work through Fred's internal engine without an additional service, local TLS certificate or egress token

#### Scenario: Proxy routing and credentials
- **WHEN** a deployment configures a proxy with credentials and a private proxy CA
- **THEN** provider calls and every page/redirect request use the proxy with verified origin TLS
- **AND** proxy credentials stay outside model arguments, activity, diagnostic logs and origin headers

#### Scenario: Proxy unavailable
- **WHEN** the configured proxy is unavailable
- **THEN** Fred returns a bounded error without opening a direct Internet connection

#### Scenario: Network without external DNS
- **WHEN** Fred runs behind a configured proxy on a network without external DNS
- **THEN** fetches and search results with public host names go to the proxy unresolved
- **AND** non-public IP literals, numeric hosts in any form and names that cannot be public (single-label, `localhost`, `.local`, `.internal`, `.svc`) are refused locally without any connection

#### Scenario: Proxy refuses a destination
- **WHEN** the proxy answers 403 to the tunnel for an HTTPS page
- **THEN** the tool returns `proxy_refused`, distinct from `unavailable` (proxy unreachable, 407 or 5xx), with a short instruction telling the model not to retry that site, and analytics count it as blocked

#### Scenario: Admin self-test
- **WHEN** a platform administrator runs the web research self-test
- **THEN** a deterministic agent exercises the real per-user port with a fixed probe battery and reports each protection as passed, failed or skipped
- **AND** it fails first, probing nothing, when web research is not enabled or its activity store is not ready

### Requirement: Attributed, retained search activity

Fred SHALL record each dispatched research request with opaque subject/correlation IDs, query or public URL, timing and outcome. Records SHALL exclude page bodies, snippets and credentials. Access SHALL be restricted to platform operators and records SHALL expire after a configurable 30-day default. Deleting an account SHALL NOT erase its activity, which remains a security trace until expiry; an administrator SHALL be able to erase one user's activity explicitly. A compliant activity sink SHALL be required for enablement.

#### Scenario: Successful and failed research
- **WHEN** a user triggers a search that succeeds or fails
- **THEN** an authorized investigator can attribute the request and outcome to that user using the restricted activity store
- **AND** team, session and agent identifiers, duration and result count are available where applicable
- **AND** generic logs, metrics and standard tool audit contain no query text

#### Scenario: Retention expiry
- **WHEN** a record exceeds the configured retention
- **THEN** the activity store deletes it and no search activity view returns it

#### Scenario: Account deletion keeps the security trace
- **WHEN** an administrator deletes or suspends an account
- **THEN** that user's activity stays available to investigators until retention expiry

#### Scenario: Explicit administrator erasure
- **WHEN** an administrator with user administration rights erases one user's activity
- **THEN** every stored record of that user is deleted and no search activity view returns it

### Requirement: Operational visibility

Fred SHALL provide content-free counts, latency, failure and saturation signals for web research through its existing metrics and document alerts for research failures and activity-sink failures. Monitoring SHALL work for local, Docker/Podman, VM and Kubernetes deployments without a dedicated research server or user text in metric labels.

#### Scenario: Admin cost and blocking view
- **WHEN** a platform observer opens analytics for a time range
- **THEN** Fred shows web research volume, estimated provider cost with its formula, blocked, saturated and failed requests by reason, latency and distinct users, without queries, URLs or page content

#### Scenario: DMZ outage
- **WHEN** the configured proxy is unreachable
- **THEN** an operator sees research failure signals and can correlate them with failed tool requests

### Requirement: Configurable search provider

Fred SHALL select the web search provider from deployment configuration among a keyless public provider, an offline fixture provider and a keyed commercial provider, behind the same tools, ceilings, activity records and metrics. Fred MUST NOT fall back from the configured provider to another one. A keyed provider MUST read its key from the secret environment and MUST NOT expose it to model arguments, activity, logs or any other origin.

#### Scenario: Local development without dependencies
- **WHEN** web research is enabled without a provider setting
- **THEN** Fred uses the keyless provider with no key, account or extra service

#### Scenario: Offline tests
- **WHEN** the fixture provider is configured
- **THEN** searches return the configured results without any network access

#### Scenario: Production provider without key
- **WHEN** a keyed provider is configured and its secret is missing
- **THEN** Fred Agents refuses to start with a configuration error

#### Scenario: Provider outage
- **WHEN** the configured provider fails or rejects a request
- **THEN** the tool returns `provider_failed` and no other provider is called

### Requirement: Optional daily quotas per user

Fred SHALL let a deployment cap, per user and per UTC calendar day, the number of searches and the number of page reads independently. Each cap SHALL be optional and absent by default. A request over its cap MUST be refused before any network access with `quota_exceeded`, recorded as a failed activity that does not consume quota.

#### Scenario: Search quota reached
- **WHEN** a user has already made the configured number of searches today (UTC)
- **THEN** the next search returns `quota_exceeded` without contacting the provider, and page reads remain available

#### Scenario: Remaining quota shown
- **WHEN** a capped operation succeeds
- **THEN** its result carries the cap and the remaining count for today, shown in the trace detail

#### Scenario: No quota configured
- **WHEN** neither cap is set
- **THEN** no request is ever refused for quota and results carry no quota

#### Scenario: New day
- **WHEN** UTC midnight passes
- **THEN** the user's counts start again from zero
