---
schema: 1
title: "Make team avatars cacheable and stop shipping oversized images"
impact: none
configuration: none
configuration_reason: "No configuration key, default or chart value changes; the presigned-URL TTL requested by callers is unchanged."
no_action_reason: "Browser-cache and image-size optimisation only; stored avatars, the team API contract and the object-storage layout are untouched."
---
## Applicability

Existing Fred deployments upgrading to this release. The caching improvement
applies to deployments whose content storage is `minio` (MinIO / SeaweedFS /
S3). Deployments on `gcs` are unaffected — see Limitations.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

Three changes ship together, all aimed at how fast team avatars appear:

- **Presigned URLs are now stable and cacheable.** `MinioContentStore`
  previously signed every URL with the wall clock, so the same avatar got a
  different URL on each request and browsers could never reuse their cached
  copy. Signatures are now anchored to a fixed grid of a quarter of the
  requested TTL, and carry a `response-cache-control` override so the browser
  is told it may reuse the bytes. A minted URL still keeps at least three
  quarters of the TTL the caller asked for.
- **New avatars are exported at 320x320** instead of 512x512 by the in-app crop
  editor. 320 covers the largest consumer (the 96px settings preview) at 3x
  device pixel ratio; every other surface renders the avatar at 28-48px.
- **Avatar `<img>` tags declare their intrinsic size** and decode
  asynchronously, so the row keeps its layout while the image loads.

## Validation

Open the team list in the navigation panel on a deployment whose teams have
uploaded avatars, then reload the page. In the browser network panel, the
avatar requests should be served from the browser cache on the second load
rather than re-downloaded from object storage.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Avatars uploaded while the new export size is deployed stay valid after a
rollback — only their stored resolution differs.

## Limitations

- Avatars uploaded before this release keep their existing 512x512 bytes. They
  become cacheable like any other object, but are not re-encoded; they shrink
  only if a team admin re-uploads.
- The caching improvement does not reach the `gcs` content store. Its V4 signer
  takes no request timestamp, so it always stamps the current clock and mints a
  different URL per call. Making browser-facing GCS content cacheable requires
  the separate browser-facing URL strategy already tracked for that backend.
