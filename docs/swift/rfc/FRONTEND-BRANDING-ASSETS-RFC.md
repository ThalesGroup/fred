# RFC: Per-deployment frontend branding assets synced from object storage (OPS-07)

**Status:** Proposed
**Author:** Simon Cariou
**Date:** 2026-07-23
**ID:** OPS-07
**Contract impact:** None — this design deliberately stays out of the frozen product
contract. Branding remains owned by the frontend static surface
(`CONTROL-PLANE-PRODUCT-CONTRACT.md §3.1`, decision #1850 "Move frontend branding
config out of control-plane bootstrap").

---

## 1. Problem

A deployment cannot customize the frontend's visual identity (favicon, logo,
default team banner, default team/personal avatar) without rebuilding the
frontend image.

Today:

- All branding binaries are baked into the nginx image at Vite build time:
  `apps/frontend/public/images/` (`fred.svg`, `fred-dark.svg`,
  `default-team-banner.png`, `default-team-avatar.png`, …) is copied into
  `dist/` and then into `/usr/share/nginx/html`
  (`apps/frontend/dockerfiles/Dockerfile-prod:43`).
- Asset *selection* is already runtime-configurable through the `properties`
  bag of `public/config.json` (`useFrontendProperties.ts:54-89`: `logoName`,
  `faviconName`, `defaultTeamBannerFile`, `defaultPersonalAvatarFile`, …),
  and deployments already override `config.json` via a ConfigMap mounted over
  the baked file (deployment factory `fred-frontend.yaml`, monorepo chart
  `configmap-frontend.yaml`).
- But the property values can only reference files **already present in the
  image** under `/images/`. There is no runtime override mechanism for
  `/images/*` in any chart. Changing a logo therefore means rebuilding and
  re-releasing the frontend image — disproportionate for a per-deployment
  branding swap.

The same limitation applies to the brandable text assets: the legal pages and
release notes already probe per-brand override paths under
`/contrib/<releaseBrand>/` (`gcu.<lang>.md`, `gcu.md`, `gdpr.<lang>.md`,
`gdpr.md`, `release.md`) — but no `public/contrib/` exists in the image, and
the only deployment mechanism today is a per-file legal ConfigMap (gcp-c1
`fred-frontend-legal`), which does not cover `release.md` and grows one mount
per file.

The need: let each deployment (fredlab, customer instances, …) provide its own
branding binaries **and per-brand markdown** from the platform's S3-compatible
object storage, without a frontend image rebuild and without touching the
frozen control-plane contract.

## 2. Proposed solution — init-container sync (ops-driven, no backend change)

At frontend pod startup, an **initContainer** syncs a dedicated object-storage
prefix into an `emptyDir` volume, mounted at **two new paths** inside the
nginx web root (one shared volume, two `subPath` mounts):

```
s3://<branding-bucket>/branding/
  ├── images/    ──sync──▶  <emptyDir>/images   ──mount──▶  /usr/share/nginx/html/images/custom/
  └── contrib/   ──sync──▶  <emptyDir>/contrib  ──mount──▶  /usr/share/nginx/html/contrib/
```

- Neither mount point exists in the image (`images/custom/` is new;
  `public/contrib/` is not shipped), so the baked default assets under
  `/images/` and the root `gcu.md`/`gdpr.md`/`release.md` remain untouched and
  keep working as fallbacks.
- nginx serves the synced files as plain static assets: pre-auth (favicon and
  loading-screen logo need no bearer token), normal browser caching, no URL
  TTL, no public exposure of the object-storage endpoint (the initContainer
  pulls from the *internal* S3 endpoint).
- `config.json` properties — already overridable per deployment via the
  existing ConfigMap — point at the synced files:

  ```json
  {
    "properties": {
      "logoName": "custom/acme-logo",
      "logoNameDark": "custom/acme-logo-dark",
      "faviconName": "custom/acme-favicon",
      "faviconNameDark": "custom/acme-favicon-dark",
      "defaultTeamBannerFile": "custom/team-banner.png",
      "defaultTeamAvatarFile": "custom/team-avatar.png",
      "defaultPersonalAvatarFile": "custom/personal-avatar.png"
    }
  }
  ```

  This works with **zero frontend code change**: consumers interpolate the
  property into a path (`/images/${file}` in `TeamCard.tsx`,
  `TeamSelectionNavbar.tsx`, `useSelectedTeam.ts`;
  `${baseUrl}images/${name}.svg` in `App.tsx`).

