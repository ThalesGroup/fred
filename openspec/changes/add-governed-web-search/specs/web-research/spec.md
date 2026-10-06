## MODIFIED Requirements

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

### Requirement: Operational visibility

Fred SHALL provide content-free counts, latency, failure and saturation signals for web research through its existing metrics and document alerts for research failures and activity-sink failures. Monitoring SHALL work for local, Docker/Podman, VM and Kubernetes deployments without a dedicated research server or user text in metric labels.

#### Scenario: DMZ outage
- **WHEN** the configured proxy is unreachable
- **THEN** an operator sees research failure signals and can correlate them with failed tool requests
