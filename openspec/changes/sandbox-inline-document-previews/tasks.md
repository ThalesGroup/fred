## 1. Sandbox the raw-content stream

- [x] 1.1 Define `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff` once in `content_controller.py` and merge them into the headers shared by the 200 and 206 responses of `/raw_content/stream/{document_uid}`, keeping `Content-Disposition: inline`.

## 2. Regression coverage

- [x] 2.1 Add a controller test that serves an SVG from a fake content store and asserts both headers, `Content-Type` and inline `Content-Disposition` on a full (200) request.
- [x] 2.2 Assert the same headers and the exact byte window on a ranged (206) request.
- [x] 2.3 Add a PDF control case proving ordinary previews still return the full body inline.

## 3. Verification and close-out

- [x] 3.1 Run the focused test, then the full offline suite (the `make test` pytest selection) and Ruff on touched files in `apps/knowledge-flow-backend`.
- [x] 3.2 Confirm the frontend loads the stream only through pdf.js `fetch`, so the CSP cannot break the preview.
- [x] 3.3 Add the PR migration note and run the `make migration-check` validator.
- [x] 3.4 Record exact evidence in `verification.md` and run `openspec validate sandbox-inline-document-previews --strict`.
