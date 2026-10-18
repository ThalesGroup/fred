---
schema: 1
title: "Refresh runtime images and shared dependency security floors"
impact: none
configuration: none
configuration_reason: "Only runtime image dependencies change; environment variables, chart values and application configuration remain compatible."
no_action_reason: "The refreshed Fred images take effect through normal deployment, with no data migration or special restart order."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The frontend image uses nginx 1.31.7 and refreshed Alpine
packages. All Python production images use Python 3.12.15 on Debian stable.
The agent image uses headless Impress for PPT previews; Knowledge Flow retains
headless Writer, Calc and Impress for document conversion and recalculation.
Installed build-only pip copies and their vendored dependencies are removed.
Knowledge Flow drops the unused LangChain agent runtime and refreshes Docling,
MCP, Mako, multidict and uv.

Shared fred-core and fred-sdk dependencies require the Temporal Python SDK (`temporalio`)
1.30 or newer within major version 1. This is not a Temporal server upgrade
requirement. Their consumers must refresh their locks when adopting the new
packages; the repository locks use 1.30.0. The fred-core MCP extra and runtime
require patched MCP v1; fred-core requires uv 0.12.23 or newer. Temporal now
negotiates gRPC compression with downgrade support; no Fred configuration change
is required.

The corrected core, SDK and runtime packages are version 4.5.3. Capability
packages take a patch increment and require the corrected shared libraries.
Capability configuration versions are unchanged.

Rebuilds should pull fresh bases and avoid stale cached package installation
layers when assessing newly published security fixes.

## Validation

Open the frontend, verify configured application proxy routes, and confirm any
deployment theme still loads. Run an agent turn and generate a PPT preview.
Verify control-plane lifecycle workers and Knowledge Base synchronization. In
Knowledge Flow, ingest a PDF and Office document, preview a presentation, and
check spreadsheet formula recalculation.
Scan the deployed image digests to verify their runtime packages; assess npm
dependencies separately from the nginx image.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
An older image can reintroduce the vulnerabilities corrected by this update.

## Limitations

Scan results reflect the vulnerability database at scan time. This runtime update
does not change npm dependencies or remove their separately reported findings.
Debian packages without published stable fixes, ChromaDB findings and Temporal's
remaining embedded rustls finding stay visible. Package-level findings do not by
themselves establish exploitability in Fred. The dormant ensurepip bundled wheel
is still part of the Python base; installed pip is absent from the final images.
