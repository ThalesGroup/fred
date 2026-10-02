## Why

The first pull request Trivy scan reports 29 critical vulnerability findings in three production Python images. Their runtime environments include development tools, and Knowledge Flow uses an older Debian-based Python image, so avoidable packages and stale OS versions reach production.

## What Changes

- Install only runtime Python dependencies into the three production images while preserving editable first-party packages and runtime tools.
- Refresh the production OS packages and align Knowledge Flow with the maintained Python 3.12 image family already used by the other backends.
- Rebuild and rescan the images, compare critical findings to the 29-finding baseline, and explain any residual findings without suppressing them.

## Capabilities

No product capability or public contract changes are intended. This security maintenance change skips delta specs because application behavior should be preserved.

## Impact

- Shared Python dependency installation recipe and the three production Python Dockerfiles.
- Package composition of released images, build time, and deployment rollback guidance.
- No API, database, frontend behavior, or configuration contract change.
