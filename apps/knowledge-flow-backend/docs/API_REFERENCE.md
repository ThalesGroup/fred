# Knowledge Flow document API reference

This reference describes the ten mounted document and tabular REST operations
from the generated OpenAPI contract. **Static generation is not functional
validation.** These operations and the examples have not been validated end to
end by this documentation increment. This technical reference is outside the
arc42 dossier's validated Weaver journeys.

See [integration without the Fred SDK](INTEGRATION.md) for delegated credentials,
JSON header encoding, scope semantics, transport limits and request examples.
The [developer guide](DEVELOPER_GUIDE.md#document-context-contract) describes
the runtime-to-REST/MCP path and request isolation.

The prefix below comes from the configuration used during export; callers must
use their deployment's configured `app.base_url` (normally `/knowledge-flow/v2`).
The four tabular operations are also projected as MCP tools at `/mcp/tabular`
relative to that prefix. Document operations are REST only in this mounted set.

Regenerate from the repository root with the existing arc42 documentation tool:

```sh
make -C docs/architecture knowledge-flow-reference
make -C docs/architecture check-knowledge-flow-reference
```

Both targets reuse KF's `generate-openapi` target and the shared
`scripts/generate_openapi.py`; the second checks generated-content freshness.
They do not run HTTP requests, authorization scenarios, model calls or Weaver
journeys. Do not edit the generated block below by hand.

<!-- generated: openapi apps/knowledge-flow-backend/openapi.json documents tabular -->
Paths are relative to `/knowledge-flow/v2`.

Operations: [`/documents`](#documents-routes) · [`/tabular`](#tabular-routes). [Schemas](#schemas).

## /documents routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/documents/search](#post-documentssearch) | Search documents using vectorization |
| GET | [/documents/tree](#get-documentstree) | List visible corpus folders and documents |
| GET | [/documents/{document_uid}/chunks](#get-documentsdocument_uidchunks) | Fetch a document's published chunks in index order |
| POST | [/documents/{document_uid}/extract](#post-documentsdocument_uidextract) | Extract information from a document |
| GET | [/documents/{document_uid}/markdown](#get-documentsdocument_uidmarkdown) | Read a document's full published markdown |
| POST | [/documents/{document_uid}/summarize](#post-documentsdocument_uidsummarize) | Summarize a document on demand |

### POST /documents/search

Search documents using vectorization. Returns up to top_k ranked published chunks from the selected corpus (context space and ancestors) and explicitly listed attachments in the exact owned conversation. Two active sources use reciprocal-rank fusion with chunk deduplication; a single source preserves its ranking and scores. Fewer hits, including an empty array, are valid. No offset or pagination token. Scores depend on the search policy and are not probabilities. A hit is rechecked against publication and lifecycle facts.

Operation `search_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`SearchRequest`](#searchrequest).

- 200: array of [`VectorSearchHit`](#vectorsearchhit) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access. The document index may also be unavailable (corpus_not_ready).

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### GET /documents/tree

List visible corpus folders and documents. Returns structured spaces, folders and visible published documents in the authorized context space and ancestors, intersected with the context selection. Conversation attachments are excluded. folder_id starts at an in-scope folder; absent means root. Folder and document records together are capped by limit (default 1000, maximum 5000), ordered by space, folder ID path and name, with IDs breaking ties. Ancestor folders provide structure only, never permission to read their other contents. An empty result means no visible entries in this selection. truncated=true reports omitted records and does not establish completeness; there is no continuation token. This is not an existence oracle: an unavailable or out-of-scope folder returns the same 404 folder_not_found.

Operation `list_document_tree`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `folder_id` | query | string (uuid) or null |  |  |
| `limit` | query | integer, >= 1, <= 5000 |  | Default: `1000`. |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: [`DocumentTreeResponse`](#documenttreeresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Folder unavailable or outside the authorized selection (folder_not_found); not an existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### GET /documents/{document_uid}/chunks

Fetch a document's published chunks in index order. Returns chunks from the published generation of a visible corpus document or explicitly authorized conversation attachment, in chunk_index order, capped by limit (default 200, maximum 1000). No continuation token or truncation flag: reaching the limit does not establish completeness. An empty array also covers no visible chunks or a vector store without direct chunk-read support. This is not an existence check or a whole-document guarantee.

Operation `get_document_chunks`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `limit` | query | integer, >= 1, <= 1000 |  | Default: `200`. |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`VectorSearchHit`](#vectorsearchhit) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access. The document index may also be unavailable (corpus_not_ready).

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### POST /documents/{document_uid}/extract

Extract information from a document. Extracts items matching an instruction from authorized published markdown, using bounded map calls and deduplication. Input above 2,000,000 characters is reduced to its first and last 1,000,000 characters and flagged truncated. Individual model-call failures are logged and contribute no items; they do not set truncated or necessarily fail the HTTP request. A successful response is therefore not proof of exhaustive extraction. Use a verbatim read when the exact source text is required.

Operation `extract_document`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`ExtractDocumentRequest`](#extractdocumentrequest).

- 200: [`ExtractDocumentResponse`](#extractdocumentresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### GET /documents/{document_uid}/markdown

Read a document's full published markdown. Returns the published output.md text after shared space, corpus selection or explicit conversation attachment, ownership and lifecycle checks. Not an original binary download. Missing or non-visible documents return 404. No pagination; clients must budget for the whole response.

Operation `get_document_markdown`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: [`MarkdownResponse`](#markdownresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### POST /documents/{document_uid}/summarize

Summarize a document on demand. Generates a fresh, steerable summary of an already-ingested document. Unlike the abstract persisted at ingestion time (fixed, generic, ~180 words), this endpoint accepts an optional `instruction` to focus the summary (e.g. "focus on financial risks", "list every action item") and a `max_chars` budget. Large documents are summarized via map-reduce; small documents take a single pass. If the result still exceeds `max_chars`, one corrective pass attempts to shorten it. This is a target, not a guaranteed output length: the corrective pass may fail or remain above the budget. LLM output is selective and may omit source information; this is not a verbatim read.

Operation `summarize_document`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`SummarizeDocumentRequest`](#summarizedocumentrequest).

- 200: [`SummarizeDocumentResponse`](#summarizedocumentresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

## /tabular routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/tabular/documents](#get-tabulardocuments) | List published tabular documents in the active document selection |
| GET | [/tabular/documents/schemas](#get-tabulardocumentsschemas) | Inspect document catalogs, SQL aliases and column types |
| POST | [/tabular/query](#post-tabularquery) | Run one read-only DuckDB SELECT over discovered tables |
| POST | [/tabular/search](#post-tabularsearch) | Locate a precise value after inspecting document structure |

### GET /tabular/documents

List published tabular documents in the active document selection. Lists authorized published CSV/Excel documents. Empty selection returns an empty array. No pagination parameter or fixed response-count cap. Excel includes table identities; CSV omits tables in this compact listing. Use describe_tabular_documents to obtain exact SQL aliases and columns. Sources are the union of the selected corpus and explicitly authorized conversation attachments, further narrowed by requested dataset/document IDs. Published Parquet artifacts do not require vector chunks. All sheets/tables keep their existing aliases; no dataset outside this union is mounted.

Operation `list_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`TabularDocumentListResponse`](#tabulardocumentlistresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### GET /tabular/documents/schemas

Inspect document catalogs, SQL aliases and column types. Inspect the catalog, SQL table aliases and column types before querying. Pass exact document UIDs from list_tabular_documents; every one must belong to the active document selection. Batch several documents when a query will join them. For Excel, read the published markdown catalog first, then inspect tables[].columns. CSV markdown is null. Describe all tables by default, or select table_names to inspect only relevant schemas; the workbook catalog stays complete. The configured max_selected_datasets bounds the total tables described, and analysis is subject to the same tabular execution budgets. Categorical string categorical_values contain all distinct non-null values: preserve their exact spelling and format in filters. Numeric min_value and max_value are finite observed bounds, not query answers. Use query_alias in SQL FROM/JOIN clauses and document UIDs only as document selectors. Sources are the union of the selected corpus and explicitly authorized conversation attachments, further narrowed by requested dataset/document IDs. Published Parquet artifacts do not require vector chunks. All sheets/tables keep their existing aliases; no dataset outside this union is mounted.

Operation `describe_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uids` | query | array of string, min items 1, max items 1000 | yes | Document UUIDs copied exactly from list_tabular_documents, not filenames or SQL table aliases. Repeat the parameter for several documents. All requested documents must be in scope; 1 to 1000 identifiers. |
| `table_names` | query | array of string, max items 1000 or null |  | Optional exact query_alias values or unambiguous sheet/title names. Omit or pass an empty list for all tables. Does not rename SQL aliases. |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`TabularDocumentDescriptionResponse`](#tabulardocumentdescriptionresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
- 504: [`KnowledgeFlowError`](#knowledgeflowerror) — Tabular execution budget exceeded. Narrow datasets or query before retrying; cancellation of blocked I/O is best effort.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### POST /tabular/query

Run one read-only DuckDB SELECT over discovered tables. Run one read-only DuckDB SELECT after describing every document it reads. Use exact query_alias values from describe_tabular_documents in FROM/JOIN. dataset_uids narrows the active selection; a workbook UID includes all its tables. SQL must reference at least one dataset. Execution, memory, row and dataset ceilings come from storage.tabular_store.query. Results stop at row_limit, without pagination; truncated=true means rows is partial. Compute totals and aggregates in SQL instead of inferring them from previews. rows=[] with error=null is a successful query with zero matching rows and an explicit success message. A zero count or null aggregate is still a row. Reuse successful results; inspect types and filters before changing an unexpectedly empty query instead of repeating it unchanged. HTTP 400 requires correcting SQL or arguments. Retry capacity 503 with bounded backoff; for 504 narrow the query. Sources are the union of the selected corpus and explicitly authorized conversation attachments, further narrowed by requested dataset/document IDs. Published Parquet artifacts do not require vector chunks. All sheets/tables keep their existing aliases; no dataset outside this union is mounted.

Operation `query_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`TabularQueryRequest`](#tabularqueryrequest).

- 200: [`RawSQLResponse`](#rawsqlresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
- 504: [`KnowledgeFlowError`](#knowledgeflowerror) — Tabular execution budget exceeded. Narrow datasets or query before retrying; cancellation of blocked I/O is best effort.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

### POST /tabular/search

Locate a precise value after inspecting document structure. Locate a precise value when the inspected catalog cannot identify its table. Use only after describe_tabular_documents, as a last-resort value locator rather than a structure-discovery or aggregation tool. Matching ignores case, accents and whitespace; numeric columns are searchable too. Use dataset_uids to narrow the search. The stripped keyword must have at least two characters and must remain nonempty after normalization. Up to 5 rows per table and 30 matching tables; callers may lower these caps. The configured dataset scan ceiling can further restrict work. Inspect tables_truncated and each match's row_truncated; an empty matches list with truncation is not proof the value is absent. Use the located aliases in a subsequent query_tabular_documents. Sources are the union of the selected corpus and explicitly authorized conversation attachments, further narrowed by requested dataset/document IDs. Published Parquet artifacts do not require vector chunks. All sheets/tables keep their existing aliases; no dataset outside this union is mounted.

Operation `search_tabular_values`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`TabularSearchRequest`](#tabularsearchrequest).

- 200: [`TabularSearchResponse`](#tabularsearchresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required) or rejected delegation. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — A required data dependency is unavailable; this never grants access. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
- 504: [`KnowledgeFlowError`](#knowledgeflowerror) — Tabular execution budget exceeded. Narrow datasets or query before retrying; cancellation of blocked I/O is best effort.

Response 400 example `invalid_context` (`application/json`):

```json
{
  "detail": "invalid_document_context"
}
```

Response 403 header `X-Fred-Denial-Cause`: `permission_refused`, `account_suspended`. Present for authorization/account errors only. Not emitted by every response with this status.

Response 403 example `missing_context` (`application/json`):

```json
{
  "detail": "document_context_required"
}
```

Response 503 header `X-Fred-Denial-Cause`: `account_status_unavailable`. Present for authorization/account errors only. Not emitted by every response with this status.

## Schemas

### DocumentAccessContext

Server-bound space, admitted corpus, selection and explicit conversation attachments, accepted only from an authenticated delegated caller. Never inferred from model arguments. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `attachment_ids` | array of string (uuid) |  | Explicit attachment UUIDs, independently of corpus selection. Empty grants no attachment access; requires conversation_id. SQL verifies every document. Default: `[]`. |
| `authorized_space_ids` | array of string (uuid) | yes | Exact corpus authorized by Control Plane at turn admission, carried by the trusted workload. Empty grants no corpus access. |
| `conversation_id` | string (uuid) or null |  | Server-bound conversation UUID; SQL verifies its owner, exact space and live state. Default: `null`. |
| `document_scope` | [`DocumentScope`](#documentscope) | yes | Corpus-only intersection of selection clauses. Zero clauses add no filter; one empty clause selects no corpus documents. Attachments are selected separately. |
| `space_id` | string (uuid) | yes | Admitted turn's space UUID; SQL checks its current lifecycle, not the person's admission rights. |

### DocumentScope

Intersection of selections, evaluated on document placement in Knowledge Flow. No selections means unrestricted; one empty selection means nothing. Keeping the clauses separate preserves folder/document overlap without enumerating a corpus. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `selections` | array of [`DocumentSelection`](#documentselection) |  | All clauses must match. An omitted or empty array adds no filter within the authorized space. No identifier-count cap is imposed here; HTTP server and proxy header limits still apply. Default: `[]`. |

### DocumentSelection

Union of direct folder contents and explicit documents, using Weaver IDs. No recursive expansion: a picker represents a subtree by selecting its folders. An empty selection covers no documents. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_ids` | array of string (uuid) |  | Explicit document UUIDs, unioned with this clause's folder contents. Omitted means no explicit documents. A clause with neither selects nothing. Default: `[]`. |
| `folder_ids` | array of string (uuid) |  | Union of direct folder contents; not recursive. Omitted means no folders in this clause. Default: `[]`. |

### DocumentTreeDocument

Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `added_at` | string (date-time) | yes |  |
| `document_uid` | string (uuid) | yes |  |
| `folder_id` | string (uuid) or null | yes |  |
| `mime` | string | yes |  |
| `name` | string | yes |  |
| `space_id` | string (uuid) | yes |  |

### DocumentTreeFolder

Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `folder_id` | string (uuid) | yes |  |
| `name` | string | yes |  |
| `parent_id` | string (uuid) or null | yes |  |
| `space_id` | string (uuid) | yes |  |

### DocumentTreeResponse

Bounded corpus navigation; folder/document records count towards limit. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `documents` | array of [`DocumentTreeDocument`](#documenttreedocument) |  | Default: `[]`. |
| `folders` | array of [`DocumentTreeFolder`](#documenttreefolder) |  | Default: `[]`. |
| `spaces` | array of [`DocumentTreeSpace`](#documenttreespace) |  | Default: `[]`. |
| `truncated` | boolean |  | Default: `false`. |

### DocumentTreeSpace

Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `space_id` | string (uuid) | yes |  |

### ExtractDocumentRequest

Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `instruction` | string, min length 1 | yes | What to extract exhaustively, e.g. 'every functional requirement', 'all deadlines and their context'. |

### ExtractDocumentResponse

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `chunks_processed` | integer | yes | Number of map windows attempted, not the number of successful model calls or source chunks. |
| `document_uid` | string | yes |  |
| `extraction` | string | yes | Consolidated, de-duplicated list of every extracted item (markdown bullets), in document order. |
| `item_count` | integer | yes |  |
| `truncated` | boolean | yes | True only when input exceeded the 2,000,000-character cap and was head/tail-windowed. Does not report individual model-call failures. |

### HTTPValidationError

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `detail` | array of [`ValidationError`](#validationerror) |  |  |

### KnowledgeFlowError

Existing HTTP error envelope. Request-validation errors use HTTPValidationError instead.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `detail` | string | yes | Error code or message. Do not assume all messages are stable machine-readable codes. |

### MarkdownResponse

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `content` | string | yes | Full UTF-8 text of the authorized published output.md artifact; no pagination or response-size limit is imposed here. |

### RawSQLResponse

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dataset_uids` | array of string |  | Document UUIDs of the mounted tables. A workbook UUID may appear more than once. |
| `error` | string or null |  | Null on this mounted success path; failures use HTTP error statuses, not a success response containing an error. |
| `message` | string or null |  | Explicit success explanation when the query returned zero rows (not an error or a claim that the whole document has no relevant information) or when the result is truncated. |
| `query_aliases` | array of string |  | Exact aliases of the mounted tables used by the query. |
| `row_limit` | integer or null |  | Result-row limit applied to this query. |
| `rows` | array of object |  | JSON objects keyed by selected SQL columns; values depend on the query. At most row_limit rows. |
| `sql_query` | string | yes | Validated SQL before the server adds its outer result-row LIMIT. |
| `truncated` | boolean |  | True when the query produced more rows than row_limit: rows is partial, so compute counts and totals with SQL aggregates. Default: `false`. |

### SearchPolicyName

One of: `hybrid`, `strict`, `semantic`.

### SearchRequest

Search arguments; document authority comes from the authenticated header. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `min_score` | number or null |  | Keep hits whose original retrieval score (or 0.0 when absent) is at least this value, after optional reranking and its top_k limit. |
| `question` | string | yes | Natural-language search query. This operation returns chunks, not a generated answer. |
| `rerank` | boolean |  | Retrieve up to min(top_k * 5, 100) candidates and rerank visible, in-scope hits with the cross-encoder, keeping top_k. Retrieval scores are unchanged. Default: `false`. |
| `search_policy` | [`SearchPolicyName`](#searchpolicyname) or null |  | Optional search policy preset. If omitted, defaults to 'hybrid'. |
| `top_k` | integer, >= 1.0, <= 100.0 |  | Number of results to return. Default: `10`. |

### SummarizeDocumentRequest

Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `instruction` | string or null |  | Free-text instruction steering the summary: focus area, audience, what to look for, desired length/tone. |
| `max_chars` | integer, >= 200.0, <= 20000.0 |  | Target summary length in characters, not a guaranteed ceiling. One corrective pass is attempted if exceeded. Default: `2000`. |

### SummarizeDocumentResponse

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_uid` | string | yes |  |
| `keywords` | array of string |  |  |
| `shrunk_for_budget` | boolean | yes | True when a corrective rewriting pass completed. This does not guarantee that the result is within max_chars. |
| `summary` | string | yes |  |

### TabularColumnDescription

Compact public schema, separate from stored ingestion classification.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `categorical_values` | array of string or null |  | Exact distinct non-null categories, preserving spelling and case. Present only for a described categorical string column. |
| `dtype` | `string`, `integer`, `float`, `boolean`, `datetime`, `unknown` | yes |  |
| `max_value` | integer or number or null |  | Largest finite value. Present only for integer/float columns; null if none exist. |
| `min_value` | integer or number or null |  | Smallest finite value. Present only for integer/float columns; null if none exist. |
| `name` | string | yes |  |

### TabularDocumentDescriptionResponse

Extraction catalog and full schemas for one authorized tabular document. Why this exists: - One batch call must return the workbook context before its typed tables, while CSV documents expose their typed table without a catalog. How to use: - Returned by `GET /tabular/documents/schemas` (one entry per requested document uid).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_name` | string | yes |  |
| `document_uid` | string | yes |  |
| `kind` | `csv`, `spreadsheet` | yes |  |
| `markdown` | string or null |  |  |
| `source_tag` | string or null |  |  |
| `tables` | array of [`TabularTableSchema`](#tabulartableschema) |  |  |

### TabularDocumentListResponse

Document name and identifiers needed by later tabular tools.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_name` | string | yes |  |
| `document_uid` | string | yes |  |
| `source_kind` | `corpus`, `conversation_attachment` |  | Default: `"corpus"`. |
| `tables` | array of [`TabularDocumentListTableResponse`](#tabulardocumentlisttableresponse) or null |  |  |
| `tag_names` | array of string or null |  |  |

### TabularDocumentListTableResponse

Excel table identity exposed by the document-list endpoint.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `query_alias` | string | yes |  |
| `sheet` | string or null |  |  |
| `title` | string or null |  |  |

### TabularQueryRequest

One read-only DuckDB SELECT over authorized document tables. sql uses discovered table aliases; dataset_uids scopes exact document UUIDs. If omitted, SQL may reference any table in the active authorized scope; only referenced tables are mounted. An explicit empty list selects nothing. The query must read at least one table and respect the server's dataset limit. The trusted document scope is supplied by the runtime outside tool arguments. max_rows caps the returned preview; compute totals and statistics in SQL. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dataset_uids` | array of string, max items 1000 or null |  | Document UUIDs copied exactly from authorized discovery, not filenames, SQL aliases or shortened identifiers. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook UUID selects all its tables. |
| `max_rows` | integer, >= 1.0 or null |  | Requested result-row limit; omitted/null uses configured default_max_rows. Clamped to configured max_rows, not rejected when larger. No pagination; the response says when rows were cut. For totals or statistics, aggregate in SQL rather than counting this preview. |
| `sql` | string, min length 1 | yes | One read-only DuckDB SELECT/WITH using exact tables[].query_alias values from describe_tabular_documents. These aliases are SQL table names, not document UUIDs or filenames. Must reference an authorized dataset; SELECT 1, writes and external reads are refused. |

### TabularSearchRequest

Bounded lookup of a precise value after inspecting document structure. Schemas expose types and categorical values; this locator helps find other cell values across tables. dataset_uids scopes exact document UIDs, with one workbook UID covering all its tables. If omitted, all readable datasets in the active scope may be searched. Prefer a narrow scope and keyword. Preview ceilings can be lowered, never raised; truncation means partial coverage and requires refining the search. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dataset_uids` | array of string, max items 1000 or null |  | Document UUIDs copied exactly from authorized discovery, not filenames, SQL aliases or shortened identifiers. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook UUID selects all its tables. |
| `keyword` | string, min length 1 | yes | Precise word or expression of at least two characters after trimming (400 otherwise), nonempty once normalized. Case/accent/whitespace-insensitive substring matching, including numeric columns. Use after document description; generic terms match too many tables to locate a value. |
| `max_matching_tables` | integer, >= 1.0, <= 30.0 |  | Maximum tables with a match returned before the search stops (ceiling). Default: `30`. |
| `max_rows_per_table` | integer, >= 1.0, <= 5.0 |  | Maximum matching rows returned per table (ceiling). Default: `5`. |

### TabularSearchResponse

Result of a keyword value-locator search. Why this exists: - One payload tells the agent where a value occurs and warns when the result is partial, so it refines the keyword instead of trusting a truncated picture. How to use: - Returned by `POST /tabular/search`. - When `tables_truncated` is true the result is partial, for one of two reasons: the keyword matched more tables than `max_matching_tables` (it is too generic — refine it), or the scope held more datasets than one request may scan (scope it with `dataset_uids`). Compare `searched_dataset_uids` with what you expected to tell the two apart.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `keyword` | string | yes |  |
| `matches` | array of [`TabularTableMatch`](#tabulartablematch) |  |  |
| `normalized_keyword` | string | yes |  |
| `searched_dataset_uids` | array of string |  | Documents that were in scope for this search. A document dropped by the dataset limit is omitted entirely. Note this is not proof a listed document was read exhaustively: when tables_truncated is true the scan stopped early, so a listed document may still hold the keyword in a table that was never opened. |
| `tables_truncated` | boolean |  | True when the result is partial: either the max_matching_tables cap was reached, or the scope exceeded the number of datasets one search may scan. Other tables may also contain the value. Default: `false`. |

### TabularTableMatch

One table in which the searched keyword was found. Why this exists: - The agent needs to know exactly which table and which columns hold the value, and to see a bounded sample of matching rows, before issuing one targeted `query_tabular_documents`. How to use: - Returned inside `TabularSearchResponse.matches`. - Query the table via its `query_alias`; `matched_columns` names the columns to filter on.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_name` | string | yes |  |
| `document_uid` | string | yes |  |
| `matched_columns` | array of string |  |  |
| `query_alias` | string | yes |  |
| `row_truncated` | boolean |  | True when more matching rows existed than were returned (max_rows_per_table reached): other occurrences remain in this table. Default: `false`. |
| `rows` | array of object |  |  |
| `sheet` | string or null |  |  |
| `title` | string or null |  |  |

### TabularTableSchema

Full schema for one queryable table (summary fields plus columns). Why this exists: - Schema inspection is table-level for multi-table documents; every table of a workbook must be visible, not only the first one. How to use: - Returned inside `TabularDocumentDescriptionResponse.tables`.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `columns` | array of [`TabularColumnDescription`](#tabularcolumndescription) |  |  |
| `generated_at` | string or null |  |  |
| `query_alias` | string | yes |  |
| `row_count` | integer or null |  |  |
| `sheet` | string or null |  |  |
| `title` | string or null |  |  |

### ValidationError

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ctx` | object |  |  |
| `input` | any |  |  |
| `loc` | array of string or integer | yes |  |
| `msg` | string | yes |  |
| `type` | string | yes |  |

### VectorSearchHit

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `author` | string or null |  |  |
| `chunk_index` | integer or null |  | Position of the chunk inside its source document, used to restore document order |
| `chunk_kind` | string or null |  | content (default, real ingested prose/data) or 'dataset_pointer' (a discovery pointer to a structured dataset, never citable as a source) or 'markdown_table' (a Markdown table kept whole or split on row boundaries). |
| `citation_url` | string or null |  |  |
| `confidential` | boolean or null |  |  |
| `content` | string | yes |  |
| `created` | string or null |  |  |
| `embedding_model` | string or null |  |  |
| `file_name` | string or null |  |  |
| `file_path` | string or null |  |  |
| `has_visual_evidence` | boolean or null |  |  |
| `language` | string or null |  |  |
| `license` | string or null |  |  |
| `mime_type` | string or null |  |  |
| `modified` | string or null |  |  |
| `page` | integer or null |  |  |
| `preview_at_url` | string or null |  |  |
| `preview_url` | string or null |  |  |
| `pull_location` | string or null |  |  |
| `rank` | integer or null |  |  |
| `repo_url` | string or null |  |  |
| `repository` | string or null |  |  |
| `retrieval_session_id` | string or null |  |  |
| `retrieved_at` | string or null |  |  |
| `score` | number | yes | Similarity score from vector search |
| `section` | string or null |  |  |
| `slide_id` | integer or null |  |  |
| `slide_image_uri` | string or null |  |  |
| `tag_full_paths` | array of string |  | Default: `[]`. |
| `tag_ids` | array of string |  | Default: `[]`. |
| `tag_names` | array of string |  | Default: `[]`. |
| `title` | string | yes |  |
| `token_count` | integer or null |  |  |
| `type` | string or null |  | File type/category |
| `uid` | string | yes | Document UID |
| `vector_index` | string or null |  |  |
| `viewer_fragment` | string or null |  |  |
<!-- end generated -->
