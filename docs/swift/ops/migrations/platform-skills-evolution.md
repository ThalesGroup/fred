---
schema: 1
title: "Enable packaged skills and add global skill policy"
impact: minor
configuration: production
configuration_reason: "Absent skills configuration now enables the packaged catalog; Helm defaults preserve absence, explicit null and custom directories. Global policy requires a control-plane migration and coordinated runtime rollout."
---
## Applicability

Deployments upgrading agent runtimes, control plane and frontend for platform skills.

## Prerequisites

Back up the control-plane database. Review whether each agent pod should use the
packaged catalog, an existing custom directory or explicit `skills: null`.

## Configuration

An absent `skills` key or `{}` now uses `directory: package`. Use `skills: null`
to preserve an intentionally disabled installation. Existing custom paths keep
their meaning. Charts omit the optional key by default and retain explicit null.
Packaged resources remain English; the frontend translates their titles and
descriptions using trusted packaged provenance. No translation files are needed
for custom skills.

The packaged diagram skill is now named `graph` (`/graph`), displayed as
Graphiques in French and Graphs in English. Mermaid remains its rendering
format. The former packaged `mermaid` name is no longer advertised; stored
messages keep their original text and selections. Existing retired-skill
handling applies to old names. If an installation tested this branch with a
disabled `mermaid` policy, review the retired entry and disable `graph` after
the runtime rollout if that opt-out is still intended. Custom skill names are
unchanged.

## Upgrade

1. Apply the linear control-plane migration `d7b24ef08361` after `f28c3e9ab641`.
   It creates a small global policy table; no existing data is rewritten.
2. Deploy the new control plane before new runtimes, so direct runtime execution
   can read `/platform/skills/policy`. Deploy all configured runtime replicas,
   then the frontend. Do not disable any skill until all runtime replicas have
   completed the rollout.
3. Open Administration > Features > Skills. Check all sources are available and
   policy-capable before setting global opt-outs. Absence of a policy row means
   enabled. Stored opt-outs can be re-enabled even when all sources are offline.

New runtimes request managed bindings with `X-Fred-Skill-Policy: 1` and read the
shared policy for direct template execution. Catalog relays request metadata
version 1; runtimes retain version 0 responses for older control planes.

## Validation

Verify default skills and both locale labels, select `/grill-me`, and check its
load activity. Disable a packaged skill, start another turn in an existing
conversation and on another replica, and verify discovery and new loads reject
it. Re-enable it and verify the next turn can load it again. Custom directories
are outside this global policy.

## Rollback

Re-enable all disabled skills before rolling runtimes back. Older raw-template
runtimes cannot enforce this new policy. An older managed runtime is refused
when disabled names exist. Restore earlier configuration or explicitly set
`skills: null` if needed. The additive table can remain during application
rollback; downgrade it only after new control-plane replicas have stopped, since
downgrade deletes stored opt-outs.

## Limitations

An inventory URL behind a load balancer cannot prove that every replica has
upgraded. The completed runtime rollout is an operator prerequisite. Policy
changes apply to the next turn, including resumes; they do not interrupt an
in-flight turn or erase instructions already in checkpointed context. A configured
control plane that cannot serve fresh policy causes direct execution to fail closed.
