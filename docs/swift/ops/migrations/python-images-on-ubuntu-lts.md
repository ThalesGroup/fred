---
schema: 1
title: "Build the Python production images on Ubuntu 24.04 LTS"
impact: none
configuration: none
configuration_reason: "Only the base of the fred-agents, control-plane and Knowledge Flow images changes; environment variables, chart values and application configuration remain compatible."
no_action_reason: "The images keep the same runtime user (UID/GID 1000), entrypoints, ports, paths and converters, so normal deployment applies them with no data migration or special restart order. Only custom images built FROM a Fred Python image need attention: they now inherit Ubuntu 24.04 instead of Debian 13, so their apt package names must be checked (for example, libmagic1 is now libmagic1t64) before rebuilding them."
---
## Applicability

Existing Fred deployments upgrading to this release, including operators who build their own images on top of a Fred Python image.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The fred-agents, control-plane-backend and knowledge-flow-backend images, including the `-pymupdf` variant, now build on Ubuntu 24.04 LTS instead of Debian 13. Python remains 3.12.15, installed from uv's standalone CPython builds. LibreOffice moves from 25.2 to Ubuntu's maintained 24.2 series.

If you build a custom image `FROM` one of these Fred images, check it before rebuilding:

1. Replace Debian 13 package names in its `apt-get install` lines with their Ubuntu 24.04 equivalents (for example, `libmagic1` is now `libmagic1t64`).
2. Do not rely on Debian-specific paths or on a preinstalled `ubuntu` user; the runtime user remains `fred-user` (UID/GID 1000).
3. Rebuild the image and run its own validation before deploying it.

## Validation

Run an agent turn and generate a PPT preview. Check that the control-plane starts and its migrations complete. In Knowledge Flow, ingest a PDF, a legacy Office document and a spreadsheet with formulas. Scan the deployed image digests: the Debian findings without a fixed version, including the libxml2 CVE-2026-6653 critical finding, no longer appear.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. An older image brings back the Debian findings.

## Limitations

- The standalone CPython build bundles OpenSSL, SQLite and expat. Image scanners do not report them; their fixes arrive with a Python or uv update in Fred, not through apt.
- `pandoc`, `inkscape` and `ffmpeg` come from Ubuntu's universe component, whose security maintenance is community-provided.
