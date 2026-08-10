# RFC: Content URL strategy — application-signed proxy URLs when presigning is unavailable

**Status:** proposed; open questions in §6 need sign-off before implementation
**Author:** fmuller
**Date:** 2026-08-10
**ID:** CONTENT-URL-STRATEGY
**Related docs:** `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`, `docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`
**Related issues:** #1209 (closed — introduced the presigned media rewrite), #1897 (open — configurable media TTL), #1795 (closed — native GCS backend)

---

## 1. Problem

Browser-facing presigned URLs only work on MinIO/S3. On a private GCP deployment
using GCS we do not (yet) hold `iam.serviceAccounts.signBlob` on a signing service
account, and V4 signing requires either that permission or an exported SA key.
Neither is available, and the request is pending. The platform needs to work in
the meantime.

Two consequences today:

1. **Knowledge Flow — markdown images are broken.** `content_controller.py:104`
   rewrites in-document media references to presigned URLs so the browser `<img>`
   can load them without a bearer token. Line 111 guards it with
   `isinstance(content_store, MinioStorageBackend)`, and KF's GCS store raises
   `NotImplementedError` outright (`gcs_content_store.py:322`). On GCS the rewrite
   is silently skipped, the original same-origin URL survives, and the
   unauthenticated `<img>` request is refused.

2. **Control plane — the app will not start.** `app/context.py:258-266` fails fast
   when a GCS content store is configured without `signing_service_account_email`.
   Team avatars (`teams/service.py:1517`) are the only consumer.

The same gap exists in local mode: `LocalContentStore.get_presigned_url`
(`local_content_store.py:100`) and `FileSystemContentStore.get_presigned_url`
(`filesystem_content_store.py:420`) both raise, so team avatars have never worked
on a local filesystem backend.

This is not a new architectural direction. The GCS store's own docstring already
records the intended fallback — "the deployment default relies on application-level
HMAC download tokens (backend-agnostic)" (`gcs_content_store.py:328-329`) — and the
primitive exists (`features/filesystem/download_token.py`). It was never built.

## 2. Proposed solution

Replace the presigned URL with an application-signed URL pointing at a minimal
read-through proxy in front of the content store the app already has.

The signature **is** the authorization decision, minted by code that has already
run its ReBAC check. This is deliberately the same security model as a presigned
URL — a time-limited bearer capability over one object key — so that the two modes
are transparently interchangeable for every consumer.

### 2.1 Configuration

A `url_strategy` field on the existing `content_storage` discriminated union in
each app:

```yaml
content_storage:
  type: gcs
  url_strategy: proxy # "presigned" (default) | "proxy"
```

Rationale for a per-store field rather than a global boolean:

- Control plane and Knowledge Flow are configured independently; one env var
  cannot express "GCS here, MinIO there".
- Local mode simply defaults to `proxy` and gains working avatars, with no flag
  and no temporary-ness.
- The field is self-documenting at removal time. A boolean named
  `bypass_presigned_urls` in a prod values file outlives its reason.

**No `auto` mode.** Catching `NotImplementedError` and falling back silently (the
pattern at `tabular/service.py:1141`) would turn a production misconfiguration
into an unnoticed bandwidth bill. Misconfiguration must fail fast, as it does today.

### 2.2 Resolver

Services stop calling `store.get_presigned_url()` and call a resolver that returns
either the real presigned URL or a proxy URL, per configured strategy. The
`isinstance(..., MinioStorageBackend)` check at `content_controller.py:111`
disappears — backend capability was never a type question.

Invariant, unchanged from the one already governing `get_presigned_url`:

> Only call the resolver after the caller has authorized the user for that object.

Current call sites already satisfy it: `content_service.py:150` runs the ReBAC
`READ` check that transitively guards markdown preview; team avatar URLs are built
inside already-authorized team reads.

### 2.3 Token

`{expiry}.{HMAC-SHA256(key|expiry)}`, urlsafe-base64, verified with
`hmac.compare_digest`. Stateless: no token store, expiry travels in the token and
is trustworthy only because the signature covers it.

**The uid is deliberately not bound.** The existing `/fs/download` token binds
`path|uid|expiry`, which works only because that route *also* has
`Depends(get_current_user)` to supply the uid at verify time. The object proxy has
no session by construction — that is the whole point — so a uid it cannot recompute
is unverifiable, and one it transmits is a uid leaked in a URL.

### 2.4 Route

A router factory in `fred-core`, **mounted only when `url_strategy == "proxy"`**.
In `presigned` mode the endpoint does not exist and does not appear in the OpenAPI
spec, so there is no dormant unauthenticated route. Removal is a config flip plus
deleting the field.

Streaming follows the existing reference pattern at
`content_controller.py:300-393`: `Accept-Ranges`, 206 with `Content-Range` and no
`Content-Length`, 416 handling, `BackgroundTask(close)`, chunked generator.

Response headers must include `Cache-Control: private, max-age=…` and an `ETag`.
Without them a markdown document with twenty images re-streams twenty objects
through the API pod on every render. `private` (not `public`) keeps a capability
URL out of shared proxy caches.

### 2.5 TTL

60 seconds for both markdown media and team avatars. The current 1 hour on avatars
(`teams/service.py:1517`) is not needed and is reduced here. #1897 (configurable
TTL) stays independent.

## 3. Explicitly rejected

**Re-checking ReBAC inside the proxy.** Considered for revocation-within-TTL.
Rejected: the proxy would need a key→resource→permission mapping maintained
separately from the minting code — a second authz surface that drifts the moment
anyone adds an object type. It would also make `proxy` behave differently from
`presigned` (revocation mid-TTL), defeating the transparency requirement. A real
presigned URL has exactly the same non-revocability; short TTLs are the control in
both modes. Parity is the goal, not improvement.