- Per-brand markdown works the same way through the **already-implemented**
  `/contrib/` probing: set `releaseBrand` in the properties and upload the
  files under `branding/contrib/<brand>/`.

### 2.0 Exact frontend fetch paths (verified 2026-07-23) — the sync MUST match these

The invariant this RFC guarantees: **object key ↔ property value ↔ URL ↔ file
on disk line up exactly.** Verified against the code:

| Asset | Property | URL built by the code (file:line) | File nginx must serve | Object key |
| --- | --- | --- | --- | --- |
| Loading-screen logo | `logoName` / `logoNameDark` | `${BASE_URL}images/<value>.svg` — `App.tsx:92` | `html/images/<value>.svg` | `branding/images/<name>.svg`, property = `custom/<name>` |
| Favicon (tab icon) | `faviconName` / `faviconNameDark` (fallback: `logoName*`) | `${BASE_URL}images/<value>.svg` — `App.tsx:137-138` | idem | idem |
| Default team banner | `defaultTeamBannerFile` / `defaultPersonalBannerFile` | `/images/<value>` — `TeamCard.tsx:75`, `useSelectedTeam.ts:76` | `html/images/<value>` | `branding/images/<file.ext>`, property = `custom/<file.ext>` |
| Default team/personal avatar | `defaultTeamAvatarFile` / `defaultPersonalAvatarFile` | `/images/<value>` — `TeamCard.tsx:88`, `TeamSelectionNavbar.tsx:63,85` | idem | idem |
| GCU (terms of use) | `releaseBrand` = `<brand>` | probes in order: `${base}/contrib/<brand>/gcu.<lang>.md` → `…/gcu.md` → `${base}/gcu.<lang>.md` → `${base}/gcu.md` — `GcuPage.tsx:52-54` | `html/contrib/<brand>/gcu[.<lang>].md` | `branding/contrib/<brand>/gcu[.<lang>].md` |
| GDPR page | `releaseBrand` | same candidate chain with `gdpr` — `GdprPage.tsx:41-43` | `html/contrib/<brand>/gdpr[.<lang>].md` | `branding/contrib/<brand>/gdpr[.<lang>].md` |
| Release notes (brand card) | `releaseBrand` | `${base}/release.md` **and** `${base}/contrib/<brand>/release.md` — `ReleaseNotesContent.tsx:77-80` | `html/contrib/<brand>/release.md` | `branding/contrib/<brand>/release.md` |

Notes on the table:

- **Nothing in the code references `images/custom/`.** The frontend reads
  `/images/<property value>` — the `custom/` segment travels *inside* the
  property value, unmodified: `getProperty` is a raw dictionary lookup with no
  sanitization (`config.tsx:201`), `useFrontendProperties` only applies
  `|| fallback` defaults, and every consumer does plain template
  interpolation. Full traced chain for one asset:
  `config.json properties.defaultTeamBannerFile = "custom/team-banner.png"`
  → `TeamCard.tsx:75` builds `/images/custom/team-banner.png`
  → nginx `root /usr/share/nginx/html` + `try_files $uri /index.html`
  (`docker-entrypoint.sh:39,85-87`) → file
  `/usr/share/nginx/html/images/custom/team-banner.png` = the emptyDir mount.
  **Consequence: updating the properties to include the `custom/` prefix is a
  mandatory part of enabling the feature** — syncing files alone changes
  nothing (by design: selection stays where it always was).
- **A wrong property value fails soft but ugly**: a URL under `/images/` that
  matches no file falls through `try_files` to `/index.html` and returns the
  SPA HTML with a 200 — a broken image (or broken favicon), not a 404. This
  is pre-existing behavior for any typo'd property; the ops doc must call it
  out because the sync adds a second way to get it wrong (file uploaded under
  a different name than the property says).
- `<lang>` is the two-letter i18n language (`fr`, `en` — `i18n.language`
  truncated at the `-`: `fr-FR` → `fr`); the language-suffixed file wins over
  the plain one, and `contrib/<brand>/` wins over the baked root files — the
  candidate chains are resolved sequentially, first non-null wins
  (`GcuPage.tsx:56-57`, `GdprPage.tsx:45-46`). The precedence is already in
  the code, nothing to add.
