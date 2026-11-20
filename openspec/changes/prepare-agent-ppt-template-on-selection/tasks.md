# Tasks

## Temporary preparation

- [x] Extend the existing asset and preparation rows with temporary ownership, author, target and expiry in one migration. Verify PostgreSQL upgrade and downgrade.
- [x] Add authorized, bounded upload, status, retry and discard routes for agent creation and editing. Admit the file and preparation before Save, so the existing dispatcher can start the worker.
- [x] Expire abandoned uploads and reclaim their objects through the existing cleanup path after active worker leases end.

## Agent save and form

- [x] Accept a preparation reference on create and update. Atomically attach the same preparation and assets after checking author, team, target, capability, runtime, rules and settings. Keep the legacy multipart path.
- [x] Upload on file selection and show transfer, preparation, success and failure in the agent form. Preserve an in-flight upload when the same form closes and reopens.
- [x] Keep Save blocked until upload admission, then let Save attach a pending, running or succeeded preparation without starting another analysis. Fence replaced files and changed analysis settings.
- [x] Update English and French UI text, help content and product contract documentation.
- [x] Verify the focused frontend and backend paths, generated API types and migration.

## Final checks

- [x] Exercise the running app in creation and editing, capture screenshots and inspect worker activity.
- [x] Run the root quality gate, audit the complete branch and obtain an independent read-only review.
- [x] Commit the finished change as one revertable commit on the existing branch.

## Workflow follow-up

- Sync and archive `reusable-capability-preparation` before syncing and archiving this change, so this delta supersedes its save-time requirement in order.
