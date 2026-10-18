## Why

The published Python images report 67 HIGH and 1 CRITICAL Debian findings (fred-agents v3.7.0), none with a fixed version listed. A comparison under the same scanner and database shows that base + LibreOffice on Ubuntu 24.04 LTS reports no HIGH or CRITICAL finding. The difference comes from Debian's no-dsa backlog, NVD-derived severities and a Debian-specific libxml2 backport, not from Fred's code. Tracking: #3167, follow-up to #3161.

## What Changes

- Rebase the builder and final stages of the fred-agents, control-plane-backend and knowledge-flow-backend production Dockerfiles from `python:3.12.15-slim-trixie` to `ubuntu:24.04`.
- Pin CPython 3.12.15 through uv's standalone builds (uv 0.13.1), so the interpreter version does not follow the distribution.
- Keep the runtime user (`fred-user`, UID/GID 1000), entrypoints, installed converters and venv layout unchanged.

## Capabilities

No product capability or public contract changes are intended. This security maintenance change skips delta specs because application behavior should be preserved.

## Impact

- The three production Python Dockerfiles and the Knowledge Flow `-pymupdf` variant built from the same file.
- Images derived from Fred's images now inherit Ubuntu 24.04 instead of Debian 13.
- No API, database, frontend, chart or configuration contract change.