- **`<brand>` is the *slugified* `releaseBrand`, not the raw value** — all
  three consumers apply `trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-")`
  (`GcuPage.tsx:41-45`, `GdprPage.tsx:30-34`, `ReleaseNotesContent.tsx:67-74`)
  before building the path. `releaseBrand: "FredLab"` probes
  `contrib/fredlab/…`. The S3 folder name must match the **slug**; the ops doc
  must say "use a lowercase slug for both the property and the folder".
  Contrast with the image properties, which are raw, unsanitized lookups.
- The `/contrib/` candidates are only probed when the slug is non-empty
  (`GcuPage.tsx:52`); setting `releaseBrand` is therefore **mandatory** for
  the markdown overrides to activate.
- **The markdown chain is robust to missing files, unlike images**: every
  fetch rejects responses that look like the SPA shell
  (`!text.toLowerCase().includes("<!doctype")` — `GcuPage.tsx:49`,
  `GdprPage.tsx:38`; `ReleaseNotesContent.tsx:37-39` additionally checks
  `content-type` and `/@vite/client`), so the nginx `try_files → index.html`
  soft-404 is filtered out and the chain falls through to the next candidate /
  the baked root file. A missing or misnamed `.md` in the bucket degrades
  cleanly to the default text.
- Markdown fetches use `cache: "no-cache"` (`GcuPage.tsx:47`), so in-place
  updates of the `.md` files need no cache-busting (unlike images, §2.1).
- **GCU legal nuance — text and gate are two different levers.** The sync
  changes the *displayed* terms text only. Whether users must (re-)accept is
  driven by `gcu_version`, served pre-auth by the control plane
  (`/frontend/config`, FRONT-10) from its own configuration. A real terms
  change therefore requires **both**: upload the new
  `contrib/<brand>/gcu[.lang].md` *and* bump `gcu_version` in the
  control-plane config (gcp-c1: `controlPlane.config.gcuVersion`). Updating
  the markdown alone re-papers the page without re-prompting anyone — the ops
  doc must state this pairing explicitly.
- Pre-existing caveat, out of scope: the banner/avatar consumers build
  absolute `/images/…` URLs without the `BASE_URL` prefix (`TeamCard.tsx:75`),
  which already breaks under a non-root `frontend_basename`; this RFC neither
  fixes nor worsens that.

### 2.1 Constraints inherited from the current path templates

- **Logo and favicon must be SVG** — `App.tsx` appends `.svg` to `logoName` /
  `faviconName`. Accepted for now; the properties carrying a full filename
  (banners, avatars) take any supported format. Lifting the constraint would
  be a small, separate frontend change (accept full filenames with extension)
  and is out of scope here.
- **Applying a branding change requires a pod rollout** (`kubectl rollout
  restart`): both the ConfigMap subPath mount and the initContainer only take
  effect at pod start. Accepted: branding changes are rare, and this is the
  same cadence as every other deployment-config change.
- **Cache busting for images is by filename versioning** — operators should
  upload new versions under a new name (`custom/acme-logo-v2`) and update the
  property, rather than overwrite in place, to defeat stale browser caches.
  (Markdown overrides are exempt: they are fetched with `cache: "no-cache"`,
  see §2.0.)

### 2.2 Failure mode

The sync is **tolerant by default**: if the bucket is unreachable or the
prefix is empty, the initContainer logs a warning and exits 0, and the pod
starts with the baked default branding. A `strict: true` value flips it to
fail-fast for deployments where custom branding is mandatory. Rationale: a
branding asset must never take the product down.

### 2.3 Security

- The initContainer uses **read-only** credentials scoped to the branding
  bucket/prefix, injected from a Kubernetes Secret. This is the only new
  credential surface; the nginx container itself gets no S3 access.
- Everything under the branding prefix becomes **publicly served static
  content**. The prefix must contain nothing but branding assets; the ops doc
  must state this explicitly.

### 2.4 Chart surface (sketch)

New optional block, same shape in the monorepo chart
(`deploy/charts/fred/values.yaml`) and the deployment factory charts
(`gcp-c1/helm`, `gcp-c1/argocd`):

```yaml
fredFrontend:
  brandingSync:
    enabled: false
    # S3-compatible source (SeaweedFS, MinIO, GCS via interop/gsutil image)
    image: "minio/mc:<pinned>"
    endpoint: "http://fred-seaweedfs:8333"
    bucket: "fred-branding"
    prefix: "branding/"
    secretName: "fred-branding-s3"   # read-only access key/secret
    strict: false
```

