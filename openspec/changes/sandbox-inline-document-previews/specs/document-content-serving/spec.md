## ADDED Requirements

### Requirement: Inline document streams cannot run active content
Knowledge Flow SHALL serve every response of the inline raw-content stream
(`/raw_content/stream/{document_uid}`), full or ranged, with
`Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff`,
whatever MIME type the document was stored with.

#### Scenario: Full SVG stream is sandboxed
- **GIVEN** a readable document stored as `image/svg+xml`
- **WHEN** a client requests its raw-content stream without a `Range` header
- **THEN** the response is HTTP 200 with `Content-Type: image/svg+xml`, an
  `inline` `Content-Disposition`, `Content-Security-Policy: sandbox` and
  `X-Content-Type-Options: nosniff`

#### Scenario: Ranged SVG stream is sandboxed
- **GIVEN** a readable document stored as `image/svg+xml`
- **WHEN** a client requests a byte range of its raw-content stream
- **THEN** the response is HTTP 206 with the requested bytes, a matching
  `Content-Range`, and the same `Content-Security-Policy: sandbox` and
  `X-Content-Type-Options: nosniff` headers

### Requirement: Inline PDF previews keep working
Knowledge Flow MUST keep serving the raw-content stream with an `inline`
disposition and its stored MIME type, so the in-app PDF viewer can still load
a document by full or ranged requests.

#### Scenario: PDF preview stream
- **GIVEN** a readable document stored as `application/pdf`
- **WHEN** the PDF viewer requests its raw-content stream
- **THEN** the response is HTTP 200 with `Content-Type: application/pdf`, an
  `inline` `Content-Disposition` and the complete document bytes
