## Why

Fred's frontend and manager can currently be deployed independently: the observed Resources crash followed a current frontend talking to the old standalone manager. One Fred deployment must build and run the agreed manager-based composition together.

Tracking: https://github.com/ThalesGroup/fred/issues/3092

## What Changes

- Make manager a normal Fred chart application and image build/publication entry.
- **BREAKING**: the branch's Fred deployment runs manager API/worker, knowledge-flow API/worker and frontend: five application workloads sharing three images. Control-plane API/worker and fred-agents are disabled and are not built by the local Fred command.
- Keep `make k3d-app APP=fred DIR=../fred` as the deployment command, including manager identity, configuration and bootstrap guidance. Retire the standalone manager deployment.
- Migrate the existing standalone Helm release without resetting identities, data, roles or secrets; make reruns converge.
- Preserve the complete UI. Requests for services not reconstructed remain explicit failures; their absence must not prevent frontend startup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-helm-deployment`: one coordinated Fred deployment includes manager and preserves an existing installation during composition changes.

## Impact

Fred chart/defaults/generated schema, local build mapping, image CI catalog, frontend proxy, deployment/reset consumers, manager README, arc42 operations and migration guide. Companion factory work covers its Fred instance values, identity declaration, hooks and guidance; preserve existing local edits and keep the generic engine application-neutral.

The active `deploy-fred-with-helmfile` change establishes the generic mechanism and published-release workflow. This is a separate reconstruction outcome; its old four-image/six-workload assertions do not describe this branch's new composition. Unrelated validation tasks in that change are not closed by this lot. Docker Compose, deletion of Python source, document ingestion and completing missing product APIs are excluded.
