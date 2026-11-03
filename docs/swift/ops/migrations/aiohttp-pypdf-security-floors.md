---
schema: 1
title: "Patch aiohttp and pypdf, and publish the Python libraries against PyPI"
impact: none
configuration: none
configuration_reason: "Only dependency versions, Python package versions, locks and the maintainer publication targets change; no deployment setting or default is introduced."
no_action_reason: "The patched aiohttp and pypdf ship inside the rebuilt images through their locks, so a normal deployment applies them."
---

## Applicability

Fred deployments upgrading from v3.9.1, and projects installing fred-core, fred-sdk or fred-runtime from PyPI. fred-core now requires `aiohttp>=3.14.5`, so those projects can no longer resolve a vulnerable aiohttp; knowledge-flow-backend moves to aiohttp 3.14.5 and pypdf 6.21.2.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required. Projects depending on the Fred libraries pick up the aiohttp floor by updating to fred-core, fred-sdk and fred-runtime 4.5.8 once published.

## Validation

In the knowledge-flow-backend image, `python -c "import aiohttp, pypdf; print(aiohttp.__version__, pypdf.__version__)"` prints `3.14.5 6.21.2`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Maintainers publishing the Python libraries no longer pass `BASE_TAG` to `make publish-libs-dry-run` or `make publish-libs`; `make prepare-python-release` still takes it.
