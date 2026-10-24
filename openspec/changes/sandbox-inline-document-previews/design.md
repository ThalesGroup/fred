## Context

`stream_document` builds one `headers` dict (`Accept-Ranges`, inline
`Content-Disposition`) and reuses it for the full 200 and the ranged 206
`StreamingResponse`. The media type is whatever the content store recorded for
the upload, so any active type (SVG, HTML, XML) is served inline as-is.

The only UI consumer is `PdfStreamingDocumentViewer`: pdf.js fetches the URL
with a bearer header (size probe with `Range: bytes=0-0`, then range
requests). Nothing loads this URL in an `<iframe>`, `<img>`, `<object>`, media
element, or top-level navigation.

## Goals / Non-Goals

**Goals:**

- Neither the 200 nor the 206 response can run active content if a browser
  ever opens it as a document on the application origin.
- Define the hardening headers once so the two branches cannot drift.

**Non-Goals:**

- Switching the stream to `attachment`: the inline PDF preview relies on it.
  Kept only as a stronger option should a future flow need it.
- Changing `/raw_content/{uid}`, `/markdown/{uid}/media/...` or
  `/markdown/{uid}/artifact/...`: they are already served as `attachment`.
- Changing `/raw_content/pdf/{uid}`: it only ever serves a LibreOffice-rendered
  `application/pdf`, never a user-chosen active type.
- MIME allow-listing or rewriting active types at upload or serve time.

## Decisions

### Add the headers to the shared dict, once

A module-level mapping of the two headers is merged into the `headers` dict the
route already shares between both responses. This is the smallest change that
covers both status codes and keeps them in one place; a middleware or a
response subclass would widen the change to routes that do not need it.

### Plain `sandbox`, no allow tokens

`sandbox` with no tokens gives the document an opaque origin and blocks
scripts, forms and plugins. The self-test treats a sandbox without both
`allow-scripts` and `allow-same-origin` as effective; the bare directive is the
strictest form.

### `nosniff` alongside

It stops a browser from re-interpreting a mislabelled upload (for example an
HTML file stored as `text/plain`) as something more active.

## Risks / Trade-offs

- [A future flow opens the stream as a top-level PDF document] → Chromium
  refuses to render a PDF under a `sandbox` CSP. Today no flow does (bearer
  auth makes navigation impossible); such a flow would need a dedicated
  endpoint or a blob URL, which does not inherit the response CSP.
- [pdf.js behaviour] → CSP response headers apply to documents and workers,
  not to `fetch`/XHR bodies, so range loading is unaffected.

## Migration Plan

Normal Knowledge Flow deployment; rollback simply drops the two headers.
