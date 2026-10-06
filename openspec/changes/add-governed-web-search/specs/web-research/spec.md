## ADDED Requirements

### Requirement: Governed web research tools

Fred SHALL expose bounded `web_search`, `fetch_url`, and `search_and_fetch` tools only to agents for which the web research capability is enabled and authorized. Search SHALL support result count, SafeSearch, region and freshness; fetch SHALL return bounded main text and source metadata, with optional focus. The same behavior SHALL work across supported agent execution models.

#### Scenario: Authorized search
- **WHEN** an authorized agent invokes `web_search` with a query and valid filters
- **THEN** Fred returns bounded titles, public URLs and snippets with source attribution
- **AND** the call is recorded with its user and outcome

#### Scenario: Disabled or unauthorized capability
- **WHEN** the capability is disabled or the current user loses permission
- **THEN** Fred does not dispatch an outbound request

### Requirement: Controlled external egress

Every outbound web research request SHALL use the configured authenticated HTTPS egress endpoint. The egress service MUST reject non-HTTP(S), private/non-global addresses, unsafe redirects, excessive responses and non-textual content. It MUST verify the destination actually connected to after DNS resolution and MUST NOT forward caller secrets to another origin.

#### Scenario: Split-VM deployment
- **WHEN** Fred runs on an application VM and the egress service runs on a DMZ VM
- **THEN** the same HTTPS operation contract and service authentication apply as in container and Kubernetes deployments

#### Scenario: Redirect to an internal address
- **WHEN** a public page redirects to an internal or non-global destination
- **THEN** the egress service refuses the fetch before connecting to that destination

#### Scenario: Egress unavailable
- **WHEN** the endpoint times out or rejects the request
- **THEN** the tool returns a bounded failure without exposing transport credentials or raw exception text

### Requirement: Attributed, retained search activity

Fred SHALL create one restricted activity record per logical web research tool request, with opaque user and correlation identifiers, operation, request query or public URL, time, outcome, duration and result count where applicable. It SHALL NOT store fetched page content, snippets, credentials or headers in that record. The sink SHALL purge records after a configurable retention period defaulting to 30 days and SHALL participate in user erasure. Fred SHALL not enable web research without a configured compliant sink.

#### Scenario: Successful and failed research
- **WHEN** a user triggers a search that succeeds or fails
- **THEN** an authorized investigator can attribute the request and outcome to that user using the restricted activity store
- **AND** generic logs, metrics and standard tool audit contain no query text

#### Scenario: Retention expiry and user erasure
- **WHEN** a record exceeds the configured retention or its user is erased
- **THEN** the activity store deletes it and no search activity view returns it

### Requirement: Operational visibility

Fred SHALL provide content-free counts, latency and failure metrics for web research, endpoint health checks, and documented alerts for egress unavailability, error rates, saturation and activity-sink failures. The monitoring path SHALL work for local, Docker/Podman, VM and Kubernetes deployments without adding user text as a metric label.

#### Scenario: DMZ outage
- **WHEN** the egress endpoint is unreachable
- **THEN** an operator sees a health or failure signal and can correlate it with failed tool requests
