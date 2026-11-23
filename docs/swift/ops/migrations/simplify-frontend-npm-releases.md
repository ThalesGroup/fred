---
schema: 1
title: "Simplify frontend npm releases with shared Make commands"
impact: none
configuration: none
configuration_reason: "The change replaces repository release tooling and its GitHub adapter; deployed Fred services, charts, and runtime configuration are unchanged."
no_action_reason: "Existing deployments and already published npm versions remain unchanged; release maintainers use the new commands only for future frontend package releases."
---

## Applicability

Fred deployments and maintainers of `@fred-oss/design-tokens`, `@fred-oss/ui`, and `@fred-oss/iframe-sdk`.

## Prerequisites

No additional prerequisite applies to a Fred deployment. Before a future npm publication, release maintainers review the local and CI prerequisites in `libs/frontend/RELEASE.md`.

## Configuration

No deployment configuration changes are required. Existing npm Trusted Publisher and GitHub `npm-publish` environment settings remain external release prerequisites.

## Upgrade

Deploy Fred normally. For future frontend npm releases, use the shared `prepare-release`, `publish`, `verify-release`, and `promote` Make targets instead of retained attempt/recovery inputs. If `swift` advances after preparation, publish the unchanged older directory through explicit local or token authentication; GitHub OIDC publication intentionally requires the workflow source commit to match the prepared commit.

## Validation

From `libs/frontend`, run `make help` and confirm the four release targets are listed. Run a publication dry run against a prepared test directory; it must perform no npm publication or distribution-tag mutation.

## Rollback

Use the normal code rollback procedure. This tooling change does not alter deployed data or existing npm package bytes.

## Limitations

Preparation intentionally requires a clean committed checkout so its recorded source commit is truthful. Real npm publication, promotion, GitHub environment approval, and npm account configuration are not exercised by repository tests.
