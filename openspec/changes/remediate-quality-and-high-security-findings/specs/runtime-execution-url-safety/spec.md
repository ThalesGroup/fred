## Purpose

Keep browser-facing runtime execution endpoints on the application origin so bearer-authenticated calls cannot be redirected through configuration or an untrusted preparation response.

## ADDED Requirements

### Requirement: Runtime ingress prefixes are safe browser paths

The control plane SHALL accept runtime ingress prefixes only as canonical root-relative paths on the current origin. It SHALL reject absolute URLs, network-path references, path traversal, encoded separators, query strings, and fragments before publishing execution endpoints.

#### Scenario: Valid configured prefix

- **WHEN** a runtime source has a canonical prefix such as `/runtime/agents-v2`
- **THEN** execution preparation returns endpoints under that prefix

#### Scenario: External or ambiguous prefix

- **WHEN** a runtime source is configured with an external origin or an ambiguous path
- **THEN** configuration validation rejects the source with a clear error before it can be used for execution

### Requirement: Bearer-authenticated execution stays on the application origin

The frontend SHALL validate each preparation endpoint immediately before issuing a bearer-authenticated runtime request. It SHALL reject endpoints whose resolved origin differs from the application origin or whose path is not an accepted runtime execution path.

#### Scenario: Same-origin execution

- **WHEN** preparation returns a valid same-origin runtime execution path
- **THEN** the frontend sends the request with the existing bearer authorization and streaming behavior

#### Scenario: Tampered preparation response

- **WHEN** preparation returns an external, network-path, or malformed execution endpoint
- **THEN** the frontend fails the execution without sending its bearer token to that endpoint