The initContainer command is provider-neutral (`mc mirror` by default; a GCS
deployment can swap the image/command for `gsutil rsync` — the chart only
mandates "fill the emptyDir with the `images/` + `contrib/` layout"). The pod
mounts one shared `emptyDir` twice via `subPath`: `images` →
`/usr/share/nginx/html/images/custom`, `contrib` →
`/usr/share/nginx/html/contrib`. Docker-compose deployments get the equivalent
via a one-shot sync service sharing a named volume, or a plain bind mount.

### 2.5 Relationship to the existing legal ConfigMap

The gcp-c1 `fred-frontend-legal` ConfigMap (per-file mounts of
`gcu[.fr].md`/`gdpr[.fr].md` over the baked root files) keeps working but
becomes redundant for deployments using `brandingSync` + `releaseBrand`: the
`/contrib/<brand>/` candidates take precedence over the root files anyway
(§2.0). The deployment factory can migrate at its own pace; this RFC does not
remove the ConfigMap mechanism.

## 3. Alternatives considered

**B — Presigned URLs served by the control plane** (the existing *team banner*
pattern, `teams/service.py:1122-1136`). Rejected for *platform* branding:
1-hour TTLs are wrong for long-lived references (favicon, logo in an open
tab), rotating URLs defeat browser caching, the object-store public endpoint
must be exposed to browsers, and `LocalContentStore` cannot presign at all
(`local_content_store.py:89` — the current gcp-c1 control-plane storage is
`type: local`). Presigned stays the right answer for per-team, post-auth,
user-uploaded banners; it is the wrong tool for deployment branding.

**C — Control plane serves the bytes** (public `GET /frontend/branding/{slot}`
streaming from the content store with `ETag`/`Cache-Control`, plus admin
upload endpoints). Technically sound and the natural path if **self-service
branding from the product UI** ever becomes a requirement — but it reopens the
frozen contract (`§3.1.1` minimal pre-auth surface, `§3.9` "no binary through
the control plane"), requires a `get_object` read method on the fred-core
`ContentStore` protocol (3 implementations), and reverses the #1850 direction.
Deferred: option A does not preclude it — if C lands later, the upload side
writes to the same bucket prefix and A's serving path is simply replaced.

**D — ConfigMap `binaryData` mounted over `/images/*`.** Works for small SVGs
(≤ ~1 MiB per ConfigMap) and needs no S3, but does not scale to PNG banners,
multiplies per-file mounts, and creates a second mechanism next to the S3 one.
Kept as a degenerate fallback for deployments without object storage.

**Rebuild the image per brand.** Status quo; disproportionate cost per
deployment and couples branding to the release cycle.

## 4. Impact

| Surface | Change |
| --- | --- |
| Frontend code | **None** (SVG constraint accepted, §2.1; `/contrib/` probing already implemented) |
| Control-plane / backends | **None** |
| Frozen contracts | **None** — branding stays frontend-static (#1850, product contract §3.1) |
| `deploy/charts/fred` | New optional `brandingSync` initContainer + emptyDir (2 `subPath` mounts: `images/custom`, `contrib`) + Secret ref |
| Deployment factory (`gcp-c1/helm`, `gcp-c1/argocd`) | Same block; fredlab branding bucket + read-only creds; values wiring for `properties` (incl. `releaseBrand`); legal ConfigMap optionally retired (§2.5) |
| Docs | Ops guide (deployment factory): bucket layout (`images/` + `contrib/<brand>/`), the §2.0 mapping table, filename versioning, SVG constraint, public-content warning |

## 5. Verification

- `helm template` renders with `brandingSync.enabled: true/false` (both chart families).
- Local k3d + SeaweedFS: upload a test set (logo/favicon SVGs, banner/avatar
  PNGs, `contrib/<brand>/{gcu.md,gcu.fr.md,gdpr.md,release.md}`), deploy with
  the properties override (incl. `releaseBrand`), then verify against the §2.0
  table:
  - favicon + loading-screen logo pre-auth (before Keycloak login);
  - default banner/avatar fallback chain (custom → baked default → initials);
  - GCU/GDPR pages serve the brand + language variant, and the release-notes
    page shows the brand card next to the base one.
- Kill the S3 endpoint, restart the pod: tolerant mode boots with baked
  defaults (images **and** root gcu/gdpr/release fallbacks); strict mode
  blocks with a clear initContainer error.
