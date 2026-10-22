# Verification

## Backend (2026-10-22)

- **fred-sdk:** `make code-quality` clean; `make test` 663 passed. New tests in `tests/test_capability_model_port.py`: an authorizer without the manager check refuses it (403); `capability_platform_model` fails closed (503) unbound and returns the bound port.
- **fred-runtime:** `make code-quality` clean (5 pre-existing unreachable-code warnings); `make test` 2240 passed. New tests in `tests/test_capability_platform_ports.py`: the manager check asks `CAN_MANAGE_CAPABILITIES` on the organisation, 403 when denied, open with security off, identity-only without ReBAC, 403 without a user; the teamless port has no team, resolves the pod default and an explicit vision profile; the route binder binds it.
- **ppt_builder capability:** `make code-quality` clean; `make test` 956 passed, 5 skipped (reference templates not provided). New `tests/test_platform_template.py` (14 tests): Fred template until replaced; every write refused for a non-manager with the row unchanged; a manager upload is analysed with the teamless port and the platform's default model; an unreadable (400) or oversized (413) upload keeps the current default; a re-run takes the vision choice, keeps the file name and leaves agent rows untouched; re-run without a template is 404; reset deletes the row; `/analysis/__platform__` is 404; pending and failed platform analyses leave agents on the Fred template and ready; a succeeded one serves agents without their own, with no store read on the next turn; the agent template wins; an expired snapshot serves while one read replaces it; a write drops a read started before it; stored pattern edits never reach the default template. `test_no_template_drops_every_pattern_edit` replaces the built-in pruning test (D7).
- **Migration:** single head `r9d3f4a5b6c7`; on a throwaway SQLite file, `upgrade head`, `alembic check` (no drift), downgrade to `q8c2e3b4d5f6`, upgrade, downgrade to base all pass. The PostgreSQL check (`make db-check-postgres-full`) needs Docker and was not run.
- **Control plane:** `make code-quality` clean; `make test` 2042 passed. New test: `CapabilityEnablementItem` carries `route_base_url` and a model row's `vision_profile_ids`.
- **Generated clients:** `controlPlaneOpenApi.ts` (+4 lines) and `pptBuilderCapabilityOpenApi.ts` regenerated; `npx tsc --noEmit` passes.
- **Performance review (per-turn path):** a turn of an agent without its own template reads only the pod-local snapshot (no I/O); once expired, the expired value serves and one background read (single flight, shielded) replaces it; only a pod's first turn awaits one primary-key read. The inventory and template bytes come from the existing LRUs. No new metric or log on the hot path; a failed read logs a warning and keeps the last value for 30 s. The upload's readability check runs off-loop in a heavy-job slot.

## Not yet verified

- Frontend tasks 5.2–5.5, Help Center 6.1, browser check 6.4.
