---
schema: 1
title: "Coordinated v3.5.0 upgrade and rollback"
impact: minor
configuration: none
configuration_reason: "Release preparation consolidates existing migration procedures and adds no configuration setting; the minor impact comes from those existing changes."
---
## Applicability

Upgrade from Fred v3.4.0 to v3.5.0 with paired code and chart releases. This
sequence combines the procedures below; it adds no migration of its own.

## Prerequisites

Back up the shared PostgreSQL database and keep the previous images, chart,
values, model catalog and OpenFGA model identifier. Rehearse the complete
upgrade and rollback with the deployment's overlays and custom agent pods.
If `global.whitelist` or `users.txt` restricts access, configure equivalent
Platform access rules or exceptions, preview them and enable filtering before
removing the file whitelist. Preserve a verified administrator recovery path.

## Configuration

Remove `global.whitelist` from Fred chart values and any separate `users.txt`
mount. No other setting must change for an ordinary upgrade. The production
reference is the Fred chart values; `configuration_prod.yaml` is for local
Docker Compose only. Custom agent pods need the SDK and runtime of this release.
If `fred-agent-evaluator` is deployed, use a version that forwards the selected
chat model as described in the model-picker section before relying on overrides.

## Upgrade

### Required coordinated rollout

1. Quiesce affected writers, take the verified database backup and preserve the
   previous deployment inputs. Keep the equivalent Platform access policy on
   throughout rollout where it replaces a file whitelist.
2. Run the control-plane Alembic chain once, before updated control-plane or
   Knowledge Flow readers start. From the v3.4.0 head `93427a5fe874`, the chain
   is `9f6d3c2a1b08` -> `e5ff6d80cc9f` -> `a6c1d94e27b3` -> `e9026d8e4db6`
   -> `24c2f88374fe`. Use the deployment's migration job or equivalent command;
   the chart's migration hooks are disabled by default. Run the normal runtime
   and Knowledge Flow migration checks as part of the deployment; this release
   adds no revisions in those trees.
3. Deploy the matching Fred chart and updated control plane. Confirm its
   OpenFGA model is written and selected with the marketplace permissions, and
   confirm the Platform access policy still admits the intended users.
4. Deploy updated Knowledge Flow services and all agent runtime pods, including
   third-party pods rebuilt on this release's SDK/runtime. Upgrade runtime pods
   before the frontend so messages with several prompt commands retain their
   full display after reload. Upgrade the evaluator as noted above if used.
5. Deploy the frontend and verify the control-plane, runtime and frontend
   together. Resume traffic only after the validation below passes.

### Optional activation and user data

- Marketplace publication stays off by default. After all pods are updated,
  platform administrators may enable it for eligible teams and set quotas.
- To use GPT-6 Astra through Azure APIM, add an authorized Responses API model
  profile to the deployment model catalog and restart affected pods if needed.
- To use custom theme CSS, labels or extra selectable themes, upload the new
  theme ZIP only after the frontend is upgraded, then restart frontend pods.
- No document re-ingestion is required for the upgrade. A user may upload an
  earlier failed Windows-1252 or BOM-prefixed text file again to benefit from
  the decoding fix; existing successful documents remain unchanged.

## Validation

Confirm the control-plane head is `24c2f88374fe`, the OpenFGA model is selected,
and access restrictions remain effective. Check sign-in, team invitation join
history, chat model choice and reasoning, multiple prompt commands after reload,
the patch-note history and a basic agent-marketplace browse. If publication is
enabled, test publishing and importing an agent with configuration files.
Validate custom pods and the evaluator where deployed. Exercise any activated
Astra profile or theme ZIP separately.

## Rollback

Stop new traffic and affected workers before changing images or schemas.
Disable optional marketplace publication and Astra selection, and restore the
previous theme ZIP if used. A code-only rollback is suitable only when the old
images were rehearsed against the current schema and data. Otherwise, use a
coordinated restore from the pre-upgrade backup. Any in-place downgrade must
be reviewed across the full chain and run with the new migration image while
readers and writers remain stopped. It can discard marketplace entries,
model settings, patch-note exposure and seen history, and Free-link join history;
the old per-template model overrides and earlier dismissal choices are not
reconstructed. Restore the previous OpenFGA model and file-whitelist settings
only with old application readers, and verify access before reopening traffic.

## Limitations

The chart does not order application Deployments, so enforce the staged rollout
in the deployment procedure. The release guide does not validate private
overlays, third-party pod builds, evaluator compatibility or production APIM
permissions. Patch-note history before this upgrade lacks historical content;
previously failed text uploads are not repaired automatically.
