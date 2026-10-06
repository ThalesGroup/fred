---
schema: 1
title: "Enable shared platform skills for managed ReAct and Deep agents"
impact: minor
configuration: production
configuration_reason: "Optional skills.directory selects packaged resources or a read-only project directory; chart defaults remain disabled."
---
## Applicability

Fred deployments upgrading the runtime, control plane and frontend together.
Normal upgrades retain existing behavior when skills configuration is absent.
The `/skill` composer command is reserved on every deployment.

## Prerequisites

Use matching runtime/SDK/control-plane/frontend versions. For a project directory,
provide UTF-8 SKILL.md procedures with name/description YAML metadata and bounded
text references. Every replica must receive the same resources.

## Configuration

Optional activation: set `applications.fred-agents.configuration.skills.directory: package`
in chart values to use the `compte-rendu` example shipped inside fred-runtime.
For custom skills, mount a trusted directory read-only and use its absolute pod
path. Relative paths resolve against the configuration file parent. Omit skills
(or leave chart `skills: null`) to disable. No IAM grants or secrets are added.
Application development configuration examples explicitly enable `package`.

## Upgrade

Deploy the control plane, runtime and frontend with the normal procedure. Older
runtime catalog routes are shown as unsupported during a rolling upgrade.
To activate or change resources, drain active turns and restart all relevant
agent pod replicas. Avoid mixed snapshots: use identical config/resources on
all replicas before resuming traffic. Invalid entries are omitted with diagnostic
folder names. Existing checkpoints retain loaded procedure messages; catalog
metadata refreshes on their next turn, without resetting conversations.

Existing prompts using command `skill` remain library-readable and editable but
lose that slash shortcut. Rename the command to restore it; new assignments,
imports and promotions with `skill` return a reserved-command conflict.

## Validation

Select a managed ReAct or Deep instance. Verify its `/skill` menu lists only its
runtime catalog. Send `/skill compte-rendu` plus notes containing a decision and
an action without a deadline: a user-origin load step precedes the response,
and absent fields are marked `Non précisé`. On an ordinary relevant request the
model can load the same skill automatically. Reopen the chat and check the
compact origin step remains. Verify unknown selection fails before inference
and unavailable tools are explained without fabricated results.

## Rollback

Disable `skills`, then drain/restart the pods to remove the catalog and loading
tools. Use normal application rollback for a full revert; no database migration
is introduced. Disabling does not erase already-loaded checkpoint context or
stored history. Start a fresh conversation if older instructions must be excluded.

## Limitations

V1 supports a few dozen shared procedures and confined text references. Resources
refresh only at restart; skills do not install tools, execute scripts, or grant
permissions. Selection/following by the model is probabilistic. Graph agents and
a dedicated terminal CLI are outside this feature.
