---
schema: 1
title: "Build the Python production images on Ubuntu 24.04 LTS"
impact: none
configuration: none
configuration_reason: "Only the base of the fred-agents, control-plane and Knowledge Flow images changes; environment variables, chart values and application configuration remain compatible."
no_action_reason: "The images keep the same runtime user (UID/GID 1000), entrypoints, ports, paths and converters, so normal deployment applies them with no data migration or special restart order."
---
## Applicability

Existing Fred deployments upgrading to this release. Operators who build their own images on top of a Fred Python image must also read Limitations.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The fred-agents, control-plane-backend and knowledge-flow-backend images, including the `-pymupdf` variant, now build on Ubuntu 24.04 LTS instead of Debian 13. Python remains 3.12.15, installed from uv's standalone CPython builds. LibreOffice moves from 25.2 to Ubuntu's maintained 24.2 series.

## Validation

Run an agent turn and generate a PPT preview. Check that the control-plane starts and its migrations complete. In Knowledge Flow, ingest a PDF, a legacy Office document and a spreadsheet with formulas. Scan the deployed image digests: the Debian findings without a fixed version, including the libxml2 CVE-2026-6653 critical finding, no longer appear.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. An older image brings back the Debian findings.

## Limitations

- Images derived from Fred's Python images now inherit Ubuntu 24.04. Their `apt-get` package names may differ from Debian 13: for example, `libmagic1` is `libmagic1t64`. The base no longer has a `ubuntu` user.
- The standalone CPython build bundles OpenSSL, SQLite and expat. Image scanners do not report them; their fixes arrive with a Python or uv update in Fred, not through apt.
- `pandoc`, `inkscape` and `ffmpeg` come from Ubuntu's universe component, whose security maintenance is community-provided.