**Frontend blob fetch.** `knowledgeFlowApi.blob.ts:31` already has
`downloadMarkdownMediaBlob`; a custom `img` component could fetch with the bearer
token and produce an object URL. Rejected: it requires changes in every consumer
(markdown renderer, `TeamCard`, `TeamSettingsParameters`, `HomeNavPanel`), needs
`URL.revokeObjectURL` lifecycle management, breaks Range/streaming, and — decisive
— is hard to remove cleanly later. The proxy leaves the frontend byte-identical in
both modes.

**Short-lived scoped cookie.** `HttpOnly; SameSite=Strict` cookie scoped to the
object path would make plain authenticated URLs work in `<img>`. Rejected:
introduces cookie auth into a bearer-only stack, adds CSRF surface, and assumes
frontend/API share an origin — too much for a temporary measure.

**A single central proxy in control-plane.** Rejected: each app's store points at
its own bucket with its own credentials and key layout (CP `{bucket}-objects` at
`app/context.py:242`; KF a separate bucket and a richer store hierarchy). One
central proxy would need credentials for every app's bucket, making CP a storage
superuser, or would double-hop back into KF. The shared code lives in `fred-core`
and is mounted twice — one implementation, two mount points.

## 4. Security considerations

The primitive is reused, but its **role is inverted**, and this is the main risk
in the RFC.

At `mcp_fs_controller.py:230` the token is *optional* and sits on top of
`Depends(get_current_user)` plus a full ReBAC check in `service.read_bytes`. It can
only ever narrow access; it grants nothing. In the object proxy the token is the
sole grant. Consequences:

1. **The signing secret becomes a credential.** The dev fallback at
   `download_token.py:44` is tolerable for a narrowing token but not for a
   granting one. It is removed outright and replaced by `config/.env` +
   `config/.env.template` entries, with a startup failure when unset (§6.2).
2. **Per-app secrets.** The helper moves to `fred-core`; key material stays
   per-app, so a KF token is not valid against CP objects.
3. **Key handling.** The object key is bound in the signature and must be resolved
   without path traversal — there is no ReBAC check downstream to catch a bad key.
4. **Secrets in logs — pre-existing, fixed here.** `content_controller.py:124`
   logs the generated signed URL at INFO and `:212` logs the entire rewritten
   markdown body. Both leak credentials today, for presigned URLs, independently
   of this RFC. The tabular path already redacts (`tabular/service.py:143-145`);
   the same treatment applies, and the new tokens must never be logged.
5. **Bandwidth.** Bytes now traverse the API pod. Acceptable for avatars and
   inline images. Large PDFs stay on the existing bearer-authenticated streaming
   path (`PdfStreamingDocumentViewer.tsx:136-147`) and must not be routed here.

## 5. Impact on existing contracts

- `fred_core.store.ContentStore` (`base_content_store.py:55`) — a resolver is
  added alongside `get_presigned_url`; the protocol method itself is unchanged.
- `BaseContentStore` (KF, `base_content_store.py:222`) — unchanged;
  `get_presigned_url_internal` (tabular/DuckDB) is out of scope and keeps working
  on GCS.
- Frontend — no change in either mode. No generated-client regeneration expected
  unless §6.3 resolves toward exposing the route in the OpenAPI spec.
- Helm — `url_strategy` added to `values-gcp.yaml` (CP and KF content_storage
  blocks) plus the per-app signing secret.

## 6. Resolved decisions (signed off 2026-08-10)

**6.1 Resolver placement — standalone `fred-core` service.** The repo has two
independent content-store families: `fred_core.store.ContentStore` (a 2-method
`Protocol`, used by control-plane) and KF's much richer `BaseContentStore` ABC.
A mixin adopted by both was considered and rejected: it would have to be wired
into six store classes across two hierarchies with different constructors, each
needing strategy, secret, and public base URL injected at construction — pushing
key material into every storage class and redefining "content store" as something
that also mints capability tokens. It would also modify a shared protocol and an
ABC, dragging in a contract-doc update. The standalone resolver is purely
additive and touches neither hierarchy.

**6.2 Secret handling — hard-fail, and the dev fallback is removed entirely.**
The `_DEV_FALLBACK` signing key at `download_token.py:44` is deleted rather than
kept for `/fs/download`'s existing narrowing use. A hardcoded default signing key
in shipped source is dangerous regardless of the route consuming it, and the repo
already has the right mechanism for this: per-app `config/.env` files, with
`config/.env.template` documenting each secret. The signing secret joins them.

Missing secret therefore raises at startup, not at first use, with an error naming
the variable and the file to set it in — so a developer and an ops engineer both
get an actionable message rather than a silent insecure default.

**6.3 Route visibility — excluded from the OpenAPI schema.**
`include_in_schema=False`. Generated frontend code never calls the route; URLs
arrive embedded in markdown or in a DTO field. Keeps the generated client
byte-identical between modes.

**6.4 Object key — raw, not opaque.** The signature makes tampering ineffective
either way, and the key is already visible in today's same-origin media URLs
(`/knowledge-flow/v1/markdown/{uid}/media/{file}`). Opacity here would be
decoration rather than a control.

## 7. Exit

When `iam.serviceAccounts.signBlob` is granted on the GCP deployment: set
`url_strategy: presigned` (or drop the field), redeploy. Nothing else changes —
no code, no frontend, no contract. Removing the feature entirely is then deleting
the field, the router factory, and the resolver's proxy branch.
