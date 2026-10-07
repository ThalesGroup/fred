## 1. SDK and package

- [x] 1.1 Move MCP capability types/builders and catalog loaders into the SDK; verify SDK-only behavior tests and compatibility imports.
- [x] 1.2 Expose the packaged catalog through an installed entry point, update dependencies and remove pod catalog copies; verify package discovery and wheel resources.

## 2. Runtime integration

- [x] 2.1 Resolve external or installed catalogs once at startup; test override precedence, empty/missing overrides, disabled servers, duplicate IDs and provider failures.
- [x] 2.2 Update runtime consumers to SDK imports; run SDK, runtime and pod suites plus root code quality and raw typing.

## 3. Close-out

- [x] 3.1 Update authoring/operations documentation and migration note; verify migration checks and record independent review outcomes.
- [x] 3.2 Reconcile and archive this change after verification, show the complete unstaged diff, and confirm no commit was created.

## Verification evidence

- `make test`: SDK 514 passed / 3 skipped; runtime 1,634 passed / 11 skipped /
  17 integration tests deselected; fred-agents 91 passed / 6 existing xfails.
  SDK tests moved with their implementation; 27 focused SDK tests passed again
  after typing fixes. Runtime skips require the absent optional `fastapi_mcp`.
- Raw basedpyright: SDK and pod 0 errors / 0 warnings; runtime 0 errors /
  7 pre-existing unreachable-code warnings outside this change.
- Built `fred-capability-mcp` wheel and loaded its entry point directly from the
  archive in an isolated SDK interpreter with runtime imports forbidden. All
  eight resolved server models match the original catalog exactly. Chart server
  models and complete instruction strings also match the original.
- Root chart schema generation, values validation and migration checks passed.
  Dependent locks were regenerated with no existing package version changes.
- Independent spec and standards/performance reviews passed after correcting
  worktree port rewriting and moving diagnostic config reload off the event loop.
  Worktree path selection, warnings and port replacement were checked in a temp
  directory. MCP classes/builders match the original executable AST.
- No Docker image build or live MCP connection was performed.
- Root `make code-quality` passed for every module, including frontend.
- `git diff --check` passed; HEAD remains `5a8ee56d7`, index empty. The complete
  unstaged review was opened in Codex; no commit or publication was made.
