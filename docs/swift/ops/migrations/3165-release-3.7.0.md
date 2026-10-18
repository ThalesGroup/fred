---
schema: 1
title: "Prepare Fred v3.7.0 and account for dependency lock refresh"
impact: none
configuration: none
configuration_reason: "Release notes and validated package coordinates introduce no additional configuration change; the covered dependency refresh changes only existing lockfiles."
no_action_reason: "Release preparation and the covered dependency refresh need no action beyond deployment; follow the separate in-range notes for the database upgrade and optional image choices."
covers: [e6765295d27a24639efd3208e605ad12dc0b2569]
---
## Applicability

Fred v3.7.0 release preparation and the previously uncovered dependency update
from PR #3146, reviewed against its parent commit.

## Prerequisites

Follow the other procedures in this release guide before upgrading services,
particularly the control-plane database migration in `3140-t0-refresh`.

## Configuration

No additional settings, secrets or schema changes. The covered contribution
changes only six existing locks: fred-agents, fred-runtime and the HTML artifact,
platform operations, team wiki and writable document capability packages.

## Upgrade

Deploy the matched v3.7.0 images and chart after the guide's required procedures.
The covered locks update uv to 0.13.1, MCP to 1.30.0, Mako to 1.4.3 and
langgraph-sdk to 0.4.7; fred-agents and fred-runtime also update fsspec to 2026.9.0.
These updates add no Fred settings, stored-data migration or restart ordering.

The shared core, SDK and runtime release coordinates remain 4.5.3 as prepared
by the security update. Capability package patch versions are preserved and
configuration manifest versions are unchanged. This release preparation does
not publish Python packages to PyPI.

## Validation

Verify locked installations and built Python artifacts, then check the matching
code/chart version and attached operator guide. After deployment, run an agent
turn, exercise spreadsheet discovery and check document ingestion using the
selected PDF profile. Full deployment validation remains an operator step;
local processor image checks do not establish persisted ingestion in a cluster.

## Rollback

Restore matched previous images and configuration, observing the separate
admission-history and optional-dependency rollback procedures in this guide.
Release preparation and the covered lock update introduce no data rollback.

## Limitations

Dependency updates do not guarantee a vulnerability-free image. Optional Chroma
and PyMuPDF selections retain their own dependency and licensing implications.
No separate Python package publication or production deployment is performed
by preparing the release.
