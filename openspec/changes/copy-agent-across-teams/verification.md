## Verification

Verified on 2026-10-04 on branch `copy-agent-across-teams`.

### Automated tests

| Package | Command | Result |
|---|---|---|
| fred-sdk | `make test` | 511 passed, 3 skipped |
| fred-runtime | `make test` | 1784 passed, 11 skipped |
| fred-capability-ppt-filler | `make test` | 152 passed |
| fred-capability-document-access | `pytest` | 42 passed |
| fred-agents | `pytest` | 118 passed, 6 xfailed |
| control-plane-backend | `make test` | 1478 passed |
| libs/frontend | `npm test` | 379 passed |
| apps/frontend | `vitest run` | 285 files passed, 1 skipped; 3278 tests passed, 7 skipped |

`make code-quality` passed in every Python package above (fred-runtime keeps its existing `reportUnreachable` warnings). In `apps/frontend`, `tsc --noEmit`, ESLint and Prettier passed; they were run directly instead of `make code-quality` because that target clears the cache of the running Vite server.

What the tests prove:

- scope-private settings are reset on a copy to another scope and kept on a same-scope copy, for flat, list and nested models, including catalog-declared MCP keys;
- configuration files declared with `AssetKey` are read in the source and re-submitted to `validate_config` in the destination;
- a ppt-filler template whose image folders are missing in the destination is kept and reported as a notice;
- the guard test fails on an unclassified identifier-like field and passes on the real tree (entry points plus both MCP catalogs);
- the control plane checks `CAN_UPDATE_AGENTS` on the source and each destination, copies per destination with partial failures, drops a capability the destination cannot use, applies the `_imported-N` name rule, refuses a non-public template to a non-admin (404) and emits `agent.copied`;
- the dialog greys out teams without the template, warns on missing capabilities, never submits the source team and reports dropped capabilities and notices; Duplicate goes through the copy endpoint;
- the prompt import dialog tests pass unchanged after the move to `CopyToTeamsDialog`.

### Manual check

Run by the developer in the local stack, confirmed by `agent.copied` audit events:

- copies from a team to the personal space and from the personal space to a team;
- document access stays enabled with no library restriction (the restriction switch is reset since commit `9112d48a0`);
- the copied ppt-filler agent fills a presentation without re-upload and the preview opens;
- a template with missing image folders is copied and the toast lists the fields to redo.

Not checked manually: use of the copy by another editor of the destination team. The automated tests cover the destination permission check only.

### Code review

`/code-review` ran on the full branch diff. Findings 1–4 were fixed (commit `0d58e3904`); finding 5 (orphan configuration files when a copy fails after the files are stored) is documented as a risk in `design.md`.

### Follow-ups

- #2952: accept a ppt-filler template whose image folders do not exist yet, with a persistent message under the template instead of a toast.
