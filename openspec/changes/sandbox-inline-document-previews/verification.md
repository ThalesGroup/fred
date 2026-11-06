# Verification

## Environment note

`uv sync` / `make dev` could not complete in the worktree (package downloads
timed out), so tests ran on the main checkout's Knowledge Flow venv with the
worktree's code forced first on `PYTHONPATH`. The import was checked to resolve
to the worktree (`knowledge_flow_backend.__file__` under
`.claude/worktrees/.../apps/knowledge-flow-backend`). Commands, from the
worktree's `apps/knowledge-flow-backend`:

```
PYTHONPATH=$PWD /home/thomas/Documents/fred/apps/knowledge-flow-backend/.venv/bin/python \
  -m pytest <target> -q -m "not integration" --disable-socket --allow-unix-socket -p no:cacheprovider
```

## Evidence

- Focused test `tests/features/content/test_raw_content_stream_headers.py`:
  **5 passed** (full SVG 200; ranged SVG 206 for `bytes=0-9`, `bytes=10-`,
  `bytes=-5` with exact byte window and `Content-Range`; PDF 200 control).
- Same test with the controller change reverted: **5 failed**
  (`KeyError: 'content-security-policy'`), proving the regression is caught.
- Full offline suite (the `make test` selection, without coverage):
  **1606 passed, 2 skipped, 45 deselected**.
- Ruff (`check` + `format`) on the two touched Python files: all checks
  passed, 2 files unchanged.
- Migration note: `scripts/migration_guides.py check-pr --worktree` (the
  `make migration-check` command) run with the main checkout's fred-pod venv:
  valid against `fix/3209-public-team-sessions` (1 new declaration) and
  `origin/swift` (3 new declarations).
- `openspec validate sandbox-inline-document-previews --strict`: valid.

## Frontend impact

The only UI consumer of `/raw_content/stream/{uid}` is
`PdfStreamingDocumentViewer` (pdf.js `{ url, httpHeaders }` plus a `fetch`
size probe). A response CSP governs documents and workers, not `fetch`/XHR
bodies, so loading is unaffected. No `<iframe>`, `<img>`, `<object>`, media
element, blob navigation or top-level link uses this URL. Downloads use
`/raw_content/{uid}` (already `attachment`). The admin self-test step
`inline-active-content` treats a bare `sandbox` as effective.

## Not verified

- No browser run of the PDF viewer against a live stack.
- Root `make code-quality` (basedpyright) not run here.
