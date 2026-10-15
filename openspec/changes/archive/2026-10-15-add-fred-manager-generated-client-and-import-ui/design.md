## Context

The importer returns HTTP 200 with four acknowledgment counts after completion. The control-plane Migration page instead expects an asynchronous task ID and also owns snapshot export/reset. The UI shell obtains login and admission configuration from the control-plane. Manager roles are held separately in OpenFGA.

## Goals / Non-Goals

Expose the existing manager HTTP surface accurately and consume provisioning through the normal Redux/authentication path. Do not translate synchronous results into fake tasks, migrate unrelated control-plane pages, or change admission policies. Existing document routes receive contract metadata only.

## Decisions

- Use utoipa schemas derived on the existing DTOs and utoipa-axum route registration so runtime paths and generated paths share one definition. Emit canonical `/fred-manager/v1` paths with an offline CLI command before configuration loading. No Swagger UI or additional schema service is needed. Preserve nullable fields, flattened responses, enums, optional bodies, query cursors, empty responses and the multipart binary field.
- Reuse `@rtk-query/codegen-openapi`, the existing dynamic base query, and ordinary reducer/middleware registration. Keep generated output committed and OpenAPI JSON ignored, matching other services. Multipart adaptation, if required by the generator, lives in a small handwritten enhancement using generated types, never in generated output.
- Place provisioning in a dedicated admin page because snapshot migration has a different purpose and contract. Resolve its access from manager `/me`; do not infer manager authority from control-plane roles. Preserve existing application admission guards. Hide upload until authority resolves, report authorization-service errors explicitly, and recheck authority at the server on every import.
- Show the synchronous acknowledgment counts, disable duplicate submission, distinguish unsupported ZIP/errors from success, and explain that failure or connection loss can leave effects and replay is additive. Never render a successful completion before the response arrives.
- Route `/fred-manager` ahead of Vite's broad `/fred` prefix. Keep deployment routing consistent wherever the frontend proxy owns it.
- Reuse disposable PostgreSQL/OpenFGA/Keycloak test fixtures and Playwright browser automation. Test the Make ZIP rather than handcrafted successful responses. Exercise authentication, actual multipart requests, completed reports and replay; assert resulting spaces and roles against the manager and reject unauthorized/legacy imports. Isolate shell dependencies explicitly if necessary; never mock the manager, directory or authorization engine in the import journey.

## Risks / Trade-offs

- Generated declarations can drift from extractor behavior: cover route inventory, body/schema edge cases and the generated multipart transport with executable contract tests.
- Manager and control-plane permissions differ: keep authority decisions local to the owning API and test a manager admin without control-plane admin rights.
- A disconnected synchronous import has an uncertain result: do not automatically retry application failures; preserve clear replay guidance.
- A manager `/me` request adds five platform Checks, deduplicated by RTK Query across navigation and the guard. Import itself retains its existing request budget and SQL locking. No new OpenFGA evaluator or grant store is introduced.

## Migration Plan

Generate the contract/client first, then connect the page and browser test. Each complete step receives independent review, regression corrections, the required checks and an arc42 documentation pass in its local commit. No data migration or push. Reverting the frontend step removes the new entry without changing stored roles or imported data.
