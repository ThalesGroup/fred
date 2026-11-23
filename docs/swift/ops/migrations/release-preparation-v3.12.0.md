---
schema: 1
title: "Prepare Fred v3.12.0 and review dependency updates"
impact: none
configuration: none
configuration_reason: "Release preparation updates publication inputs. The covered Dependabot contributions modify only Python lockfiles."
no_action_reason: "The OpenTelemetry, Soup Sieve and dnspython lockfile updates ship with the rebuilt images. They introduce no extra configuration or data migration. Follow the other notes for feature activation."
covers:
  - d4605cefb7478a8ef706eb2dc50832262583da62
  - cf698a739afae1b4cbcd92e82439e32bc1038198
---
## Applicability

Existing Fred deployments upgrading to v3.12.0.

## Prerequisites

Use the normal deployment prerequisites.

## Configuration

The covered OpenTelemetry patch update and matching semantic conventions,
Soup Sieve selection in supported Python resolutions, and dnspython patch
update do not change Fred configuration.

## Upgrade

Deploy the rebuilt images with the normal deployment procedure. Follow the
reranking and model key notes for optional activation.

## Validation

Check that the affected projects install from their committed locks. Smoke-test
chat, Knowledge Flow ingestion and search, and check that expected telemetry is
still emitted in the deployment.

## Rollback

Restore the previous release images to restore the previous dependency set.

## Limitations

Python package publication is a separate action from the code and chart tags.
