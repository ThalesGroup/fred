## Why

`GET /knowledge-flow/v1/raw_content/stream/{document_uid}` serves an uploaded
file inline with its stored MIME type. An uploaded SVG therefore comes back as
an inline `image/svg+xml` document on the application origin, with neither a
`Content-Security-Policy: sandbox` nor `X-Content-Type-Options: nosniff`. The
admin self-test (`inline-active-content` step) flags this on every deployment.

No exploit path exists today: the endpoint requires a bearer token, so a
navigation or attacker link cannot load it, and the UI previews only PDFs from
it through pdf.js (a `fetch`, never a document context). The missing headers
are a latent weakness, closed here as defense in depth
([#3200](https://github.com/ThalesGroup/fred/issues/3200)).

## What Changes

- The raw-content stream sets `Content-Security-Policy: sandbox` and
  `X-Content-Type-Options: nosniff` on both its full (200) and ranged (206)
  responses, defined once and shared by both.
- `Content-Disposition` stays `inline`: the PDF preview depends on it.
- Offline regression tests drive the real route with a fake content store
  returning an SVG, for full and ranged requests, plus a PDF control case.

## Capabilities

### New Capabilities

- `document-content-serving`: how Knowledge Flow serves stored document bytes
  back to the browser.

### Modified Capabilities

None.

## Impact

- Affected code: `features/content/content_controller.py`
  (`stream_document`) and a new focused controller test in
  `apps/knowledge-flow-backend`.
- API shape, status codes, body bytes and OpenAPI are unchanged; only two
  response headers are added.
- Frontend: unaffected. pdf.js reads the stream with `fetch`/XHR, to which a
  response CSP does not apply.
- No configuration, data migration or vector-store impact.
