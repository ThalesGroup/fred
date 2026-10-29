# Reference: control-plane REST API

Generated reference of every Control Plane operation and the JSON schemas it
exchanges, for Fred developers, integrators and coding assistants. The web UI and
machine clients, such as document-processing workers, use this same API. Read
[Security](03-security.md) for authentication and authorization, and the
[HTTP surface](A2-manager-contracts.md#control-plane-http-surface) for admission
rules and error semantics.

The source is the OpenAPI document built from the registrations that serve requests,
so the page cannot list a route the server does not expose. The machine-readable
contract is not versioned: `make -C apps/control-plane generate-openapi` writes it to
`apps/control-plane/openapi.json`, from which the frontend client is also generated.
Every operation requires a bearer token unless marked public, and every error
answers an `ErrorBody`.

Descriptions come from the `///` doc comments on handlers, parameters and types;
an operation or field without one shows no description. Regenerate with
`make -C docs/architecture generate`.

<!-- generated: openapi apps/control-plane/openapi.json -->
Paths are relative to `/control-plane/v1`.

Operations: [`/admin`](#admin-routes) · [`/agents`](#agents-routes) · [`/authorize`](#authorize-routes) · [`/bootstrap`](#bootstrap-routes) · [`/deletions`](#deletions-routes) · [`/document-processing`](#document-processing-routes) · [`/document-uploads`](#document-uploads-routes) · [`/documents`](#documents-routes) · [`/folders`](#folders-routes) · [`/frontend`](#frontend-routes) · [`/gcu`](#gcu-routes) · [`/healthz`](#healthz-routes) · [`/import-export`](#import-export-routes) · [`/me`](#me-routes) · [`/organizations`](#organizations-routes) · [`/spaces`](#spaces-routes) · [`/users`](#users-routes). [Schemas](#schemas).

## /admin routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/admin/organizations](#get-adminorganizations) |  |
| POST | [/admin/organizations](#post-adminorganizations) |  |
| GET | [/admin/organizations/candidates](#get-adminorganizationscandidates) |  |
| GET | [/admin/teams](#get-adminteams) |  |

### GET /admin/organizations

Operation `organization_registry`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `after` | query | string (uuid) |  | Exclusive UUID cursor; at most 100 active organizations. |

- 200: [`OrganizationPage`](#organizationpage)
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 500: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /admin/organizations

Operation `create_organization`.

Request: [`CreateOrganization`](#createorganization).

- 201: [`Space`](#space)
- 400, 401, 403, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /admin/organizations/candidates

Operation `search_organization_candidates`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `query` | query | string, min length 2 | yes |  |

- 200: array of [`UserSummary`](#usersummary)
- 400, 401, 403, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /admin/teams

Operation `team_registry`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `after` | query | string (uuid) |  | Exclusive UUID cursor; at most 100 non-personal teams, ordered by ID. |

- 200: array of [`Space`](#space) — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 500: [`ErrorBody`](#errorbody) — Request failed
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

## /agents routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/agents/execute/stream](#post-agentsexecutestream) | Direct-template hello-world execution; no managed instance or business data access |

### POST /agents/execute/stream

Direct-template hello-world execution; no managed instance or business data access.

Operation `execute_stream`.

Request: [`ExecuteRequest`](#executerequest).

- 200: [`RuntimeEvent`](#runtimeevent) (`text/event-stream`) — SSE data frames containing RuntimeEvent JSON; final closes the stream without a sentinel
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 422, 501: [`ErrorBody`](#errorbody)

## /authorize routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/authorize/document](#post-authorizedocument) |  |
| POST | [/authorize/platform](#post-authorizeplatform) |  |
| POST | [/authorize/scope](#post-authorizescope) |  |
| POST | [/authorize/space](#post-authorizespace) |  |

### POST /authorize/document

Operation `authorize_document`.

Request: [`AuthorizeDocument`](#authorizedocument).

- 200: [`Allowed`](#allowed) — Success
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 422, 500: [`ErrorBody`](#errorbody) — Request failed
- 409: [`ErrorBody`](#errorbody) — Ambiguous organization context

### POST /authorize/platform

Operation `authorize_platform`.

Request: [`PlatformCheck`](#platformcheck).

- 200: [`Allowed`](#allowed) — Success
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 422, 500: [`ErrorBody`](#errorbody) — Request failed

### POST /authorize/scope

Operation `authorize_scope`.

Request: [`AuthorizeScope`](#authorizescope).

- 200: [`Scope`](#scope) — Success
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 422, 500: [`ErrorBody`](#errorbody) — Request failed
- 409: [`ErrorBody`](#errorbody) — Ambiguous organization context

### POST /authorize/space

Operation `authorize_space`.

Request: [`SpaceCheck`](#spacecheck).

- 200: [`Allowed`](#allowed) — Success
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 422, 500: [`ErrorBody`](#errorbody) — Request failed
- 409: [`ErrorBody`](#errorbody) — Ambiguous organization context

## /bootstrap routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/bootstrap/platform-admin](#post-bootstrapplatform-admin) | Same contract as the control-plane's `POST /bootstrap/platform-admin`: the caller's own verified bearer plus the deploy-time secret, granting platform owner to the caller only, once ever |

### POST /bootstrap/platform-admin

Same contract as the control-plane's `POST /bootstrap/platform-admin`: the caller's own verified bearer plus the deploy-time secret, granting platform owner to the caller only, once ever.

Operation `bootstrap_platform_admin`.

Request: [`BootstrapRequest`](#bootstraprequest).

- 200: [`BootstrapResponse`](#bootstrapresponse) — Success
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 409, 422, 500, 503: [`ErrorBody`](#errorbody) — Request failed

## /deletions routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/deletions/{operation_id}](#get-deletionsoperation_id) |  |

### GET /deletions/{operation_id}

Operation `deletion_status`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `operation_id` | path | string (uuid) | yes |  |

- 200: [`Receipt`](#receipt)
- 401, 403, 404, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

## /document-processing routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/document-processing/cleanup](#get-document-processingcleanup) |  |
| POST | [/document-processing/cleanup](#post-document-processingcleanup) |  |
| GET | [/document-processing/retrievable/{id}](#get-document-processingretrievableid) |  |
| POST | [/document-processing/retrievable/{id}](#post-document-processingretrievableid) |  |
| POST | [/document-processing/{id}/abandon](#post-document-processingidabandon) |  |
| POST | [/document-processing/{id}/claim](#post-document-processingidclaim) |  |
| POST | [/document-processing/{id}/commit](#post-document-processingidcommit) |  |
| GET | [/document-processing/{id}/original](#get-document-processingidoriginal) |  |
| POST | [/document-processing/{id}/vectors](#post-document-processingidvectors) |  |
| GET | [/document-processing/{id}/work](#get-document-processingidwork) |  |

### GET /document-processing/cleanup

Operation `cleanup`.

- 200: array of [`Cleanup`](#cleanup)
- 401, 403, 404, 503: [`ErrorBody`](#errorbody)

### POST /document-processing/cleanup

Operation `cleaned`.

Request: [`Cleaned`](#cleaned).

- 200: no body
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### GET /document-processing/retrievable/{id}

Operation `retrieval_work`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `operation_id` | query | string (uuid) | yes |  |

- 200: [`RetrievalWork`](#retrievalwork)
- 401, 403, 404, 409, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /document-processing/retrievable/{id}

Operation `confirm_retrievable`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`RetrievalConfirmation`](#retrievalconfirmation).

- 200: no body
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### POST /document-processing/{id}/abandon

Operation `abandon`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`Failure`](#failure).

- 200: [`Summary`](#summary)
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### POST /document-processing/{id}/claim

Operation `claim`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`Claim`](#claim).

- 200: [`Descriptor`](#descriptor)
- 400, 401, 403, 404, 409, 422, 429, 503: [`ErrorBody`](#errorbody)

### POST /document-processing/{id}/commit

Operation `commit`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`Commit`](#commit).

- 200: [`Summary`](#summary)
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### GET /document-processing/{id}/original

Operation `original`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `generation` | query | string (uuid) | yes |  |

- 200: string (`application/octet-stream`)
- 401, 403, 404, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /document-processing/{id}/vectors

Operation `vectors`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`VectorPlan`](#vectorplan).

- 200: no body
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### GET /document-processing/{id}/work

Operation `work`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 200: [`Work`](#work)
- 401, 403, 404, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

## /document-uploads routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/document-uploads/{id}](#get-document-uploadsid) | One of the caller's upload receipts, with its latest processing attempt; poll it to follow an upload |
| PUT | [/document-uploads/{id}/acknowledgment](#put-document-uploadsidacknowledgment) | Dismiss a terminal receipt from the caller's list; repeating it is harmless |

### GET /document-uploads/{id}

One of the caller's upload receipts, with its latest processing attempt; poll it to follow an upload.

Operation `receipt`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes | The upload's `Idempotency-Key` |

- 200: [`UploadReceipt`](#uploadreceipt)
- 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### PUT /document-uploads/{id}/acknowledgment

Dismiss a terminal receipt from the caller's list; repeating it is harmless. The receipt stays readable by key, so replaying its upload remains safe.

Operation `acknowledge`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes | The upload's `Idempotency-Key` |

- 204: no body
- 401, 403, 404, 422, 503: [`ErrorBody`](#errorbody)
- 409: [`ErrorBody`](#errorbody) — `upload_in_progress` while pending, `processing_active` while its document is processing

## /documents routes

| Method | Path | Summary |
| --- | --- | --- |
| DELETE | [/documents/{id}](#delete-documentsid) |  |
| GET | [/documents/{id}/content](#get-documentsidcontent) | Originals are attachments; no conversion or ingestion is triggered by this route |
| GET | [/documents/{id}/preview](#get-documentsidpreview) |  |
| GET | [/documents/{id}/processing](#get-documentsidprocessing) | The document's processing attempts, newest first, 50 per page |
| POST | [/documents/{id}/processing](#post-documentsidprocessing) | Process a stored document for the first time, or retry its failed attempt |
| PUT | [/documents/{id}/retrievable](#put-documentsidretrievable) |  |

### DELETE /documents/{id}

Operation `delete_document`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 200, 202: [`Receipt`](#receipt)
- 401, 403, 404, 409, 422, 429, 503: [`ErrorBody`](#errorbody)

### GET /documents/{id}/content

Originals are attachments; no conversion or ingestion is triggered by this route.

Operation `content`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 200: string (`application/octet-stream`)
- 401, 403, 404, 409, 422, 429, 503: [`ErrorBody`](#errorbody)

### GET /documents/{id}/preview

Operation `preview`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `artifact` | query | string |  | native, raw, metadata, or a relative path from the published manifest. |

- 200, 206: string (`text/plain`)
- 401, 403, 404, 409, 416, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /documents/{id}/processing

The document's processing attempts, newest first, 50 per page.

Operation `history`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `before` | query | string (uuid) or null |  | Cursor: `id` of the last attempt read. |

- 200: array of [`Summary`](#summary)
- 401, 403, 404, 409, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /documents/{id}/processing

Process a stored document for the first time, or retry its failed attempt. A document has at most one active or succeeded attempt; replaying `Idempotency-Key` returns it.

Operation `start`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes | Stored document |
| `Idempotency-Key` | header | string (uuid) | yes | Caller-chosen request UUID; replaying it is safe |

Request: [`Start`](#start).

- 200: [`Summary`](#summary)
- 400, 401, 403, 404, 422: [`ErrorBody`](#errorbody)
- 409: [`ErrorBody`](#errorbody) — `processing_exists` (active or succeeded attempt), `retry_required` (set `retry_of`), `invalid_retry`, `retry_superseded` or `idempotency_conflict`
- 429: [`ErrorBody`](#errorbody) — `processing_capacity`: too many pending attempts; honour `Retry-After`
- 503: [`ErrorBody`](#errorbody) — `processing_unavailable`

### PUT /documents/{id}/retrievable

Operation `set_retrievable`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`SetRetrievable`](#setretrievable).

- 200: [`Document`](#document)
- 400, 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

## /folders routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/folders](#post-folders) |  |
| PATCH | [/folders/{id}](#patch-foldersid) |  |
| DELETE | [/folders/{id}](#delete-foldersid) |  |
| POST | [/folders/{id}/documents](#post-foldersiddocuments) | Store one file as an immutable original; with `profile`, also request its processing atomically |
| POST | [/folders/{id}/documents/preflight](#post-foldersiddocumentspreflight) | Advisory check before uploading: names already taken in the folder and the current quota |

### POST /folders

Operation `create_folder`.

Request: [`CreateFolder`](#createfolder).

- 201: [`Folder`](#folder) — Success
- 400, 401, 403, 404, 409, 422, 500: [`ErrorBody`](#errorbody) — Request failed

### PATCH /folders/{id}

Operation `rename_folder`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

Request: [`Rename`](#rename).

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 404, 409, 422, 500: [`ErrorBody`](#errorbody) — Request failed

### DELETE /folders/{id}

Operation `delete_folder`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 404, 409, 500: [`ErrorBody`](#errorbody) — Request failed
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /folders/{id}/documents

Store one file as an immutable original; with `profile`, also request its processing atomically. `Location` names the receipt; replaying a stored `Idempotency-Key` answers 200 with the same receipt.

Operation `upload`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes | Destination folder |
| `Idempotency-Key` | header | string (uuid) | yes | Caller-chosen request UUID; replaying it is safe |
| `retry_of` | query | string (uuid) |  | Request key of a failed upload of the same file to the same folder |
| `profile` | query | [`Profile`](#profile) |  | Processing profile; omit to store only |

Request: [`FileUpload`](#fileupload) (`multipart/form-data`).

- 200: [`UploadReceipt`](#uploadreceipt) — Replay of a stored request key
- 201: [`UploadReceipt`](#uploadreceipt) — Stored
- 400: [`ErrorBody`](#errorbody) — `invalid_multipart`: not one multipart `file` part
- 401: [`ErrorBody`](#errorbody) — Missing token, or `token_expired` during the transfer
- 403, 404: [`ErrorBody`](#errorbody)
- 408: [`ErrorBody`](#errorbody) — `upload_timeout`: the transfer stalled or exceeded its deadline
- 409: [`ErrorBody`](#errorbody) — `name_conflict`, `idempotency_conflict`, `upload_failed` (retry with `retry_of`), `invalid_retry`, `upload_expired`, `retry_superseded` (`Location` names the original receipt), or `upload_in_progress` (`Location` and `Retry-After`)
- 413: [`ErrorBody`](#errorbody) — `file_too_large`: above `max_file_bytes`
- 422: [`ErrorBody`](#errorbody) — `quota_exceeded`, or an invalid request key, filename or media type
- 429: [`ErrorBody`](#errorbody) — `transfer_capacity`: all transfer slots are busy; honour `Retry-After`
- 503: [`ErrorBody`](#errorbody) — `storage_unavailable`, or `processing_unavailable` when a profile is requested

### POST /folders/{id}/documents/preflight

Advisory check before uploading: names already taken in the folder and the current quota. The upload decides; a name free here can still conflict when the file arrives.

Operation `preflight`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes | Destination folder |

Request: [`Preflight`](#preflight).

- 200: [`PreflightResult`](#preflightresult)
- 400, 401, 403, 404, 409, 503: [`ErrorBody`](#errorbody)
- 413: [`ErrorBody`](#errorbody) — `file_too_large`: a file is above `max_file_bytes`
- 422: [`ErrorBody`](#errorbody) — Not 1..200 files, or an invalid filename

## /frontend routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/frontend/config](#get-frontendconfig) |  |

### GET /frontend/config

Operation `frontend_config` · public, no bearer token.

- 200: [`FrontendConfig`](#frontendconfig)
- 500: [`ErrorBody`](#errorbody)

## /gcu routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/gcu](#post-gcu) |  |

### POST /gcu

Operation `accept_terms`.

Request: [`TermsRequest`](#termsrequest).

- 204: no body — Accepted
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 409, 422, 500: [`ErrorBody`](#errorbody)

## /healthz routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/healthz](#get-healthz) |  |

### GET /healthz

Operation `health` · public, no bearer token.

- 200: [`Health`](#health)

## /import-export routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/import-export/import](#post-import-exportimport) | Authenticate and check platform authority before constructing the body extractor |

### POST /import-export/import

Authenticate and check platform authority before constructing the body extractor. Only the ZIP's file bytes are parsed, and all parsing precedes provisioning.

Operation `import_blueprint`.

Request: [`ProvisioningUpload`](#provisioningupload) (`multipart/form-data`).

- 200: [`Report`](#report) — Success
- 400, 401, 403, 409, 413, 422, 500, 503: [`ErrorBody`](#errorbody) — Request failed

## /me routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/me](#get-me) |  |
| GET | [/me/onboarding](#get-meonboarding) |  |
| POST | [/me/personal-space](#post-mepersonal-space) |  |
| GET | [/me/spaces](#get-mespaces) |  |

### GET /me

Operation `me`.

- 200: [`Me`](#me) — Success
- 401, 403, 500: [`ErrorBody`](#errorbody) — Request failed

### GET /me/onboarding

Operation `onboarding_status`.

- 200: [`OnboardingStatus`](#onboardingstatus)
- 401, 403, 500: [`ErrorBody`](#errorbody)

### POST /me/personal-space

Operation `create_personal_space`.

Request: [`CreatePersonalSpace`](#createpersonalspace).

- 200: [`Space`](#space) — Existing personal space
- 201: [`Space`](#space) — Created personal space
- 400, 401, 403, 404, 409, 422, 500: [`ErrorBody`](#errorbody) — Request failed

### GET /me/spaces

Operation `my_spaces`.

- 200: array of [`MySpace`](#myspace) — Success
- 401, 403, 500: [`ErrorBody`](#errorbody) — Request failed
- 409: [`ErrorBody`](#errorbody) — Ambiguous organization context, or a space role without its parent membership

## /organizations routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/organizations/{organization_id}/agents](#get-organizationsorganization_idagents) |  |
| PUT | [/organizations/{organization_id}/agents/{agent_id}/default-on](#put-organizationsorganization_idagentsagent_iddefault-on) |  |
| GET | [/organizations/{organization_id}/capabilities](#get-organizationsorganization_idcapabilities) |  |
| POST | [/organizations/{organization_id}/capabilities/{runtime_id}/refresh](#post-organizationsorganization_idcapabilitiesruntime_idrefresh) |  |
| PUT | [/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/default-on](#put-organizationsorganization_idcapabilitiesruntime_idcapability_iddefault-on) |  |
| GET | [/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/revoke-impact](#get-organizationsorganization_idcapabilitiesruntime_idcapability_idrevoke-impact) |  |
| GET | [/organizations/{organization_id}/model-policy](#get-organizationsorganization_idmodel-policy) |  |
| PUT | [/organizations/{organization_id}/model-policy](#put-organizationsorganization_idmodel-policy) |  |
| POST | [/organizations/{organization_id}/model-sources/{source_id}/refresh](#post-organizationsorganization_idmodel-sourcessource_idrefresh) |  |
| GET | [/organizations/{organization_id}/models](#get-organizationsorganization_idmodels) |  |
| GET | [/organizations/{organization_id}/supervision](#get-organizationsorganization_idsupervision) |  |
| GET | [/organizations/{organization_id}/supervision/teams/{team_id}](#get-organizationsorganization_idsupervisionteamsteam_id) |  |

### GET /organizations/{organization_id}/agents

Operation `organization_agents`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |

- 200: array of [`AgentEnablement`](#agentenablement)
- 401, 403, 404, 409, 500: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### PUT /organizations/{organization_id}/agents/{agent_id}/default-on

Operation `set_organization_agent_default`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `agent_id` | path | string (uuid) | yes |  |

Request: [`SetDefaultOnRequest`](#setdefaultonrequest).

- 200: [`AgentDefaultOnResult`](#agentdefaultonresult)
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /organizations/{organization_id}/capabilities

Operation `organization_capabilities`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |

- 200: array of [`PodCapabilityInventory`](#podcapabilityinventory)
- 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### POST /organizations/{organization_id}/capabilities/{runtime_id}/refresh

Operation `refresh_organization_capabilities`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `runtime_id` | path | string | yes |  |

- 204: no body — Complete pod inventory persisted; read the catalog for observation and offers
- 401, 403, 404, 409, 500, 502, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### PUT /organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/default-on

Operation `set_organization_capability_default`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `runtime_id` | path | string | yes |  |
| `capability_id` | path | string | yes |  |

Request: [`SetDefaultOnRequest`](#setdefaultonrequest).

- 204: no body — Organization decision stored
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 500, 503: [`ErrorBody`](#errorbody)
- 404: [`ErrorBody`](#errorbody) — Unknown organization, pod source or offer
- 409: [`ErrorBody`](#errorbody) — Enabling an offer the pod no longer advertises
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/revoke-impact

Operation `organization_capability_revoke_impact`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `runtime_id` | path | string | yes |  |
| `capability_id` | path | string | yes |  |

- 200: array of [`AffectedAgentInstance`](#affectedagentinstance) — Instances usable now that disabling this offer would stop
- 401, 403, 500, 503: [`ErrorBody`](#errorbody)
- 404: [`ErrorBody`](#errorbody) — Unknown organization, pod source or offer
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /organizations/{organization_id}/model-policy

Operation `organization_model_policy`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |

- 200: [`OrganizationModelPolicy`](#organizationmodelpolicy)
- 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### PUT /organizations/{organization_id}/model-policy

Operation `replace_organization_model_policy`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |

Request: [`ReplaceModelPolicy`](#replacemodelpolicy).

- 200: [`OrganizationModelPolicy`](#organizationmodelpolicy)
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 404, 500, 503: [`ErrorBody`](#errorbody)
- 409: [`ErrorBody`](#errorbody) — Policy revision conflict or newly selected offer not selectable
- 422: [`ErrorBody`](#errorbody) — Invalid policy or unknown offer

### POST /organizations/{organization_id}/model-sources/{source_id}/refresh

Operation `refresh_model_source`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `source_id` | path | string | yes |  |

- 204: no body — Complete source inventory published; read models for observations
- 401, 403, 404, 500, 503: [`ErrorBody`](#errorbody)
- 409: [`ErrorBody`](#errorbody) — Disabled, obsolete or superseded source refresh
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields
- 502: [`ErrorBody`](#errorbody) — Invalid or incomplete discovery; last success preserved

### GET /organizations/{organization_id}/models

Operation `organization_models`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |

- 200: [`OrganizationModelInventory`](#organizationmodelinventory)
- 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /organizations/{organization_id}/supervision

Operation `organization_supervision`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `after` | query | string (uuid) |  | Exclusive team UUID cursor; does not filter organization totals |

- 200: [`OrganizationSupervision`](#organizationsupervision)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /organizations/{organization_id}/supervision/teams/{team_id}

Operation `team_supervision`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `organization_id` | path | string (uuid) | yes |  |
| `team_id` | path | string (uuid) | yes |  |

- 200: [`TeamSupervisionDetail`](#teamsupervisiondetail)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

## /spaces routes

| Method | Path | Summary |
| --- | --- | --- |
| POST | [/spaces](#post-spaces) |  |
| DELETE | [/spaces/{id}](#delete-spacesid) |  |
| GET | [/spaces/{id}/document-uploads](#get-spacesiddocument-uploads) | The caller's upload receipts in the space, newest first, each with its latest processing attempt |
| GET | [/spaces/{id}/entries](#get-spacesidentries) |  |
| PUT | [/spaces/{id}/roles/{role}/{user}](#put-spacesidrolesroleuser) |  |
| DELETE | [/spaces/{id}/roles/{role}/{user}](#delete-spacesidrolesroleuser) |  |
| GET | [/spaces/{id}/storage](#get-spacesidstorage) |  |
| GET | [/spaces/{space_id}/agent-instances](#get-spacesspace_idagent-instances) |  |
| POST | [/spaces/{space_id}/agent-instances](#post-spacesspace_idagent-instances) |  |
| GET | [/spaces/{space_id}/agent-instances/{agent_instance_id}](#get-spacesspace_idagent-instancesagent_instance_id) |  |
| PATCH | [/spaces/{space_id}/agent-instances/{agent_instance_id}](#patch-spacesspace_idagent-instancesagent_instance_id) |  |
| DELETE | [/spaces/{space_id}/agent-instances/{agent_instance_id}](#delete-spacesspace_idagent-instancesagent_instance_id) |  |
| POST | [/spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution](#post-spacesspace_idagent-instancesagent_instance_idprepare-execution) |  |
| GET | [/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime](#get-spacesspace_idagent-instancesagent_instance_idruntime) |  |
| GET | [/spaces/{space_id}/agent-templates](#get-spacesspace_idagent-templates) |  |
| GET | [/spaces/{space_id}/sessions](#get-spacesspace_idsessions) |  |
| POST | [/spaces/{space_id}/sessions](#post-spacesspace_idsessions) |  |
| GET | [/spaces/{space_id}/sessions/{session_id}](#get-spacesspace_idsessionssession_id) |  |
| PATCH | [/spaces/{space_id}/sessions/{session_id}](#patch-spacesspace_idsessionssession_id) |  |
| DELETE | [/spaces/{space_id}/sessions/{session_id}](#delete-spacesspace_idsessionssession_id) |  |

### POST /spaces

Operation `create_space`.

Request: [`CreateSpace`](#createspace).

- 201: [`Space`](#space) — Success
- 400, 401, 403, 404, 409, 422, 500: [`ErrorBody`](#errorbody) — Request failed

### DELETE /spaces/{id}

Operation `delete_space`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 200: [`Receipt`](#receipt) — Already completed
- 202: [`Receipt`](#receipt) — Durably accepted
- 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /spaces/{id}/document-uploads

The caller's upload receipts in the space, newest first, each with its latest processing attempt. Superseded receipts are omitted; acknowledged ones too, unless their document is still processing.

Operation `receipts`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `before` | query | string (date-time) |  | Cursor: `created_at` of the last receipt read; requires `before_key` |
| `before_key` | query | string (uuid) |  | Cursor: `request_key` of the last receipt read |
| `limit` | query | integer (int64) |  | 1..200, default 50 |

- 200: array of [`UploadReceipt`](#uploadreceipt)
- 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### GET /spaces/{id}/entries

Operation `entries`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `parent_id` | query | string (uuid) |  |  |
| `search` | query | string |  | Literal case-insensitive substring; at most 255 characters. |
| `order` | query | [`EntryOrder`](#entryorder) |  |  |
| `offset` | query | integer (int64) |  |  |
| `limit` | query | integer (int64) |  |  |

- 200: [`Directory`](#directory)
- 401, 403, 404, 409, 422, 503: [`ErrorBody`](#errorbody)

### PUT /spaces/{id}/roles/{role}/{user}

Operation `grant`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `role` | path | [`Role`](#role) | yes |  |
| `user` | path | string | yes |  |

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 404, 409, 500: [`ErrorBody`](#errorbody) — Request failed
- 422: [`ErrorBody`](#errorbody) — Malformed subject, or not a known identity of the user directory
- 503: [`ErrorBody`](#errorbody) — User directory unavailable

### DELETE /spaces/{id}/roles/{role}/{user}

Operation `revoke`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |
| `role` | path | [`Role`](#role) | yes |  |
| `user` | path | string | yes |  |

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 404, 409, 500: [`ErrorBody`](#errorbody) — Request failed
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /spaces/{id}/storage

Operation `summary`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `id` | path | string (uuid) | yes |  |

- 200: [`StorageSummary`](#storagesummary)
- 401, 403, 404, 409, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /spaces/{space_id}/agent-instances

Operation `list_agent_instances`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |

- 200: array of [`ManagedAgentInstanceSummary`](#managedagentinstancesummary)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### POST /spaces/{space_id}/agent-instances

Operation `create_agent_instance`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |

Request: [`CreateAgentInstanceRequest`](#createagentinstancerequest).

- 201: [`ManagedAgentInstanceSummary`](#managedagentinstancesummary)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /spaces/{space_id}/agent-instances/{agent_instance_id}

Operation `get_agent_instance`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `agent_instance_id` | path | string (uuid) | yes |  |

- 200: [`ManagedAgentInstanceSummary`](#managedagentinstancesummary)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### PATCH /spaces/{space_id}/agent-instances/{agent_instance_id}

Operation `update_agent_instance`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `agent_instance_id` | path | string (uuid) | yes |  |

Request: [`UpdateAgentInstanceRequest`](#updateagentinstancerequest).

- 200: [`ManagedAgentInstanceSummary`](#managedagentinstancesummary)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### DELETE /spaces/{space_id}/agent-instances/{agent_instance_id}

Operation `delete_agent_instance`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `agent_instance_id` | path | string (uuid) | yes |  |

- 204: no body — Agent instance deleted
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### POST /spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution

Operation `prepare_execution`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `agent_instance_id` | path | string (uuid) | yes |  |
| `session_id` | query | string |  | Registered conversation to verify before routing. |
| `model_source_id` | query | string |  | Requested model source; supply together with model_upstream_id. |
| `model_upstream_id` | query | string |  | Requested upstream model; never an authorization. |

- 200: [`ExecutionPreparation`](#executionpreparation)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /spaces/{space_id}/agent-instances/{agent_instance_id}/runtime

Operation `resolve_runtime`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `agent_instance_id` | path | string (uuid) | yes |  |
| `person` | query | string |  | Canonical person; only a trusted delegated call may supply this assertion. |
| `run` | query | string |  | Run identifier; required together with person and agent. |
| `agent` | query | string |  | Delegated agent instance UUID; must match agent_instance_id. |
| `conversation` | query | string |  | Registered conversation; this resolver checks its private canonical association, then the pod checks checkpoint provenance before loading history. |

- 200: [`RuntimeBinding`](#runtimebinding)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /spaces/{space_id}/agent-templates

Operation `space_agent_templates`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |

- 200: array of [`AgentTemplateSummary`](#agenttemplatesummary)
- 400, 401, 403, 404, 409, 500, 503: [`ErrorBody`](#errorbody)
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

### GET /spaces/{space_id}/sessions

Operation `list_sessions`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |

- 200: array of [`SessionDetails`](#sessiondetails)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### POST /spaces/{space_id}/sessions

Operation `create_session`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |

Request: [`CreateSessionRequest`](#createsessionrequest).

- 200, 201: [`SessionDetails`](#sessiondetails)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### GET /spaces/{space_id}/sessions/{session_id}

Operation `get_session`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `session_id` | path | string (uuid) | yes |  |

- 200: [`SessionDetails`](#sessiondetails)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### PATCH /spaces/{space_id}/sessions/{session_id}

Operation `update_session`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `session_id` | path | string (uuid) | yes |  |

Request: [`UpdateSessionRequest`](#updatesessionrequest).

- 200: [`SessionDetails`](#sessiondetails)
- 400, 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

### DELETE /spaces/{space_id}/sessions/{session_id}

Operation `delete_session`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `space_id` | path | string (uuid) | yes |  |
| `session_id` | path | string (uuid) | yes |  |

- 200, 202: [`Receipt`](#receipt)
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody)

## /users routes

| Method | Path | Summary |
| --- | --- | --- |
| GET | [/users/me/preferences](#get-usersmepreferences) |  |
| PATCH | [/users/me/preferences](#patch-usersmepreferences) |  |
| GET | [/users/platform-roles](#get-usersplatform-roles) |  |
| PUT | [/users/{user}/platform-roles/{role}](#put-usersuserplatform-rolesrole) |  |
| DELETE | [/users/{user}/platform-roles/{role}](#delete-usersuserplatform-rolesrole) |  |

### GET /users/me/preferences

Operation `get_my_preferences`.

- 200: [`UserPreferences`](#userpreferences)
- 401, 403, 500: [`ErrorBody`](#errorbody)

### PATCH /users/me/preferences

Operation `patch_my_preferences`.

Request: [`PatchUserPreferences`](#patchuserpreferences).

- 200: [`UserPreferences`](#userpreferences)
- 400: [`ErrorBody`](#errorbody) — Malformed JSON body
- 401, 403, 422, 500: [`ErrorBody`](#errorbody)

### GET /users/platform-roles

Operation `list_platform_roles`.

- 200: array of [`Grant`](#grant) — Success
- 401, 403, 500, 503: [`ErrorBody`](#errorbody) — Request failed

### PUT /users/{user}/platform-roles/{role}

Operation `grant_platform_role`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `user` | path | string | yes |  |
| `role` | path | [`PlatformRole`](#platformrole) | yes |  |

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 404, 409, 422, 500, 503: [`ErrorBody`](#errorbody) — Request failed

### DELETE /users/{user}/platform-roles/{role}

Operation `revoke_platform_role`.

| Parameter | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `user` | path | string | yes |  |
| `role` | path | [`PlatformRole`](#platformrole) | yes |  |

- 204: no body — Success
- 400: [`ErrorBody`](#errorbody) — Invalid application request
- 401, 403, 409, 500, 503: [`ErrorBody`](#errorbody) — Request failed
- 404: [`ErrorBody`](#errorbody) — Direct grant not found
- 422: [`ErrorBody`](#errorbody) — Invalid path, query or body fields

## Schemas

### Acceptance

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `accepted_at` | string (date-time) | yes |  |
| `version` | string | yes |  |

### AffectedAgentInstance

An agent instance an offer's authorization affects, with its space for display.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_instance_id` | string (uuid) | yes |  |
| `display_name` | string | yes |  |
| `owner_name` | string or null | yes | Display name of a personal space's owner; null for other spaces. |
| `space_id` | string (uuid) | yes |  |
| `space_kind` | [`SpaceKind`](#spacekind) | yes |  |
| `space_name` | string | yes |  |

### AgentCapabilityKind

One of: `agent`.

### AgentDefaultOnResult

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capability_id` | string (uuid) | yes |  |
| `default_on` | boolean | yes |  |

### AgentEnablement

The existing admin row's identity and organization default, without invented instance health.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default_capability_ids` | array of string | yes |  |
| `default_on` | boolean | yes |  |
| `description` | string | yes |  |
| `icon` | string | yes |  |
| `id` | string (uuid) | yes |  |
| `kind` | [`AgentCapabilityKind`](#agentcapabilitykind) | yes |  |
| `name` | string | yes |  |
| `public_version` | string or null |  |  |
| `runtime_id` | string | yes |  |
| `source_id` | string | yes |  |
| `team_scope` | [`AgentScopePolicy`](#agentscopepolicy) | yes |  |
| `version` | string | yes |  |

### AgentInstanceStatus

One of: `enabled`, `disabled`.

### AgentScopePolicy

One of: `admin_gated`.

### AgentSort

One of: `name`, `created_at:desc`, `updated_at:desc`.

### AgentTemplateStatus

One of: `available`.

### AgentTemplateSummary

Form-facing projection of a permitted runtime template, not execution readiness.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `available_capabilities` | array of map of any | yes | Pod-owned descriptors, including config fields, schemas and routing metadata. |
| `capabilities` | array of string | yes |  |
| `category` | string | yes |  |
| `default_capability_ids` | array of string | yes |  |
| `default_tuning_fields` | array of map of any | yes | Pod-owned FieldSpecs, including localized defaults and UI hints, unchanged. |
| `description` | string | yes |  |
| `description_by_lang` | map of string or null |  |  |
| `display_name` | string | yes |  |
| `max_chat_input_chars` | integer (int64), >= 0 or null |  | Current pod input limit, absent when not advertised. |
| `public_version` | string or null |  |  |
| `source_agent_id` | string | yes |  |
| `source_runtime_id` | string | yes |  |
| `status` | [`AgentTemplateStatus`](#agenttemplatestatus) | yes |  |
| `supports_capabilities` | boolean | yes |  |
| `tags` | array of string | yes |  |
| `team_instantiable` | boolean | yes |  |
| `template_id` | string (uuid) | yes |  |

### Allowed

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `allowed` | boolean | yes |  |

### Artifact

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | string | yes |  |
| `sha256` | string | yes |  |
| `size` | integer (int64) | yes |  |

### AuthorizeDocument

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `document_id` | string (uuid) | yes |  |
| `permission` | [`Permission`](#permission) | yes |  |

### AuthorizeScope

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `levels` | array of [`SpaceKind`](#spacekind) or null |  | Keep only spaces of these kinds; omitted keeps every level. Never adds a space. |
| `space_id` | string (uuid) | yes |  |

### BootstrapRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `token` | string | yes |  |

### BootstrapResponse

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `user_id` | string | yes |  |
| `username` | string | yes |  |

### Candidate

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Filename as it will be uploaded. |
| `size` | integer (int64), >= 0 | yes | Size in bytes. |

### CapabilityExecutionModel

One of: `react`, `graph`.

### CapabilityFieldDescription

Public declaration only. Values, endpoints, schemas and arbitrary metadata are excluded.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `description` | string or null |  |  |
| `description_by_lang` | map of string |  |  |
| `item_type` | [`CapabilityFieldType`](#capabilityfieldtype) or null |  |  |
| `key` | string | yes |  |
| `max` | number (double) or null |  |  |
| `min` | number (double) or null |  |  |
| `required` | boolean |  |  |
| `scope_private` | boolean or null |  |  |
| `title` | string | yes |  |
| `type` | [`CapabilityFieldType`](#capabilityfieldtype) | yes |  |

### CapabilityFieldType

One of: `string`, `text`, `text-multiline`, `number`, `integer`, `boolean`, `select`, `array`, `object`, `prompt`, `secret`, `url`.

### CapabilityInventoryOffer

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `advertised` | boolean | yes | Present in the last successful snapshot; independent of observation state. |
| `capability_id` | string | yes |  |
| `default_on` | boolean | yes | Enabled for every space of this organization. |
| `descriptor` | [`PodCapabilityDescriptor`](#podcapabilitydescriptor) | yes |  |
| `runtime_id` | string | yes |  |
| `unusable_instances` | array of [`AffectedAgentInstance`](#affectedagentinstance) | yes | Instances that select this offer and may no longer use it. |
| `version` | string | yes |  |

### CatalogObservationState

One of: `not_observed`, `observed`, `unavailable`.

### ChatControlDescriptor

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capability_id` | string | yes |  |
| `params` | map of any or null |  |  |
| `widget` | string | yes |  |

### ChatProvenance

One of: `source_guarantee`, `api_metadata`.

### Claim

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `activity_id` | string (uuid) | yes |  |
| `attempt` | integer (int32), >= 0 | yes |  |
| `execution_id` | string (uuid) | yes |  |
| `stage` | [`Stage`](#stage) | yes |  |
| `work` | [`Work`](#work) | yes |  |

### Cleaned

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cursor` | integer (int32), >= 0 | yes |  |
| `generation` | string (uuid) | yes |  |
| `next_cursor` | integer (int32), >= 0 | yes |  |
| `objects_empty` | boolean | yes |  |
| `purge_document` | boolean |  |  |
| `work` | [`Work`](#work) | yes |  |

### Cleanup

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `batch` | integer (int32), >= 0 | yes |  |
| `chunks` | integer (int32), >= 0 | yes |  |
| `cursor` | integer (int32), >= 0 | yes |  |
| `generation` | string (uuid) | yes |  |
| `output_prefix` | string | yes |  |
| `preserve_objects` | boolean | yes |  |
| `protected_ordinals` | array of integer (int32), >= 0 | yes |  |
| `purge_document` | boolean | yes |  |
| `work` | [`Work`](#work) | yes |  |

### Commit

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `manifest` | [`Manifest`](#manifest) | yes |  |
| `stage` | [`Stage`](#stage) | yes |  |
| `work` | [`Work`](#work) | yes |  |

### CreateAgentInstanceRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capability_config_values` | map of map of any or null |  | Values for unselected capabilities are ignored. |
| `capability_ids` | array of string or null |  | Omitted/null inherits template defaults; [] selects no optional capabilities. |
| `description` | string, max length 500 or null |  |  |
| `display_name` | string, min length 1, max length 255 | yes |  |
| `model_options` | [`ModelOptions`](#modeloptions) or null |  |  |
| `recommended_chat_profile_id` | string or null |  | Legacy diagnostic reference only; non-null creation is refused. Re-select by offer key. |
| `recommended_model` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `role` | string, min length 1, max length 255 or null |  |  |
| `template_id` | string (uuid) | yes | Canonical UUID returned by this space's template catalog. |
| `tuning_field_values` | map of [`TuningValue`](#tuningvalue) or null |  | All values must match TuningValue before unknown keys are ignored. Known values must also match the pod's FieldSpecs. |
| `usage_statement` | string, min length 1 | yes |  |

### CreateFolder

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |
| `parent_id` | string (uuid) or null |  |  |
| `space_id` | string (uuid) | yes |  |

### CreateOrganization

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `admin_username` | string | yes |  |
| `name` | string | yes |  |
| `owner_username` | string | yes |  |

### CreatePersonalSpace

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `organization_id` | string (uuid) | yes |  |

### CreateSessionRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_instance_id` | string (uuid) | yes |  |
| `session_id` | string (uuid) | yes | Frontend-generated identifier, retained verbatim. |
| `title` | string, max length 500 or null |  |  |

### CreateSpace

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `admin` | string | yes | Initial administrator; creation grants the caller nothing on the new space. |
| `kind` | [`SpaceKind`](#spacekind) | yes |  |
| `name` | string | yes |  |
| `parent_id` | string (uuid) | yes |  |

### Descriptor

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string | yes |  |
| `committed` | [`Manifest`](#manifest) or null |  |  |
| `expires_at` | string (date-time) | yes |  |
| `file` | any | yes |  |
| `folder_id` | string (uuid) | yes |  |
| `folder_path` | string | yes |  |
| `generation` | string (uuid) | yes |  |
| `max_artifacts` | integer (int32), >= 0 | yes |  |
| `max_chunks` | integer (int32), >= 0 | yes |  |
| `max_output_bytes` | integer (int64) | yes |  |
| `mime` | string | yes |  |
| `name` | string | yes |  |
| `organization_id` | string (uuid) | yes |  |
| `output_prefix` | string | yes |  |
| `predecessor` | [`Predecessor`](#predecessor) or null |  |  |
| `profile_settings` | any | yes |  |
| `size` | integer (int64) | yes |  |
| `space_id` | string (uuid) | yes |  |
| `stage` | [`Stage`](#stage) | yes |  |
| `work` | [`Work`](#work) | yes |  |

### Directory

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ancestors` | array of [`Folder`](#folder) | yes |  |
| `can_write` | boolean | yes |  |
| `items` | array of [`Entry`](#entry) | yes |  |
| `limit` | integer (int64) | yes |  |
| `offset` | integer (int64) | yes |  |
| `processing` | map of [`Summary`](#summary) | yes |  |
| `processing_enabled` | boolean | yes |  |
| `total` | integer (int64) | yes |  |

### Document

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string (date-time) | yes |  |
| `created_by` | string | yes |  |
| `folder_id` | string (uuid) or null | yes |  |
| `id` | string (uuid) | yes |  |
| `mime` | string | yes |  |
| `name` | string | yes |  |
| `retrievable` | boolean | yes |  |
| `retrievable_pending` | boolean | yes |  |
| `sha256` | string | yes |  |
| `size` | integer (int64) | yes |  |
| `space_id` | string (uuid) | yes |  |

### DocumentCounts

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `bytes` | integer (int64) | yes | Logical original bytes recorded in SQL, not physical storage usage. |
| `documents` | integer (int64) | yes |  |

### Entry

One of:

- `kind` = `folder`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `data` | [`Folder`](#folder) | yes |  |
| `kind` | `folder` | yes |  |

- `kind` = `document`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `data` | [`Document`](#document) | yes |  |
| `kind` | `document` | yes |  |

### EntryOrder

One of: `name_asc`, `name_desc`, `created_asc`, `created_desc`, `size_asc`, `size_desc`.

### ErrorBody

JSON error envelope shared by application, authentication and import failures.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `code` | string | yes |  |
| `detail` | string | yes |  |

### ExecuteRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_id` | string or null |  |  |
| `agent_instance_id` | string or null |  |  |
| `input` | string |  |  |
| `runtime_context` | map of any or null |  |  |
| `session_id` | string or null |  |  |

### ExecutionPreparation

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_instance_id` | string (uuid) | yes |  |
| `chat_controls` | array of [`ChatControlDescriptor`](#chatcontroldescriptor) | yes | Only controls supported by the current model facts are advertised. |
| `execute_stream_url` | string | yes |  |
| `execute_url` | string | yes |  |
| `execution_transport` | [`ExecutionTransport`](#executiontransport) | yes |  |
| `max_chat_input_chars` | integer (int64), >= 0 or null | yes |  |
| `messages_url_template` | string | yes | RFC 6570 Level 1 template. Substitute the registered session ID. |
| `model_choice` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `model_error` | [`ModelPreparationError`](#modelpreparationerror) or null | yes |  |
| `models` | [`PreparationModels`](#preparationmodels) | yes |  |
| `runtime_id` | string | yes |  |
| `space_id` | string (uuid) | yes |  |
| `supports_hitl` | boolean | yes | False until the managed Weaver HITL journey is connected. |
| `supports_streaming` | boolean | yes |  |
| `supports_ui_parts` | boolean | yes |  |

### ExecutionTransport

One of: `sse`.

### Failure

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `code` | [`FailureCode`](#failurecode) | yes |  |
| `generation` | string (uuid) or null |  |  |
| `stage` | [`Stage`](#stage) | yes |  |
| `work` | [`Work`](#work) | yes |  |

### FailureCode

One of: `unsupported_input`, `access_changed`, `integrity_failure`, `extraction_failed`, `preview_failed`, `indexing_failed`, `capacity_exceeded`, `worker_failed`, `deadline_exceeded`, `delivery_unknown`.

### FileUpload

Multipart body: exactly one `file` part.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | string (binary) | yes | The file; its multipart filename becomes the document name. |

### Folder

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string (date-time) | yes |  |
| `id` | string (uuid) | yes |  |
| `name` | string | yes |  |
| `parent_id` | string (uuid) or null | yes |  |
| `path` | string | yes |  |
| `space_id` | string (uuid) | yes |  |

### FrontendConfig

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `gcu_version` | string or null |  |  |
| `root_bootstrap_completed` | boolean | yes |  |
| `root_bootstrap_required` | boolean | yes |  |
| `user_auth` | [`PublicAuth`](#publicauth) | yes |  |

### Grant

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `role` | [`PlatformRole`](#platformrole) | yes |  |
| `user_id` | string | yes |  |

### Health

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | string | yes |  |

### Language

One of: `en`, `fr`.

### ManagedAgentInstanceSummary

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_instance_id` | string (uuid) | yes |  |
| `capability_config` | map of map of any | yes |  |
| `created_at` | string (date-time) | yes |  |
| `created_by` | string or null |  |  |
| `description` | string or null |  |  |
| `display_name` | string | yes |  |
| `model_options` | [`ModelOptions`](#modeloptions) or null |  |  |
| `recommended_chat_profile_id` | string or null |  | Diagnostic only; requires explicit re-selection if no recommended_model is saved. |
| `recommended_model` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `role` | string | yes |  |
| `selected_capability_ids` | array of string or null |  |  |
| `source_agent_id` | string | yes |  |
| `source_runtime_id` | string | yes |  |
| `space_id` | string (uuid) | yes |  |
| `status` | [`AgentInstanceStatus`](#agentinstancestatus) | yes | Operator state only, not runtime availability. |
| `template_id` | string (uuid) | yes |  |
| `tuning_field_values` | map of any | yes |  |
| `updated_at` | string (date-time) | yes |  |
| `updated_by` | string or null |  |  |
| `usage_statement` | string | yes |  |

### Manifest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifacts` | array of [`Artifact`](#artifact) | yes |  |
| `chunks` | integer (int64) | yes |  |
| `generation` | string (uuid) | yes |  |
| `rows` | integer (int64) or null |  |  |
| `vector_ordinals` | array of integer (int32), >= 0 | yes |  |
| `vectors` | integer (int64) | yes |  |

### Me

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `platform_roles` | array of [`PlatformRole`](#platformrole) | yes |  |
| `user_id` | string | yes |  |
| `username` | string | yes |  |

### ModelConnection

Deliberately excludes discovery URL, authentication and secret references.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `api_root` | string | yes |  |
| `credential_binding` | string | yes | Platform-approved reference to pod-local inference provisioning, never a secret value. |
| `provider` | string | yes |  |

### ModelDiagnostic

One of: `unknown_offer`, `not_permitted`, `source_disabled`, `source_revision_unobserved`, `discovery_unavailable`, `withdrawn`, `chat_not_established`, `options_exceed_known_limit`.

### ModelInventory

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `observation` | [`ModelObservation`](#modelobservation) | yes |  |
| `offers` | array of [`StoredModelOffer`](#storedmodeloffer) | yes |  |

### ModelMetadata

Only supported typed extensions are retained; all other feature facts stay unknown. Labels and limits, when present, are source-reported, never independently verified.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `chat` | boolean or null |  |  |
| `chat_provenance` | [`ChatProvenance`](#chatprovenance) or null |  |  |
| `context_window_tokens` | integer (int64) or null |  |  |
| `display_name` | string or null |  |  |
| `max_input_tokens` | integer (int64) or null |  |  |
| `max_output_tokens` | integer (int64) or null |  |  |
| `reasoning` | boolean or null |  | Source-reported aptitude; absent means unknown, not unsupported. |

### ModelObservation

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `checked_at` | string (date-time) or null |  |  |
| `enabled` | boolean | yes |  |
| `error_code` | string or null |  |  |
| `last_success_at` | string (date-time) or null |  |  |
| `snapshot_revision` | integer (int64) | yes |  |
| `snapshot_source_revision` | integer (int64) or null |  |  |
| `source_id` | string | yes |  |
| `source_revision` | integer (int64) | yes |  |
| `state` | string | yes |  |

### ModelOfferKey

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_id` | string | yes |  |
| `upstream_model_id` | string | yes |  |

### ModelOptions

Only explicit overrides. Missing/null members supply no value, not a provider default.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `max_tokens` | integer (int64), >= 1 or null |  |  |
| `temperature` | number (double) or null |  |  |
| `top_p` | number (double), >= 0, <= 1 or null |  |  |

### ModelPreparationError

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `code` | [`ModelPreparationErrorCode`](#modelpreparationerrorcode) | yes |  |
| `message` | string | yes |  |

### ModelPreparationErrorCode

One of: `selection_missing`, `reselection_required`, `offer_unknown`, `offer_forbidden`, `offer_unavailable`, `fallback_unavailable`.

### MySpace

Extends [`Space`](#space) with:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `inherited_roles` | array of [`Role`](#role) | yes | The subset of `roles` held only through an ancestor. |
| `organization_id` | string (uuid) | yes |  |
| `roles` | array of [`Role`](#role) | yes | Effective roles, including those descending from an ancestor. |

### OnboardingStatus

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acceptance` | [`Acceptance`](#acceptance) or null |  |  |
| `gcu_version` | string or null |  |  |
| `root_bootstrap_required` | boolean | yes |  |
| `user_id` | string | yes |  |
| `username` | string | yes |  |

### OrganizationModelInventory

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `policy` | [`OrganizationModelPolicy`](#organizationmodelpolicy) | yes | Only this organization's choices; none is a proof of executability. |
| `sources` | array of [`ModelInventory`](#modelinventory) | yes | Shared platform observations. Presence/chat/discovery are independent of permission. |

### OrganizationModelPolicy

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string (date-time) or null |  |  |
| `created_by` | string or null |  |  |
| `default` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `fallback` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `organization_id` | string (uuid) | yes |  |
| `permitted` | array of [`ModelOfferKey`](#modelofferkey) | yes |  |
| `reasoning_enabled` | array of [`ModelOfferKey`](#modelofferkey), max items 4096 | yes | Organization ceiling, independent of the user's per-question choice. |
| `revision` | integer (int64) | yes | Zero means no saved policy: no permissions or implicit selections. |
| `updated_at` | string (date-time) or null |  |  |
| `updated_by` | string or null |  |  |

### OrganizationPage

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | array of [`Space`](#space) | yes |  |
| `next_cursor` | string (uuid) or null |  |  |

### OrganizationSupervision

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `active_teams` | integer (int64), >= 0 | yes |  |
| `collection_finished_at` | string (date-time) | yes | Collection bounds, not an atomic SQL/OpenFGA snapshot. |
| `collection_started_at` | string (date-time) | yes |  |
| `organization_direct` | [`SupervisionCounts`](#supervisioncounts) | yes |  |
| `organization_id` | string (uuid) | yes |  |
| `personal_total` | [`SupervisionCounts`](#supervisioncounts) | yes | All personal spaces aggregated; no personal identity or space is exposed. |
| `teams` | [`SupervisionTeamsPage`](#supervisionteamspage) | yes | UUID ascending, at most 100 teams. Totals never depend on this page. |
| `teams_total` | [`SupervisionCounts`](#supervisioncounts) | yes |  |
| `totals` | [`SupervisionCounts`](#supervisioncounts) | yes |  |

### PatchUserPreferences

Omitted fields are preserved; explicit null restores the field's default.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_sort` | [`AgentSort`](#agentsort) or null |  |  |
| `language` | [`Language`](#language) or null |  |  |
| `sidebar_collapsed` | boolean or null |  |  |
| `team_sort_mode` | [`TeamSortMode`](#teamsortmode) or null |  |  |
| `theme_mode` | [`ThemeMode`](#thememode) or null |  |  |
| `ui_theme_id` | string or null |  |  |

### Permission

Computed permissions checked against OpenFGA.

One of: `read`, `write`, `manage`.

### PlatformCheck

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `permission` | [`PlatformPermission`](#platformpermission) | yes |  |

### PlatformPermission

One of: `list_all_teams`, `delete_team`, `delete_space`, `rescue_team_admin`, `edit_agent_class_path`, `observe_platform`, `administer_users`, `manage_platform`, `manage_capabilities`, `edit_platform_prompt`.

### PlatformRole

One of: `platform_owner`, `platform_observer`, `feature_manager`, `prompt_editor`.

### PodCapabilityDescriptor

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `config_fields` | array of [`CapabilityFieldDescription`](#capabilityfielddescription) |  |  |
| `description` | string | yes |  |
| `execution_models` | array of [`CapabilityExecutionModel`](#capabilityexecutionmodel) |  |  |
| `icon` | string | yes |  |
| `id` | string | yes |  |
| `kind` | [`PodCapabilityKind`](#podcapabilitykind) |  |  |
| `name` | string | yes |  |
| `public_version` | string or null |  |  |
| `runtime_id` | string or null |  |  |
| `source_id` | string or null |  |  |
| `team_settings_fields` | array of [`CapabilityFieldDescription`](#capabilityfielddescription) |  |  |
| `version` | string | yes |  |

### PodCapabilityInventory

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capabilities` | array of [`CapabilityInventoryOffer`](#capabilityinventoryoffer) | yes |  |
| `checked_at` | string (date-time) or null |  |  |
| `enabled` | boolean | yes |  |
| `observation` | [`CatalogObservationState`](#catalogobservationstate) | yes |  |
| `observed_at` | string (date-time) or null |  |  |
| `runtime_id` | string | yes |  |
| `template_capabilities` | array of [`PodTemplateCapability`](#podtemplatecapability) | yes | Links from the last successful snapshot, all scoped to this runtime. |

### PodCapabilityKind

One of: `tool`.

### PodTemplateCapability

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capability_id` | string | yes |  |
| `default_selected` | boolean | yes |  |
| `source_agent_id` | string | yes |  |

### Predecessor

The previous stage's result and the stored prefix that holds its artifacts.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `manifest` | [`Manifest`](#manifest) | yes |  |
| `prefix` | string | yes |  |

### Preflight

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `files` | array of [`Candidate`](#candidate) | yes | 1..200 files to check. |

### PreflightResult

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `conflicts` | array of string | yes | Requested names already stored or being uploaded in the folder. |
| `storage` | [`StorageSummary`](#storagesummary) | yes |  |

### PreparationModelOffer

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `candidate` | boolean | yes |  |
| `diagnostics` | array of [`ModelDiagnostic`](#modeldiagnostic) | yes |  |
| `key` | [`ModelOfferKey`](#modelofferkey) | yes |  |
| `metadata` | [`ModelMetadata`](#modelmetadata) or null | yes |  |
| `permitted` | boolean | yes |  |
| `reasoning_enabled` | boolean | yes |  |
| `selectable` | boolean | yes |  |

### PreparationModels

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `fallback` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `legacy_profile_id` | string or null | yes | A retained diagnostic only, never a selectable profile. |
| `offers` | array of [`PreparationModelOffer`](#preparationmodeloffer) | yes |  |
| `options` | [`ModelOptions`](#modeloptions) | yes |  |
| `recommendation` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `requires_reselection` | boolean | yes |  |

### ProcessingCount

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `documents` | integer (int64) | yes |  |
| `stage` | [`Stage`](#stage) | yes |  |
| `status` | [`ProcessingStatus`](#processingstatus) | yes |  |

### ProcessingStatus

`pending` until a worker claims the attempt, `running`, then `succeeded` or `failed`.

One of: `pending`, `running`, `succeeded`, `failed`.

### Profile

Processing depth; its settings come from the Knowledge Flow worker's exported profiles.

One of: `fast`, `medium`, `rich`.

### ProjectionPhase

One of: `ready`, `writing`, `applied`.

### ProvisioningUpload

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | string (binary) | yes |  |

### PublicAuth

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `client_id` | string | yes |  |
| `enabled` | boolean | yes |  |
| `provider` | string | yes |  |
| `realm_url` | string | yes |  |
| `roles_claim` | array of string or null |  |  |
| `uid_claim` | string | yes |  |

### PublicationCounts

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `chunks` | integer (int64) | yes | Committed manifest counts; no OpenSearch presence check. |
| `datasets_with_unknown_rows` | integer (int64) | yes |  |
| `documents` | integer (int64) | yes |  |
| `known_rows` | integer (int64) | yes |  |
| `tabular_datasets` | integer (int64) | yes | Published datasets/*.parquet artifacts, not SQL tables. |
| `total_rows` | integer (int64) or null | yes | Null when at least one dataset has no attributable row count. |
| `vectors` | integer (int64) | yes |  |

### Receipt

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor_subject` | string | yes |  |
| `completed_at` | string (date-time) or null |  |  |
| `documents_deleted` | integer (int64) | yes |  |
| `due_at` | string (date-time) | yes |  |
| `error_code` | string or null |  |  |
| `folders_deleted` | integer (int64) | yes |  |
| `id` | string (uuid) | yes |  |
| `organization_id` | string (uuid) | yes |  |
| `requested_at` | string (date-time) | yes |  |
| `rule_id` | string or null |  |  |
| `spaces_deleted` | integer (int64) | yes |  |
| `status` | [`Status`](#status) | yes |  |
| `target_id` | string (uuid) | yes |  |
| `target_kind` | [`TargetKind`](#targetkind) | yes |  |
| `target_parent_id` | string (uuid) or null |  |  |

### Rename

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes |  |

### ReplaceModelPolicy

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `expected_revision` | integer (int64), >= 0 | yes |  |
| `fallback` | [`ModelOfferKey`](#modelofferkey) or null | yes |  |
| `permitted` | array of [`ModelOfferKey`](#modelofferkey), max items 4096 | yes |  |
| `reasoning_enabled` | array of [`ModelOfferKey`](#modelofferkey), max items 4096 | yes | Organization ceiling, independent of the user's per-question choice. |

### Report

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `grants_acknowledged` | integer, >= 0 | yes |  |
| `identities_created` | integer, >= 0 | yes |  |
| `identities_resolved` | integer, >= 0 | yes |  |
| `spaces_reconciled` | integer, >= 0 | yes |  |

### RetrievalConfirmation

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `operation_id` | string (uuid) | yes |  |
| `retrievable` | boolean | yes |  |
| `step` | [`RetrievalStep`](#retrievalstep) | yes |  |

### RetrievalStep

One of: `claim`, `applied`, `confirm`.

### RetrievalWork

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `confirmed` | boolean | yes |  |
| `document_id` | string (uuid) | yes |  |
| `manifest` | [`Manifest`](#manifest) | yes |  |
| `operation_id` | string (uuid) | yes |  |
| `phase` | [`ProjectionPhase`](#projectionphase) | yes |  |
| `retrievable` | boolean | yes |  |

### Role

Direct roles stored in OpenFGA.

One of: `member`, `editor`, `admin`, `analyst`, `organization_owner`, `personal_space_creator`.

### RoleAssignments

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `assignments` | integer (int64), >= 0 | yes | Direct (user, space, role) tuples, never effective/inherited grants. |
| `role` | [`Role`](#role) | yes |  |

### RuntimeAgent

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `configuration` | any | yes | Saved tuning, excluding the legacy profile reference exposed in models for diagnostics. No refresh from the catalog; fields, values and capability envelopes are preserved. |
| `configuration_updated_at` | string (date-time) | yes |  |
| `instance_id` | string (uuid) | yes |  |
| `runtime_id` | string | yes |  |
| `template_id` | string (uuid) | yes | Organization-qualified OpenFGA identity, distinct from the registry key. |
| `template_key` | string | yes |  |

### RuntimeBinding

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent` | [`RuntimeAgent`](#runtimeagent) | yes |  |
| `conversation_id` | string or null | yes |  |
| `models` | [`RuntimeModels`](#runtimemodels) | yes |  |
| `run_id` | string or null | yes |  |
| `space` | [`RuntimeSpace`](#runtimespace) | yes |  |
| `subject_id` | string | yes |  |

### RuntimeEvent

One of:

- `kind` = `status`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `status` | yes |  |
| `sequence` | integer (int64), >= 0 | yes |  |
| `status` | string | yes |  |

- `kind` = `assistant_delta`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `delta` | string | yes |  |
| `kind` | `assistant_delta` | yes |  |
| `sequence` | integer (int64), >= 0 | yes |  |

- `kind` = `final`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `content` | string | yes |  |
| `finish_reason` | string | yes |  |
| `kind` | `final` | yes |  |
| `sequence` | integer (int64), >= 0 | yes |  |

### RuntimeModelOffer

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `candidate` | boolean | yes | Necessary known facts only; local support, credentials and connectivity remain unproven. |
| `connection` | [`ModelConnection`](#modelconnection) or null |  |  |
| `diagnostics` | array of [`ModelDiagnostic`](#modeldiagnostic) | yes |  |
| `key` | [`ModelOfferKey`](#modelofferkey) | yes |  |
| `metadata` | [`ModelMetadata`](#modelmetadata) or null |  |  |
| `observation` | [`ModelObservation`](#modelobservation) or null |  |  |
| `permitted` | boolean | yes |  |
| `selectable` | boolean | yes | New selection writes additionally require successful current discovery (M2). |

### RuntimeModels

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `legacy_profile_id` | string or null |  | Diagnostic only. Never an alternative resolution key. |
| `offers` | array of [`RuntimeModelOffer`](#runtimemodeloffer) | yes | Union of permitted keys and retained recommendation/default/fallback references. |
| `options` | [`ModelOptions`](#modeloptions) | yes |  |
| `policy` | [`OrganizationModelPolicy`](#organizationmodelpolicy) | yes |  |
| `recommendation` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `requires_reselection` | boolean | yes |  |

### RuntimeSpace

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes |  |
| `kind` | [`SpaceKind`](#spacekind) | yes |  |
| `organization_id` | string (uuid) or null | yes | Canonical organization ownership, not inherited document scope for personal spaces. |
| `project_id` | string (uuid) or null | yes |  |
| `team_id` | string (uuid) or null | yes |  |

### Scope

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `space_ids` | array of string (uuid) | yes | Filter for chunks and metadata: `space_id` must be one of these. The space and its ancestors, never descendants: a team conversation never sees its projects' content. A personal space's scope is itself. |

### SessionDetails

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_deleted` | boolean | yes |  |
| `agent_disabled` | boolean | yes |  |
| `agent_display_name` | string | yes | Current name, or the registration snapshot after instance removal. |
| `agent_instance_id` | string (uuid) | yes |  |
| `created_at` | string (date-time) | yes |  |
| `messages_url` | string or null | yes | Public history destination, independent of instance/template execution state. Null if this runtime has no enabled, platform-approved public route. |
| `runtime_id` | string | yes |  |
| `session_id` | string (uuid) | yes |  |
| `space_id` | string (uuid) | yes |  |
| `template_id` | string (uuid) | yes |  |
| `title` | string or null | yes |  |
| `updated_at` | string (date-time) | yes |  |

### SetDefaultOnRequest

Organization "enabled for all" decision, shared by agents and capability offers.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default_on` | boolean | yes |  |

### SetRetrievable

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `retrievable` | boolean | yes |  |

### Space

A space with its immutable placement and derived search path.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string (uuid) | yes |  |
| `kind` | [`SpaceKind`](#spacekind) | yes |  |
| `name` | string | yes |  |
| `parent_id` | string (uuid) or null | yes |  |
| `path` | array of string (uuid) | yes | Ancestors then self: the search scope. A personal space's path is itself. |
| `personal_owner` | string or null | yes |  |

### SpaceCheck

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `permission` | [`SpacePermission`](#spacepermission) | yes |  |
| `space_id` | string (uuid) | yes |  |

### SpaceKind

One of: `organization`, `team`, `project`, `personal`.

### SpacePermission

Evaluation is a space capability, never a document read/write permission.

One of: `read`, `write`, `manage`, `run_evaluations`, `manage_evaluation_corpus`, `read_conversations_for_evaluation`, `own_organization`, `create_personal_space`.

### Stage

Pipeline position: `queued`, `preparation`, `extraction`, `indexing`, then `done`.

One of: `queued`, `preparation`, `extraction`, `indexing`, `done`.

### Start

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `profile` | [`Profile`](#profile) | yes |  |
| `retry_of` | string (uuid) or null |  | Failed attempt to retry; required once the document has any attempt. |

### Status

One of: `queued`, `running`, `retrying`, `blocked`, `completed`.

### StorageSummary

Storage usage of a space; a project counts against its team's quota.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `bytes` | integer (int64) | yes | Total size of those documents. |
| `documents` | integer (int64) | yes | Documents in this space alone. |
| `max_file_bytes` | integer (int64), >= 0 | yes | Largest accepted file. |
| `processing_enabled` | boolean | yes | Whether processing can be requested. |
| `quota_bytes` | integer (int64) | yes | Quota shared by the space and, for a team, its projects. |
| `reserved_bytes` | integer (int64) | yes | Bytes reserved by uploads in progress, also counted against the quota. |
| `types` | array of [`TypeUsage`](#typeusage) | yes | Usage by reported MIME type: the 20 largest, then `other`. |
| `uploads_enabled` | boolean | yes |  |
| `used_bytes` | integer (int64) | yes | Published bytes counted against that quota. |

### StoredModelOffer

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `advertised` | boolean | yes |  |
| `first_seen_at` | string (date-time) | yes |  |
| `last_seen_at` | string (date-time) | yes |  |
| `metadata` | [`ModelMetadata`](#modelmetadata) | yes |  |
| `source_id` | string | yes |  |
| `upstream_model_id` | string | yes |  |
| `withdrawn_at` | string (date-time) or null |  |  |

### Summary

One processing attempt of a document.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `chunks` | integer (int64) | yes | Published text chunks; set on success. |
| `completed_at` | string (date-time) or null |  | When the attempt became `succeeded` or `failed`. |
| `created_at` | string (date-time) | yes |  |
| `document_id` | string (uuid) | yes |  |
| `error_code` | string or null |  | Last reported `FailureCode`; final once `failed`. |
| `id` | string (uuid) | yes | Attempt ID; pass it as `retry_of` to retry a failed attempt. |
| `profile` | [`Profile`](#profile) | yes |  |
| `retry_of` | string (uuid) or null |  | Failed attempt this one retries. |
| `revision` | integer (int64) | yes | Increases with every recorded change, so a poller can skip unchanged attempts. |
| `rows` | integer (int64) or null |  | Table rows, for a tabular document. |
| `stage` | [`Stage`](#stage) | yes |  |
| `status` | [`ProcessingStatus`](#processingstatus) | yes |  |
| `vectors` | integer (int64) | yes | Published search vectors; set on success. |

### SupervisionCounts

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `active` | [`DocumentCounts`](#documentcounts) | yes |  |
| `direct_roles` | array of [`RoleAssignments`](#roleassignments) | yes | Roles with no direct attribution are omitted (zero). |
| `distinct_users` | integer (int64), >= 0 | yes | Union of direct subjects; never sum role columns or child distinct counts. |
| `failed_documents` | integer (int64) | yes |  |
| `pending_purge` | [`DocumentCounts`](#documentcounts) | yes | Remaining SQL documents retired directly or through their owning space. |
| `processing` | array of [`ProcessingCount`](#processingcount) | yes | Latest attempt per active document. Missing status/stage pairs mean zero. |
| `published` | [`PublicationCounts`](#publicationcounts) | yes |  |

### SupervisionTeamsPage

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `items` | array of [`TeamSupervision`](#teamsupervision) | yes |  |
| `next_cursor` | string (uuid) or null | yes |  |

### TargetKind

One of: `organization`, `team`, `project`, `document`, `session`.

### TeamSortMode

One of: `recent`, `alpha`.

### TeamSupervision

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `counts` | [`SupervisionCounts`](#supervisioncounts) | yes | Includes the team's projects, without inherited organization roles. |
| `id` | string (uuid) | yes |  |
| `name` | string | yes |  |

### TeamSupervisionDetail

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `collection_finished_at` | string (date-time) | yes |  |
| `collection_started_at` | string (date-time) | yes |  |
| `organization_id` | string (uuid) | yes |  |
| `team` | [`TeamSupervision`](#teamsupervision) | yes |  |

### TermsRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | string | yes |  |

### ThemeMode

One of: `light`, `dark`, `system`.

### TuningScalar

Type: string or number (double) or boolean.

### TuningValue

Type: [`TuningScalar`](#tuningscalar) or array of [`TuningScalar`](#tuningscalar) or map of [`TuningScalar`](#tuningscalar).

### TypeUsage

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `bytes` | integer (int64) | yes |  |
| `documents` | integer (int64) | yes |  |
| `mime` | string | yes | Reported MIME type, or `other`. |

### UpdateAgentInstanceRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capability_config_values` | map of map of any or null |  | Omitted keeps config for an unchanged selection; null resets selected config. |
| `capability_ids` | array of string or null |  | Omitted keeps selection; null resolves current defaults; [] selects none. |
| `description` | string, max length 500 or null |  | An empty string is an explicit description. |
| `display_name` | string, min length 1, max length 255 or null |  | Omitted/null metadata leaves the saved value unchanged. |
| `model_options` | [`ModelOptions`](#modeloptions) or null |  |  |
| `recommended_chat_profile_id` | string or null |  | Omitted keeps the recommendation; null clears it; other values return 422. |
| `recommended_model` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `role` | string, min length 1, max length 255 or null |  |  |
| `status` | [`AgentInstanceStatus`](#agentinstancestatus) or null |  |  |
| `tuning_field_values` | map of [`TuningValue`](#tuningvalue) or null |  | Omitted keeps values; null/{} clears them; an object replaces known values. |
| `usage_statement` | string, min length 1 or null |  |  |

### UpdateSessionRequest

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `title` | string, max length 500 or null |  | Omitted/null keeps the current title; an empty string explicitly clears it. |
| `updated_at` | string (date-time) or null |  | Last observed activity. Monotonic, capped at server time; omission keeps activity. |

### UploadReceipt

Durable outcome of one upload request, readable by its request key.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acknowledged_at` | string (date-time) or null |  | When the receipt was dismissed or superseded. |
| `completed_at` | string (date-time) or null |  | When the upload became `stored` or `failed`. |
| `created_at` | string (date-time) | yes |  |
| `document_id` | string (uuid) or null |  | Set once `stored`. |
| `error_code` | string or null |  | Failure code when `failed`. |
| `folder_id` | string (uuid) | yes |  |
| `mime` | string | yes | MIME type reported by the client; metadata, not verified. |
| `name` | string | yes | NFC-normalized filename. |
| `processing` | [`Summary`](#summary) or null |  |  |
| `processing_profile` | [`Profile`](#profile) or null |  |  |
| `request_key` | string (uuid) | yes | The `Idempotency-Key` that identifies this receipt. |
| `sha256` | string | yes | Hex SHA-256 of the received bytes. |
| `size` | integer (int64) | yes | Bytes received. |
| `space_id` | string (uuid) | yes |  |
| `status` | [`UploadStatus`](#uploadstatus) | yes |  |
| `successor_key` | string (uuid) or null |  | Request key of the retry that replaced this failed upload. |

### UploadStatus

`pending` while the file is transferred and verified, then `stored` once published, or `failed` with an `error_code`.

One of: `pending`, `stored`, `failed`.

### UserPreferences

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_sort` | [`AgentSort`](#agentsort) | yes |  |
| `initialized` | boolean | yes |  |
| `language` | [`Language`](#language) or null |  |  |
| `sidebar_collapsed` | boolean | yes |  |
| `team_sort_mode` | [`TeamSortMode`](#teamsortmode) | yes |  |
| `theme_mode` | [`ThemeMode`](#thememode) | yes |  |
| `ui_theme_id` | string or null |  |  |

### UserSummary

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `avatar_image_url` | string or null |  |  |
| `email` | string or null |  |  |
| `first_name` | string or null |  |  |
| `id` | string | yes |  |
| `last_name` | string or null |  |  |
| `username` | string or null |  |  |

### VectorPlan

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `count` | integer (int32), >= 0 | yes |  |
| `generation` | string (uuid) | yes |  |
| `work` | [`Work`](#work) | yes |  |

### Work

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `contract_version` | integer (int32), >= 1, <= 1 | yes |  |
| `document_id` | string (uuid) | yes |  |
| `installation_id` | string (uuid) | yes |  |
| `original_sha256` | string | yes |  |
| `processing_id` | string (uuid) | yes |  |
| `profile` | [`Profile`](#profile) | yes |  |
<!-- end generated -->
