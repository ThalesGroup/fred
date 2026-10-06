## 1. Retire the Team Resources entry point

- [ ] 1.1 Remove the `mine` tab, root path, stats query, and workspace render from `TeamResourcesPage`; verify its focused frontend tests show only supported roots with the feature flag on and off.
- [ ] 1.2 Remove active “Mon espace” labels and feature-flag descriptions that no longer apply; verify a current-source search has no UI entry point to `/teams/{team}/users/{uid}`.

## 2. Retire the backend personal area

- [ ] 2.1 Remove top-level `users` routing and synthetic list/stat entries from Knowledge Flow's scoped filesystem while retaining nested agent `users`; verify focused tests reject the personal path and accept agent and shared paths.
- [ ] 2.2 Remove top-level personal-path handling from filesystem search/provenance and check every `/fs` operation for bypasses; verify list, stat, read, write, delete, search, and copy cases cannot access that prefix, while existing agent-file tests pass.

## 3. Align agent authoring contracts

- [ ] 3.1 Remove `read_user_bytes` and `ToolContext.read_user` from the SDK port and runtime adapter; verify focused SDK/runtime tests and a repository consumer search find no remaining dependency.
- [ ] 3.2 Align `ToolContext.resolve_template` with Graph's agent-first, shared-second lookup; verify tests for precedence, shared fallback, and missing template.

## 4. Reconcile documentation and verify the lot

- [ ] 4.1 Update current filesystem, resource dashboard, and authoring documentation while leaving historical RFCs/archives as history; verify active docs describe the supported roots and retained object policy.
- [ ] 4.2 Run affected frontend, Knowledge Flow, SDK, and runtime checks plus root code quality, then review the full branch diff against its target branch and record findings and dispositions in the PR or task response.
- [ ] 4.3 Reconcile this change's artifacts with the implementation, validate and sync its delta spec, and archive the change; verify OpenSpec reports completion.
