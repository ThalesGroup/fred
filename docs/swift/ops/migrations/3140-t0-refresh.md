---
schema: 1
title: "Explicit T0 refresh with durable removal history"
impact: minor
configuration: none
configuration_reason: "Admission remains controlled in SQL administration; no YAML, Helm, environment, permission or secret changes are introduced."
---

## Applicability

Authenticated deployments using platform admission administration. Normal admission and the initial import retain their behavior; administrators can explicitly refresh completed T0 imports while filtering is off.

## Prerequisites

Use the shared PostgreSQL authority and the normal control-plane migration credentials. Schedule the schema upgrade before deploying new admission readers or writers.

## Configuration

No configuration changes. The existing administrator permission controls both refresh modes. No import runs at startup, on upgrade or on activation.

## Upgrade

1. Run the normal control-plane `make db-upgrade`. Revision `d4e8b2a6f091` creates `platform_access_removals` and adds `platform_access_settings.t0_removal_history_complete`.
2. Upgrade participating services and the frontend. New readers require the migrated settings column; control-plane administration requires the history table.
3. Optional feature use: while filtering is off, open Users and select the small refresh icon beside T0 completion. With reliable history, choose preservation or inclusion and confirm.

A completed import from an older version has no reliable removal history. Its next refresh requires inclusion and explicitly warns that the entire T0 whitelist is recalculated and manually removed people can regain access. Confirming that full import establishes the new baseline and enables preservation for future refreshes. Existing grants and provenance are retained. No historical reconstruction is required for legacy test data.

## Validation

After a normal initial import, remove a test exception and introduce a new test identity in the configured directory. Preservation must add the newcomer without restoring the recorded removal. Inclusion must warn before allowing that removed candidate to be re-added. Verify that active filtering disables the icon and the server rejects refresh. In a legacy test environment, verify the missing-history warning and forced inclusion, then the availability of both modes after success. Each committed refresh emits one audit summary with mode and actual additions.

## Rollback

Roll back application code while retaining the additive schema and existing grants. Old code does not record removals. If any revocation occurs under old code, before returning to the new version set `t0_removal_history_complete = false` for settings row `id = 1` using the normal operator database procedure; the next explicit refresh must establish a new baseline. Do not drop history if preserving recorded removals is required. Downgrading the migration drops that protection and cannot undo access granted by a refresh.

## Limitations

Preservation protects recorded individual removals, not suspension or independent rule/team sources. Inclusion adds missing T0 candidates rather than deleting other grants. Directory changes between preview and confirmation can change the final added count. An unavailable directory or stale policy/completion fails without partial additions. Identities not known to the configured directory are not imported.
