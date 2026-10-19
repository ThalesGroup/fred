## Why

The developer needs one ordinary factory checkout on swift and the usual Fred deployment command. The factory-specific manager integration was withdrawn in favor of preserving the control-plane deployment contract.

Tracking: https://github.com/ThalesGroup/fred/issues/3092

## What Changes

- Build the Rust manager as the control-plane-backend image and run it as control-plane-backend/control-plane-worker in Fred's chart.
- Keep five application workloads and three images: Rust API/worker, Knowledge Flow API/worker, frontend. Disable Python control-plane and fred-agents execution.
- Consume unchanged factory swift instance values, identities and secrets. Keep UI calls and layout unchanged through gateway routing.
- Preserve manager database, OpenFGA store, bootstrap, consent and lifecycle queue identities when upgrading the existing fred-app release.

## Capabilities

### Modified Capabilities

- `local-helm-deployment`: Fred owns implementation selection behind the stable control-plane deployment contract.

## Impact

Fred chart/schema, Rust SQL migration entry point, image build/publication, frontend gateway, reset inventory and architecture/operations documentation. No factory edits or cluster mutation by the assistant. API reconstruction and document ingestion are excluded. The developer confirmed this revision on 2026-10-19.
