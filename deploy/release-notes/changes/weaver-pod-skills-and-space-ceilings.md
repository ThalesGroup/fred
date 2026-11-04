---
schema: 1
title: "Weaver: pod skills, local offer ceilings and project execution"
impact: minor
configuration: local
configuration_reason: "Pod skills now default to packaged resources; explicit null still disables them. Existing custom paths retain their meaning. No production chart values or deployment secrets are added."
---
## Applicability

Weaver installations adopting pod skills and organization/team/project restrictions.
This is an adaptation of the Swift skill content and loading contracts, not a
migration of Swift's global skill policy or its Python Control Plane endpoints.

## Prerequisites

Back up the Control Plane database and the deployed configuration. Use matching
fred-sdk and fred-runtime packages on every replica of each logical pod. Allow a
maintenance window if replicas cannot be replaced before the new Control Plane.
The supported engines are ReAct and Deep; embedded Ralph and graph agents do not
support skill loading. The skill named `graph` is an instruction resource, not a
graph agent.

## Configuration

Omitted `skills`, `skills: {}` and `skills: {directory: package}` use the seven
packaged skills. `skills: null` opts out. Existing relative and absolute custom
paths remain supported; an empty directory string is invalid. A missing directory
is reported as unavailable, not as a successful empty catalog.

Files and instructions belong to the pod. An organization only authorizes its
pod offers, exactly like capabilities. Team and project owners may further
restrict those offers. No local decision can exceed its parent ceiling. These
same local restrictions apply to tools as well as skills. Missing local policy
inherits; an explicit empty restriction denies every offer from that pod. Reset
retains a revision so stale editors cannot overwrite a newer decision.

## Upgrade

1. Apply normal Control Plane migrations, including additive migration 0005,
   through the deployment migration procedure. Do not alter 0001–0004 or create
   migration records manually. No production database was migrated by this work.
2. Replace every runtime replica with the matching SDK/runtime before switching
   the Control Plane to the new contract. A new runtime receiving no skill
   decision from an old resolver denies all new skill loads. Old runtime packages
   may reject the new resolver fields; mixed replicas are not a supported rollout.
3. Deploy the Control Plane and generated frontend together. Refresh each pod's
   inventory from the organization capabilities screen. Confirm skill support and
   source availability, then explicitly authorize the intended skill offers.
   Existing tool authorizations are preserved; new skills are denied initially.
4. Team/project owners can then set local restrictions. These settings grant no
   role, content Read, or permission to administer a child space. Project agent
   creation and chat require their usual direct local roles and organization
   agent authorization. Local prompts remain limited to teams/personal spaces.

## Validation

Check organization refusal, inherited ceiling, explicit empty team restriction,
project refusal, reset and competing edits (409). Verify that a manager without
Read can govern their own space but cannot chat, and cannot govern a child.

On each replica, check `graph`, `meeting-minutes` and `grill-me` in the authorized
composer. `analyze-data`, `compare-options`, `grounded-research` and
`summarize-document` are model-only for new loading. References load only within
the admitted snapshot. Preview and preparation must not call a model or allocate
a title job. A changed source revision refuses the request until the inventory
and serving replicas agree. Inspect actual partial/full load traces, rehydrate
history, and revoke a skill before a new turn and a HITL resume.

The repository report records offline test and quality results. No k3d product
journey was run for this change; the above deployment checks remain operator work.

## Rollback

Prefer a corrective forward release. Before reverting to a version that does not
enforce local ceilings, stop affected traffic and disable the relevant pod
sources or withdraw organization authorizations; otherwise older code could
ignore local restrictions. Restore a mutually compatible Control Plane, SDK,
runtimes and frontend using the normal release procedure. The additive tables
retain decisions; do not delete migration history to force old code to start.
If the chosen old release requires a database restore, coordinate it with the
application rollback using the pre-upgrade backup.

## Limitations

There is no organization-owned skill content, editor, marketplace, or replacement
runtime loader. Changes to source files require a pod restart and inventory
refresh; ReAct and Deep read the same bounded immutable startup snapshot.

`mermaid`, `data-visualization` and `verify-answer` have no packaged aliases.
Historical messages stay readable. An unavailable or newly model-only selection
is refused without silently converting the draft to ordinary text. Custom skills
keep their own names and descriptions and obey the same ceilings. Builtin labels
are translated only when backed by pod provenance.

An admitted turn may finish. Revocation affects the next admission, including
resume; instructions already in conversation/checkpoint history are not erased.
The existing title admission, resume and late-event identity contracts are retained.
