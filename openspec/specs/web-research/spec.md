# Web Research Specification

## Purpose

Provide native, governed web research for Fred agents through internal direct or proxy access, with restricted activity retention and content-free monitoring.

## Requirements

### Requirement: Governed web research tools

Fred SHALL expose bounded `web_search`, `fetch_url`, and `search_and_fetch` tools only to agents for which the web research capability is enabled and authorized. Search SHALL support result count, SafeSearch, region and freshness; fetch SHALL return bounded main text and source metadata, with optional focus. The same behavior SHALL work across supported agent execution models.

#### Scenario: Authorized search
- **WHEN** an authorized agent invokes `web_search` with a query and valid filters
- **THEN** Fred returns bounded titles, public URLs and snippets with source attribution
- **AND** the call is recorded with its user and outcome

#### Scenario: Deployment context ceilings
- **WHEN** a tool call requests more results or page text than the deployment `max_results` or `max_chars_per_page` allows
- **THEN** Fred returns at most those ceilings to the model and cites only the returned pages

#### Scenario: Disabled or unauthorized capability
- **WHEN** the capability is disabled or the current user loses permission
- **THEN** Fred does not dispatch an outbound request

### Requirement: Controlled external egress

Fred SHALL execute research internally, directly or through an explicitly configured HTTP(S) forward proxy, with no proxy-to-direct fallback. It MUST reject unsafe URLs, redirects and excessive/non-text responses. Direct connections MUST pin public DNS results. Proxy deployments MUST enforce public-only final destinations at the proxy. Origin TLS MUST remain verified and proxy credentials MUST NOT reach origins.

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

### Requirement: Attributed, retained search activity

Fred SHALL record each dispatched research request with opaque subject/correlation IDs, query or public URL, timing and outcome. Records SHALL exclude page bodies, snippets and credentials. Access SHALL be restricted to platform operators, expire after a configurable 30-day default, and support user erasure. A compliant activity sink SHALL be required for enablement.

#### Scenario: Successful and failed research
- **WHEN** a user triggers a search that succeeds or fails
- **THEN** an authorized investigator can attribute the request and outcome to that user using the restricted activity store
- **AND** team, session and agent identifiers, duration and result count are available where applicable
- **AND** generic logs, metrics and standard tool audit contain no query text

#### Scenario: Retention expiry and user erasure
- **WHEN** a record exceeds the configured retention or its user is erased
- **THEN** the activity store deletes it and no search activity view returns it


#### Scenario: Late request after user erasure
- **WHEN** an already authorized request tries to start recording after its user was erased on another replica
- **THEN** a shared durable erasure fence refuses the insertion and no query record is recreated

### Requirement: Operational visibility

Fred SHALL provide content-free counts, latency, failure and saturation signals for web research through its existing metrics and document alerts for research failures and activity-sink failures. Monitoring SHALL work for local, Docker/Podman, VM and Kubernetes deployments without a dedicated research server or user text in metric labels.

#### Scenario: DMZ outage
- **WHEN** the configured proxy is unreachable
- **THEN** an operator sees research failure signals and can correlate them with failed tool requests
