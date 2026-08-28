# RFC: Fred integrated applications

**Status:** Implemented for V1

**Author:** Fred platform team

**Area:** `control-plane-backend`, `frontend`, `fred-core`, `fred-sdk`, deployment

**Related docs:** [`CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md),
[`REBAC.md`](../platform/REBAC.md),
[`FRONTEND-AUTHZ-PATTERN.md`](../platform/FRONTEND-AUTHZ-PATTERN.md),
[`CONFIGURATION_AND_POLICY_CONVENTIONS.md`](../platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md),
[`FORKING_GUIDE.md`](../platform/FORKING_GUIDE.md)

---

## 1. Decision

Approve one generic extension point for integrating multiple product
applications into Fred as native, collaborative-team-scoped pages.

V1 defines:

1. Each installed application has one versioned, application-owned manifest.
   The same manifest input generates the control-plane catalog and the
   frontend's statically allowlisted lazy-loader registry.
2. Application admission reuses Fred's capability enablement. A manifest id
   `<application-id>` is represented by derived capability id
   `app__<application-id>` and catalog kind `app`.
3. Applications render under `/team/:teamId/apps/:appId/*`. Team identity is
   explicit in the URL and never inferred from browser state.
4. V1 modules are trusted, build-time React modules loaded inside the Fred
   shell. Iframes and runtime-loaded remote modules are outside V1.
5. Fred owns discovery, routing, shell context, and coarse admission. Each
   application owns its page content, API client, data, and server-side
   authorization.

### 1.1 V1 scope

V1 includes:

- strict manifest validation and deterministic generation of the frontend
  registry, control-plane catalog, locale resources, and container routing
  contract
- the `app` catalog kind, reserved `app__` namespace, collaborative-team
  permission, team-authorized application catalog endpoint, and platform-admin
  application controls
- a typed, deployment-wide `enableApplications` availability gate that is off
  by default and preserves installed manifests and grants while disabled
- the generic team routes, Apps index, authorization-first native module host,
  narrow host facade, relative navigation, authenticated request adapter,
  polling/focus refresh, and app-local failure containment
- matching application-service routing in local Vite and the deployed
  frontend's nginx container, with startup validation, upstream TLS
  verification, and container smoke coverage

The immutable generated catalog is the V1 installation record. Durable
registration tombstones, explicit same-id reactivation, and release lifecycle
management are outside V1 and follow the deferred contract in §7.4.

## 2. Problem

Fred has extension mechanisms for static fork content and independently
deployed backend runtimes, but no corresponding contract for a product
application that needs a first-class page in Fred.

Without a generic host, every integration would edit shared Fred code to add
routes, navigation, authorization, translations, Redux state, and API types.
That does not scale to multiple applications, creates merge conflicts in
forks, and encourages frontend-only flags that can drift from backend access.

The required abstraction is smaller than a general plugin platform: a typed
catalog, native route host, team entitlement, and narrow host API for trusted
applications.

## 3. Goals and non-goals

### 3.1 Goals

- integrate multiple applications without application-specific branches in
  Fred's router, navigation, authorization hooks, or shared store
- let platform administrators enable applications globally or per team through
  the existing Capabilities surface
- make team scope explicit and server-validated
- render native pages with Fred navigation, locale, theme, loading states, and
  error containment
- keep application UI, API models, translations, business objects, and data
  outside the generic host
- generate frontend and control-plane catalogs from one manifest source and
  fail closed on mismatch
- preserve a future path to independently deployed UI modules

### 3.2 Non-goals

V1 does not provide:

- an untrusted extension marketplace or arbitrary JavaScript URLs
- iframe hosting or runtime module federation
- personal-space or per-user application grants; V1 admission is scoped to
  collaborative teams
- application-specific object permissions or backend deployment lifecycle
- application secrets in manifests, frontend configuration, or capability
  settings
- dynamic Redux reducer or middleware injection
- a published frontend SDK before an external consumer needs one
- a replacement for agent, tool, model, or runtime capability contracts

## 4. Baseline and terminology

Fred's current constraints shape the design:

- the frontend has one static React Router table under one shell
- selected team identity comes from the `:teamId` URL parameter
- control-plane owns authenticated product metadata and generated frontend API
  types
- a platform administrator is not implicitly a member of every team
- capability `can_use` is checked with the **team** as subject, not the user
- the existing capability model already supports default-on, explicit team
  grants, team opt-out, personal scope, and platform-admin management
- the frontend is one private Vite package with lazy native pages, but no
  workspace package system or remote-module loader

Terms used below:

| Term            | Meaning                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| **Application** | A trusted product UI module rendered inside Fred, optionally backed by an application-owned service. |
| **Installed**   | A valid manifest and compatible frontend module exist in the deployed build.                         |
| **Enabled**     | The selected team has `can_use` on the derived application capability.                               |
| **Available**   | The application is installed, active, compatible, and enabled for the selected collaborative team.   |
| **Host**        | Fred-owned catalog and page code that resolves, admits, loads, and contains an application.          |
| **Host API**    | The narrow, versioned context Fred passes to an application module.                                  |

Installed and enabled are independent. A stale grant cannot resurrect an
uninstalled module, and installation never grants access by itself.

## 5. Proposed architecture

```text
                 one versioned manifest input
                              |
                 +------------+-------------+
                 |                          |
        generated frontend registry   control-plane app catalog
                 |                          |
                 |                    OpenFGA capability
                 |                    app__<application-id>
                 |                          |
                 +------------+-------------+
                              |
                 team-authorized app summary
                              |
            /team/:teamId/apps/:appId/*
                              |
                  Fred application host
                              |
                 lazy native app module
                              |
              constrained authenticated client
                              |
   /app-services/<application-id>/teams/<team-id>/...
```

| Concern                                                            | Owner               |
| ------------------------------------------------------------------ | ------------------- |
| Installed catalog, entitlement projection, team catalog API        | control-plane       |
| Route, navigation, module resolution, host context, error boundary | Fred frontend       |
| Page content, translations, state, API client, domain behavior     | application module  |
| Data authorization, objects, operations                            | application service |

Fred core must not branch on a concrete application id.

## 6. Manifest and catalog

### 6.1 Manifest

Each application supplies one manifest containing `schema_version`, a stable
`id` and semantic `version`, localized `display_name` and `description`
objects, a supported `icon`, `host_api_version`, `module_key`, and the boolean
`service_required` deployment contract.

Rules:

- `id` is a stable lowercase slug and must not be reused for a different app.
- `display_name` and `description` require an English fallback and may provide
  more locales.
- `icon` is a validated Fred-supported icon name, not raw SVG or HTML.
- `module_key` is resolved only by the build-time allowlist. It is never a
  server-provided import URL.
- `service_required` declares whether deployment must provide an application
  service mapping; it does not contain an upstream address.
- manifests contain no tokens, credentials, arbitrary headers, raw HTML, or
  executable URLs.

Fred derives rather than configures these values independently:

```text
capability id = app__<manifest.id>
page route    = /team/:teamId/apps/<manifest.id>
service root  = /app-services/<manifest.id>/teams/<team_id>/
```

The full capability id must pass Fred's capability-id validation. `app__` is
reserved for `kind="app"`; catalog ingestion rejects another kind using it.
The build derives stable i18n keys from the id, generates the frontend locale
resources, and projects those string keys into the existing capability
`name`/`description` fields. The shared fields do not change type.

### 6.2 One source, two generated consumers

V1 discovers packages only from this installation boundary:

```text
apps/applications/<application-id>/
├── fred-app.json
├── frontend/
│   ├── index.tsx
│   └── Application.module.css
└── backend/
    └── README.md
```

`frontend/index.tsx` has one default page export. The generator validates that
the package directory, manifest id, and module key agree, then emits a literal
dynamic import for each entry. The frontend build and TypeScript configuration
are extended once to include each package's `frontend/` directory; adding
another application changes no shared Fred source file. The optional `backend/`
directory is reserved for an independently built application service and is not
part of the frontend registry or control-plane catalog.

That explicit, allowlisted manifest set generates:

1. a frontend registry with statically analyzable lazy imports; and
2. a JSON catalog artifact packaged for control-plane.

Both outputs carry a catalog revision for diagnostics and a normalized
`contract_digest` per application. Neither is maintained by hand. At runtime
Fred renders only the intersection of:

- the control-plane application summary
- the local generated module registry
- matching per-app contract digest, application version, and host API version
- the selected team's current entitlement

A mismatch affects only that application, not the whole catalog. The host
records a diagnostic and does not load its code. Deployments either update the
two images atomically or accept a temporary unavailable state for the changed
application during a rolling update; an unrelated app remains usable.

Every newly installed V1 application is `admin_gated`. Installation or upgrade
never grants access. Application team settings are outside V1 and must not use
the existing generic capability-settings JSON, which is not a secrets store
and is read by agent-runtime paths applications do not use.

## 7. Authorization and control-plane contract

The backend-owned `enableApplications` feature gate precedes all application
admission and defaults to `false`. While disabled, application routes,
catalogs, administration controls, and service gateway paths fail closed;
generated modules remain bundled and existing grants remain dormant. The flag
controls availability, not authorization. When enabled, the checks below still
apply in full.

### 7.1 Reuse capability enablement

Extend the catalog discriminator to:

```text
tool | agent | model | app
```

An application has its own manifest projected into
`CapabilityCatalogEntry`; it does not use runtime `CapabilityManifest`, whose
routers, tables, state, and execution models describe agent behavior.

The current admin list and enable/disable/default-on/personal-scope routes
remain the only writers of capability relations. The admin Capabilities page
adds an **Apps** filter and reuses its existing default-on and team-matrix
controls.

V1 application rows do not offer the personal-scope control and exclude
personal teams from their team matrix. Catalog and service admission reject a
personal team even if `default_on` makes the underlying capability check true;
the V1 collaborative-team boundary is an additional ceiling.

Application entries are excluded from agent-instance dependency, impact,
suspension, revival, reasoning, and model-health calculations. Reusing the
tuple model does not mean running agent-specific orchestration for app toggles.

### 7.2 Team application catalog

Add:

```text
GET /control-plane/v1/teams/{team_id}/applications
```

```text
ApplicationList
  schema_version: "1"
  catalog_revision: string
  items: ApplicationSummary[]

ApplicationSummary
  id: string
  version: string
  name: string
  description: string
  icon: string
  host_api_version: string
  contract_digest: string
```

`name` and `description` are the deterministic i18n keys generated in §6.1.
The frontend registers their generated locale resources before rendering either
the team catalog or the admin capability list.

The endpoint first canonicalizes the team id and requires the caller's
`can_use_team_applications` permission. A non-member receives 403 before any
application metadata is evaluated. Personal teams are outside V1 and return no
applications. For a collaborative team, the endpoint returns only installed,
active, compatible applications for which that team currently has `can_use`.
Global admin fields such as all enabled team ids remain on the platform-admin
capability endpoint.

The catalog is fetched per route team, not placed in `FrontendBootstrap`,
which would be stale or ambiguous after a team switch.

### 7.3 Two independent admission checks

Add the team permission:

```text
team#can_use_team_applications = team_member
```

This is deliberately separate from `can_read`, which also admits public
non-members, and from agent-specific permissions.

Opening an application or its service requires:

```text
user can_use_team_applications on team:<team_id>
AND
team:<team_id> can_use capability:app__<app_id>
```

A platform administrator without team membership fails the first check.
Frontend hiding and route guards improve UX but do not authorize data.

Every application-service request uses the host-derived path
`/app-services/<app_id>/teams/<team_id>/<relative_path>`. The module cannot
override either id. The proxy strips only `/app-services/<app_id>` and preserves
the team-scoped remainder for the service.

The service independently validates the bearer, app id, collaborative team id,
membership permission, active installation, and entitlement. It uses Fred's
canonical capability authorization helper (or an exact equivalent that adds
the contextual `organization#team` edge); a raw context-free OpenFGA check is
not equivalent because it breaks default-on semantics. A proxy may route
requests but does not replace these checks.

The `app__<id>` capability is coarse admission only. Future object permissions
require a separately reviewed authorization contract.

### 7.4 Deferred removal lifecycle

Any future removal lifecycle must keep durable registration state keyed by
application id. A manifest seen previously and now absent becomes a tombstone; it is unavailable
even if OpenFGA grants remain, but stays visible to platform administrators for
cleanup.

If the same id reappears after being tombstoned, it enters
`pending_reactivation`. It cannot be listed to teams, loaded, proxied, or
enabled until a platform administrator clears or explicitly re-establishes its
structural capability relations and activates the new registration. A normal
version update that remains continuously installed does not create a new
generation or discard valid grants.

Normal uninstall is still two-stage: revoke/default-off access, verify no team
retains it, then remove the module and manifest. The tombstone path is the
fail-closed recovery for interrupted or out-of-order removal.

## 8. Native frontend host

### 8.1 Routes and navigation

Fred owns exactly two generic routes:

```text
/team/:teamId/apps
/team/:teamId/apps/:appId/*
```

Collaborative-team navigation contains one **Apps** entry, never one entry per
app. It is shown when the team has at least one available app; personal spaces
never show it. A direct visit with none renders a generic empty state.

The host resolves team membership and the authorized catalog before invoking
the lazy loader. Deep links cannot bypass this order. All deeper path segments
belong to the selected application.

Absence from the filtered catalog deliberately collapses unknown, uninstalled,
inactive, and not-entitled into one unavailable result. This avoids an
application-existence oracle. Missing local module, digest/version mismatch,
load failure, and render failure remain distinguishable only after the caller
has received an authorized catalog entry.

### 8.2 Registry and host API

The generated registry contains static loaders equivalent to:

```ts
interface FredApplicationRegistration {
  id: string;
  version: string;
  hostApiVersion: "1";
  contractDigest: string;
  load: () => Promise<{
    default: React.ComponentType<FredApplicationPageProps>;
  }>;
}
```

Registry construction rejects duplicate or invalid ids/module keys and
unsupported host versions. Control-plane never returns executable module
locations.

The application receives a narrow context:

```ts
interface FredApplicationPageProps {
  application: ApplicationSummary;
  context: {
    team: { id: string; name: string; isPersonal: boolean };
    route: {
      basePath: string;
      subPath: string;
      navigate: (relativePath: string, options?: { replace?: boolean }) => void;
    };
    locale: string;
    request: FredApplicationRequest;
  };
}
```

It does not receive Fred's Redux store, RTK slices, Keycloak object, raw
tokens, mutable internal contexts, unrestricted navigation, or arbitrary
authenticated fetch.

The request contract is fetch-compatible without exposing URL construction:

```ts
type FredApplicationRequest = (
  relativePath: string,
  init?: Pick<RequestInit, "method" | "headers" | "body" | "signal">,
) => Promise<Response>;
```

It normalizes a relative path under the host-derived
`/app-services/<app_id>/teams/<team_id>/` root and rejects schemes,
protocol-relative paths, traversal (including encoded traversal), and attempts
to override authorization, host, cookie, or Fred team headers. Method, safe
application headers, body, and `AbortSignal` pass through. `Response` preserves
JSON, multipart, binary, and streaming response support; network failures
reject, and non-auth HTTP statuses are returned for the app client to model.

The adapter owns current-token lookup, refresh, the normal single retry on
authentication expiry, and logout after a second authentication failure,
without returning the token to the module.

Applications own their generated domain clients on top of this injected
transport. V1 supports clients that accept a fetch-compatible function without
global Redux registration. Fred core does not register app-specific API slices,
reducers, middleware, DTOs, or endpoints.

Modules may use documented CSS custom properties and CSS Modules, but not
private Fred source imports or global selectors. A public component package can
be added later when more than one external consumer needs it.

V1 exposes its types and host-safe utilities through one public in-repository
facade, imported as `@fred/application-host`. Application modules may import
that facade and React only; the frontend coding guidelines must document this
application-directory and import-boundary exception.

### 8.3 Failure containment

Each app mounts inside app-local lazy-loading and error boundaries. The host
distinguishes catalog loading, generic unavailability, local digest/version
mismatch, module-load failure, and render failure. Ordinary non-auth service
responses, including gateway 502/503 responses, remain `Response` values for
the application client to model; they do not make the Fred host replace the
page with a host-owned service-unavailable state.

One app failure must not unmount Fred's shell or another app. Local enablement
mutations invalidate the catalog immediately. Changes made elsewhere are picked
up on window focus and by bounded polling no slower than 60 seconds; the app
service enforces revocation immediately on every request. Once refetched, the
host replaces an open page with the generic unavailable state. A previously
loaded chunk is not evidence of continuing permission.

## 9. Security, packaging, and evolution

### 9.1 Trusted native code

A native module executes with Fred's browser-origin privileges. V1 therefore
accepts only reviewed build-time modules and is not a sandbox. App packages
pass the same dependency, license, build, and review gates as Fred frontend
code.

V1 modules are part of Fred's frontend bundle, so the existing same-origin
script policy remains sufficient. Manifests cannot widen CSP or add script,
frame, or network origins. They and their logs contain no credentials, tokens,
application payloads, or unnecessary user data.

If untrusted code becomes a requirement, an isolation boundary such as a
sandboxed iframe must be reconsidered. A remote native module is not a security
boundary.

### 9.2 V1 packaging and forks

V1 uses lazy build-time imports from each application package's `frontend/`
directory. Adding an application requires its isolated package and manifest,
inclusion in the explicit build input, optional same-origin service ingress,
matching frontend and control-plane per-app contract digests, and
platform-admin enablement. A service-backed package may place an independently
built implementation under `backend/`; that service is not compiled into the
Fred frontend.

The included placeholder package is service-free: its manifest sets
`service_required` to `false`, and its `backend/` directory contains
documentation rather than runtime code or build configuration.

Deployment configuration owns a server-side map from installed application id
to service upstream; upstream URLs are never returned to the browser. At
startup, the container validates that every `service_required` app has exactly
one mapping. The frontend's nginx server and local Vite expose
the same public prefix, `/app-services/<app_id>/`, strip only that prefix, and
preserve `/teams/<team_id>/<relative_path>` to the upstream. Unknown ids fail
closed. A missing or unhealthy optional upstream returns a generic 502/503 and
must not prevent the Fred shell from starting.

It must not require app-specific edits to Fred's router, sidebar, auth hooks,
generated control-plane client, or store. It provides source isolation but not
an independent UI release cadence: changing a bundled module rebuilds Fred's
frontend image.

The forking guide documents this supported extension path. The browser contract
may be extracted into a publishable TypeScript package only when an independently
built consumer needs it; that package must expose the narrow host API, not Fred
internals.

### 9.3 Future independent deployment

The manifest, catalog, routes, capability id, and host API are loader-neutral.
A future loader may resolve an immutable remote module behind the same
registration contract, but requires a separate decision covering allowlisted
origins, integrity, CSP, dependency singletons, host-version negotiation,
rollback, outages, and cross-origin credentials.

V1 must not accept an arbitrary URL in anticipation of that future.

## 10. Impact on existing contracts

| Contract                       | Required change                                                                                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Control-plane product contract | Catalog models, `GET /teams/{team_id}/applications`, and app-specific impact exclusions are implemented; durable registration/tombstone state is deferred. |
| Capability wire contract       | Add `app` to the kind discriminator and reserve `app__`.                                                                                    |
| OpenFGA/team permissions       | Reuse capability unchanged; add `can_use_team_applications` for membership admission.                                                       |
| Frontend authorization pattern | Document the team-aware host gate while retaining backend enforcement.                                                                      |
| Frontend coding guidelines     | Define the application directory and `@fred/application-host` public import boundary.                                                       |
| Frontend routing               | Add the two generic team routes and one generic navigation item.                                                                            |
| Generated frontend API         | Regenerate from control-plane OpenAPI; add no handwritten catalog DTOs.                                                                     |
| Configuration conventions      | Define the non-secret manifest/catalog input and deployment ownership.                                                                      |
| Forking guide                  | Document package/manifest installation without core source edits.                                                                           |
| Deployment                     | Package matching catalog artifacts and verify wildcard deep links and optional service ingress.                                             |

No runtime execution, agent messaging, chat transport, model routing,
document, or application-domain contract is changed by this RFC.

## 11. Alternatives considered

### Hardcode each app in Fred

Rejected: it duplicates shared routing, navigation, auth, translations, and
state integration and forces forks to edit Fred source.

### Frontend-only flags

Rejected: hidden UI is not authorization and a separate flag store would drift
from OpenFGA enablement.

### Reuse runtime `CapabilityManifest`

Rejected: it describes agent-runtime behavior, not native product UI modules.
Applications project their own manifest into the shared entitlement catalog.

### Use `/apps/:appId` with an implicit team

Rejected: Fred derives selected team from the URL, so implicit state makes deep
links ambiguous and can check the wrong team's entitlement.

### Iframe every app

Not selected for V1: it gives stronger isolation but splits routing, theme,
focus, sizing, accessibility, and authentication. It remains appropriate for
untrusted code.

### Load remote modules immediately

Deferred: independent releases are attractive, but the current build has no
loader or package-sharing contract, and remote native code still has Fred-origin
privileges.

### Give apps a separate entitlement system

Rejected for coarse admission: Fred's capability model already provides the
required platform and team semantics. Fine-grained app permissions remain an
app-service concern.

## 12. Validation, rollout, and acceptance

Minimum automated coverage:

- manifest validation, duplicate ids, derived namespace, locale/icon fallback,
  and executable-URL rejection
- generated frontend/control-plane per-app digest/version parity and isolation
  of one rolling-update mismatch to that app
- authorization matrix covering member/entitled/installed independently,
  including a platform admin without team membership
- default-on, opt-out, the collaborative-team ceiling, live revocation, and
  stale-grant cleanup
- registry uniqueness, host-version rejection, and no module load before
  authorization succeeds
- wildcard subpaths and relative navigation cannot escape the app route
- request adapter team-path derivation, traversal/absolute-URL rejection,
  protected-header stripping, cancellation, binary, multipart, and streaming
  behavior
- missing module, load error, and render error are host-contained; ordinary
  non-auth service errors remain application-owned and do not unmount the Fred
  shell
- deployed frontend image deep links, basename-aware chunk loading, same-origin
  service path preservation/stripping, required-upstream validation, and
  unchanged bundled-mode CSP

Required authorization outcomes:

| Team member         | Team entitled | Installed | Result                    |
| ------------------- | ------------- | --------- | ------------------------- |
| yes                 | yes           | yes       | allowed                   |
| yes                 | no            | yes       | denied                    |
| no                  | yes           | yes       | denied                    |
| yes                 | yes           | no        | denied                    |
| platform admin only | yes           | yes       | denied without membership |

Acceptance additionally requires that Fred core contain no concrete app id,
domain type, or business permission; another placeholder app can be registered
without changing shared router/navigation/auth/store code; app code receives no
raw token or private Fred state; and a stale grant cannot restore a removed
app.

Validation starts with placeholder manifests, capability/catalog contracts, and
the generic host, followed by administration controls and container-level
checks. Its durable contract is summarized in the design and platform docs and
the forking guide. Application-specific integrations remain outside this RFC.

## 13. Deferred decisions

Evidence from multiple independently developed applications is required before standardizing:

1. personal-space application availability and its interaction with the
   existing personal capability class
2. an npm workspace or standalone TypeScript application-host package
3. an independently deployed native-module loader and technology choice
4. typed, non-secret per-team app configuration beyond enablement
5. application-service health in control-plane versus existing operational
   health surfaces

If this RFC is accepted, those follow-ups must reuse its identifiers, team
scope, authorization checks, and host-version boundary rather than creating
parallel registries.
