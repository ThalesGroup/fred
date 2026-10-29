# Knowledge Flow document API reference

This reference describes the nine mounted document and tabular REST operations
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
| GET | [/documents/{document_uid}/chunks](#get-documentsdocument_uidchunks) | Fetch a document's published chunks in index order |
| POST | [/documents/{document_uid}/extract](#post-documentsdocument_uidextract) | Extract information from a document |
| GET | [/documents/{document_uid}/markdown](#get-documentsdocument_uidmarkdown) | Read a document's full published markdown |
| POST | [/documents/{document_uid}/summarize](#post-documentsdocument_uidsummarize) | Summarize a document on demand |

### POST /documents/search

Search documents using vectorization. Returns up to top_k ranked published chunks from the context space and its ancestors, intersected with the document selection. Fewer hits, including an empty array, are valid. No offset or pagination token. Scores depend on the search policy and are not probabilities. A hit is rechecked against publication and lifecycle facts.

Operation `search_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`SearchRequest`](#searchrequest).

- 200: array of [`VectorSearchHit`](#vectorsearchhit) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant. The document index may also be unavailable (corpus_not_ready).

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

Fetch a document's published chunks in index order. Returns visible published chunks in chunk_index order, capped by limit (default 200, maximum 1000). No continuation token or truncation flag: reaching the limit does not establish completeness. An empty array also covers no visible chunks or a vector store without direct chunk-read support. This is not an existence check or a whole-document guarantee.

Operation `get_document_chunks`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `limit` | query | integer, >= 1, <= 1000 |  | Default: `200`. |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`VectorSearchHit`](#vectorsearchhit) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant. The document index may also be unavailable (corpus_not_ready).

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
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`ExtractDocumentRequest`](#extractdocumentrequest).

- 200: [`ExtractDocumentResponse`](#extractdocumentresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant.

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

Read a document's full published markdown. Returns the published output.md text after space, selection and lifecycle checks. Not an original binary download. Missing or non-visible documents return 404. No pagination; clients must budget for the whole response.

Operation `get_document_markdown`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uid` | path | string | yes |  |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: [`MarkdownResponse`](#markdownresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant.

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
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`SummarizeDocumentRequest`](#summarizedocumentrequest).

- 200: [`SummarizeDocumentResponse`](#summarizedocumentresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context).
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Document not visible, unpublished, retired, or published markdown unavailable (document_not_found); not a document-existence oracle.
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant.

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
| GET | [/tabular/documents/schemas](#get-tabulardocumentsschemas) | Read extraction catalogs and typed tables of selected documents |
| POST | [/tabular/query](#post-tabularquery) | Execute one read-only SELECT on authorized published datasets |
| POST | [/tabular/search](#post-tabularsearch) | Locate a precise value in authorized published datasets |

### GET /tabular/documents

List published tabular documents in the active document selection. Lists authorized published CSV/Excel documents. Empty selection returns an empty array. No pagination parameter or fixed response-count cap. Excel includes table identities; CSV omits tables in this compact listing. Use describe_tabular_documents to obtain exact SQL aliases and columns.

Operation `list_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`TabularDocumentListResponse`](#tabulardocumentlistresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant.

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

Read extraction catalogs and typed tables of selected documents. Use document UIDs from list_tabular_documents. Returns exact SQL aliases, column types, categorical values and numeric ranges; Excel includes its catalog. Every requested document must belong to the active document selection. The configured max_selected_datasets also bounds the total tables described; a workbook may contain multiple tables. CSV markdown is null; Excel returns its published extraction catalog. Category/range analysis is subject to the same tabular execution budgets.

Operation `describe_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `document_uids` | query | array of string, min items 1, max items 1000 | yes | Document UUIDs from listing, encoded as repeated document_uids query parameters. All requested documents must be in scope; 1 to 1000 identifiers. |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

- 200: array of [`TabularDocumentDescriptionResponse`](#tabulardocumentdescriptionresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
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

Execute one read-only SELECT on authorized published datasets. Use exact aliases from describe_tabular_documents. dataset_uids narrows the active selection; a workbook UID includes all its tables. SQL must reference at least one dataset. Execution, memory, row and dataset limits apply. Results are row-limited without a truncation flag or pagination token; reaching the row limit does not prove completeness. Dataset, memory, concurrency and timeout ceilings come from storage.tabular_store.query. Retry capacity 503 with bounded backoff; for 504 narrow the query.

Operation `query_tabular_documents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`TabularQueryRequest`](#tabularqueryrequest).

- 200: [`RawSQLResponse`](#rawsqlresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
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

Locate a precise value in authorized published datasets. Case/accent/whitespace-insensitive search, including numeric columns. Use dataset_uids to narrow the search. The stripped keyword must have at least two characters and must remain nonempty after normalization. Up to 5 rows per table and 30 matching tables; callers may lower these caps. The configured dataset scan ceiling can further restrict work. Inspect tables_truncated and each match's rows_truncated; an empty matches list with truncation is not proof the value is absent.

Operation `search_tabular_values`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `person` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `run` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `agent` | query | string, max length 256 or null |  | Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. |
| `x-fred-document-context` | header | [`DocumentAccessContext`](#documentaccesscontext) (`application/json`) | yes | One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no documents. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. |

Request: [`TabularSearchRequest`](#tabularsearchrequest).

- 200: [`TabularSearchResponse`](#tabularsearchresponse) — Successful Response
- 400: [`KnowledgeFlowError`](#knowledgeflowerror) — Invalid JSON document context (invalid_document_context). Invalid tabular input, SQL, keyword, publication metadata, empty query/search selection, or configured dataset limit exceeded; detail explains the failure.
- 401: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing, invalid or expired bearer credentials. The caller must satisfy the existing workload delegation policy.
- 403: [`KnowledgeFlowError`](#knowledgeflowerror) — Missing document context (document_context_required), rejected delegation, account restriction, or represented person denied access to the space. A requested document/dataset is outside the authorized selection.
- 404: [`KnowledgeFlowError`](#knowledgeflowerror) — Space not found (space_not_found). Required published dataset/catalog missing (dataset_not_found).
- 409: [`KnowledgeFlowError`](#knowledgeflowerror) — Space pending deletion (space_pending_deletion).
- 422: [`HTTPValidationError`](#httpvalidationerror) — Business body, query or path validation failed; detail is an array of validation errors. Context-header validation uses 400/403 instead.
- 500: [`KnowledgeFlowError`](#knowledgeflowerror) — Unexpected server failure; detail is Internal server error. No internal credentials or exception trace are returned.
- 503: [`KnowledgeFlowError`](#knowledgeflowerror) — Account status could not be checked. This is an unavailable decision, not a permission grant. Tabular execution capacity or queue budget exhausted. Retry with bounded backoff; persistent refusal is not success.
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

Server-bound space and document selection, accepted only from an authenticated delegated caller. Never inferred from model arguments. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_scope` | [`DocumentScope`](#documentscope) | yes | Intersection of selection clauses. Zero clauses add no filter; one empty clause selects nothing. |
| `space_id` | string (uuid) | yes | Admitted turn's space UUID; KF checks the represented person's read permission. |

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
| `query_aliases` | array of string |  | Exact aliases of the mounted tables used by the query. |
| `rows` | array of object |  | JSON objects keyed by selected SQL columns; values depend on the query. Bounded preview, without a completeness flag. |
| `sql_query` | string | yes | Validated SQL before the server adds its outer result-row LIMIT. |

### SearchPolicyName

One of: `hybrid`, `strict`, `semantic`.

### SearchRequest

Search arguments; document authority comes from the authenticated header. Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `question` | string | yes | Natural-language search query. This operation returns chunks, not a generated answer. |
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

### TabularColumnSchema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dtype` | `string`, `integer`, `float`, `boolean`, `datetime`, `unknown` | yes |  |
| `has_two_values` | boolean or null |  | For string columns, whether exactly two distinct non-null values were observed. This does not assign true/false meaning to those values. |
| `is_categorical` | boolean or null |  | For string columns, whether the count of distinct non-null values is between 1 and max_categories(row_count), with null rows included in row_count. None for non-string or older columns without this analysis. |
| `max_value` | integer or number or null |  | Largest finite non-null value of an integer or float column. None when unavailable. |
| `min_value` | integer or number or null |  | Smallest finite non-null value of an integer or float column. None when unavailable. |
| `name` | string | yes |  |
| `sample_values` | array of string or null |  | Every distinct non-null string value when is_categorical is true, preserving exact casing for SQL filters. None otherwise. |

### TabularDocumentDescriptionResponse

Extraction catalog and full schemas for one authorized tabular document. Why this exists: - One batch call must return the workbook context before its typed tables, while CSV documents expose their typed table without a catalog. How to use: - Returned by `GET /tabular/documents/schemas` (one entry per requested document uid).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_name` | string | yes |  |
| `document_uid` | string | yes |  |
| `kind` | `csv`, `spreadsheet` | yes |  |
| `markdown` | string or null | yes |  |
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

Read-only SQL query request for authorized tabular datasets. Why this exists: - The new tabular runtime can query several document-scoped datasets at once. How to use: - Send `sql` and an optional `dataset_uids` subset. - Omit `dataset_uids` to make every readable dataset in the active tabular scope available to the query. Only the aliases the SQL actually references are mounted. The authorized inventory is still resolved. - The query must reference at least one dataset alias in its `FROM` clause; a query that reads no dataset (`SELECT 1`) is rejected with 400. - A query joining more datasets than the server's per-request limit is also rejected with 400 — split it or scope `dataset_uids`. - An explicit empty dataset list selects nothing. The trusted document scope is supplied by the runtime outside tool arguments. Example: ```python request = TabularQueryRequest( sql="SELECT city, COUNT(*) FROM d_doc_sales GROUP BY city", dataset_uids=["doc-sales"], max_rows=50, ) ``` Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dataset_uids` | array of string, max items 1000 or null |  | Optional document UUID subset, not table aliases. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook includes its tables. |
| `max_rows` | integer, >= 1.0 or null |  | Requested result-row limit; omitted/null uses configured default_max_rows. Clamped to configured max_rows, not rejected when larger. No pagination or truncation flag. |
| `sql` | string, min length 1 | yes | One read-only SELECT/WITH using exact aliases returned by schema discovery. Must reference an authorized dataset; SELECT 1, writes and external reads are refused. |

### TabularSearchRequest

Keyword value-locator request over authorized tabular datasets. Why this exists: - The catalog and schemas expose a workbook's structure but never its cell values, so a question about a value otherwise forces a blind table-by-table scan — one MCP/LLM round trip per table. This locates the value once, server-side. How to use: - Send a precise `keyword`; scope with `dataset_uids` when possible (one spreadsheet uid covers all its tables). Omit `dataset_uids` to search every readable dataset in the active scope. - `max_rows_per_table` and `max_matching_tables` are ceilings (module constants) — lower them, never raise them. Example: ```python request = TabularSearchRequest(keyword="ABC-123", dataset_uids=["doc-sales"]) ``` Additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dataset_uids` | array of string, max items 1000 or null |  | Optional document UUID subset, not table aliases. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook includes its tables. |
| `keyword` | string, min length 1 | yes | Precise value to locate. Schema minimum is 1 character; the service additionally requires at least 2 stripped characters (400) and a nonempty normalized keyword. Case/accent/whitespace-insensitive substring matching, including numeric columns. |
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
| `columns` | array of [`TabularColumnSchema`](#tabularcolumnschema) |  |  |
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
