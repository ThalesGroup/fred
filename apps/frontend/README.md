# Fred Frontend

On `weaver`, the [manager first-user journey](#manager-provisioning)
requires control-plane while preserving the complete existing UI. Non-migrated
features keep their existing service calls and ordinary loading/error states.

Fred frontend is a node React/Typescript application. It uses vite.js.

A makefile is available to help you compile package and run, with or without docker.
Note that the package-lock.json is generated from a dockerfile to avoid macos/linux issues with natives packages. It is then
committed to ensure all developers share the same configuration.

## Run the Dev Server

```bash
make run               # auto: split mode if 8111+8222 are reachable, else standalone mode
```

The Vite server starts on <http://localhost:5173> with hot module reload.

In standalone mode, frontend backend URLs are overridden at runtime by env vars,
so `frontend/public/config.json` does not need to be edited manually.

## Run the Production Docker Image

```bash
make docker-build
make docker-run
```

The production container serves static assets with nginx and now proxies
`/fred/agents/v2`, `/knowledge-flow`, `/control-plane` to backend
upstreams.
The image defaults are cluster-friendly service DNS names
(`fred-agents`, `knowledge-flow-backend:8000`, and `control-plane-backend:8222`
for both control-plane and manager routes).
`make docker-run` overrides those upstreams for local use and points them to
services running on the host through `host.docker.internal`.

Override the upstreams when your backends run elsewhere:

```bash
make docker-run \
  FRONTEND_DOCKER_NETWORK=fred-shared-network \
  FRONTEND_AGENTIC_UPSTREAM=http://fred-agents \
  FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://knowledge-flow-backend:8111 \
  FRONTEND_CONTROL_PLANE_UPSTREAM=http://control-plane-backend:8222
```

Production nginx writes escaped JSON access events to stdout: event time, status-derived
`severity` (`INFO`/`WARNING`/`ERROR`), local nginx request ID, method, bounded route
family, elapsed seconds and response bytes. Raw paths, queries, addresses,
request bodies and request headers are omitted. This proxy ID is local to nginx;
API response reference headers retain their own service identity.

Native nginx error/startup events and entrypoint theme/configuration messages
remain text on their existing streams. Native errors can contain request lines
and filesystem/upstream details; the access-log exclusions do not sanitize them.
Collector parsing and severity/timestamp promotion require a deployment canary;
see [observability guidance](../../docs/swift/platform/OBSERVABILITY-AND-AUDIT.md#63-frontend-pod-logs)
and the [migration guide](../../docs/swift/ops/migrations/structured-logging-frontend.md).
No browser telemetry or collector sidecar is introduced.

Applications are not built into Fred. Each one is an independently built and
deployed UI container (optionally with its own API), registered in deployment
configuration. The frontend serves two prefixes for them, and the dev server
and the nginx container resolve both the same way:

| Prefix                    | Proxied to         | Seen by                       |
| ------------------------- | ------------------ | ----------------------------- |
| `/apps/<app_id>/`         | `ui_upstream`      | the browser, in the app frame |
| `/app-services/<app_id>/` | `service_upstream` | the app's own code            |

```bash
cp config/.env.template config/.env
# Edit config/.env, then start Fred and the registered application upstreams.
make run
```

Frontend make commands load application gateway settings from `config/.env`
when it exists. The file is local-only and ignored by Git. An explicit shell
environment value or make command-line value takes precedence, so one-off
overrides remain available:

```bash
FRONTEND_ENABLE_APPLICATIONS=false make run
```

The template's `localhost` upstreams are for native `make run`. For
`make docker-run`, use addresses reachable from inside the container, such as
`host.docker.internal` for services running on the host.

The whole `/apps/<app_id>` prefix is forwarded upstream, so build the app's
bundle with that base path — its own absolute asset URLs then resolve back
through this route. `/app-services/<app_id>` is stripped instead, because the
app constructs those paths itself.

Trailing upstream slashes are normalized and unsafe URLs are rejected. An entry
with `service_required: true` and no `service_upstream` fails startup; omitting
`service_upstream` on a UI-only application is fine and its service path returns 503. Unknown ids return 404 in both namespaces. The list is consumed only by the
development server or container and is never returned to browser code. The
control-plane process must also have
`platform.frontend.feature_flags.enableApplications: true` and its own
`platform.application_sources` entry for the same `app_id`; the environment
variables above open only the local frontend gateway. Both sides default to
`false` and fail closed when omitted.

The application gateway accepts a positive nginx size in
`FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE`, defaults it to `10m`, and streams
request bodies to the selected service without nginx request buffering. Each
application service must still enforce its own, equal or smaller, request-body
and concurrency limits.

You can force the mode with:

```bash
make run FRONTEND_BACKEND_MODE=multi
make run FRONTEND_BACKEND_MODE=standalone
```

## UI Architecture Overview

### High-Level Flow

```text
index.tsx
`-- loadConfig() (async)
    `-- Keycloak login
        `-- render <FredUi />
              `-- ApplicationContextProvider
                   `-- AppWithTheme (sets [data-theme] light/dark/system on <html>)
                        `-- AuthProvider
                             `-- GcuGuard → BootstrapGuard
                                  |-- ConfirmationDialogProvider + ToastProvider
                                  `-- RouterProvider (createBrowserRouter)
                                       `-- LayoutWithSidebar
                                             |-- SideBar (toggle + cluster + theme)
                                             `-- Outlet (all pages go here)
```

### Component Responsibilities

| Component            | Responsibility                                                                                                         |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `index.tsx`          | Loads config, triggers Keycloak login, renders the root app component                                                  |
| `FredUi.tsx`         | Wraps all providers and initializes routing based on loaded config                                                     |
| `ApplicationContext` | Holds global app state (cluster, theme, sidebar, namespaces, etc.)                                                     |
| `AppWithTheme`       | Resolves light/dark/system to a `[data-theme]` attribute on `<html>`, read by CSS custom properties (no theme library) |
| `RouterProvider`     | Powers the app's route tree using `createBrowserRouter()`                                                              |
| `LayoutWithSidebar`  | Defines app layout with optional sidebar and main outlet                                                               |
| `SideBar`            | Navigation + cluster selection + theme toggle                                                                          |
| `Outlet`             | Displays the active page route                                                                                         |

### Key Features

- **Dark/Light Theme**: Toggles dynamically using `ApplicationContext`
- **Sidebar Toggle**: Can be collapsed or hidden via `isSidebarCollapsed`
- **Cluster Navigation**: Sidebar reflects cluster state, query params updated
- **Feature Flags**: Routes are conditionally included via `isFeatureEnabled`
- **Config Loading**: `/config.json` is loaded before any routing occurs
- **Clean Routing**: Uses `createBrowserRouter` and `Outlet` pattern for clarity
- **Fully Modular**: Providers, theme, layout, and routes are decoupled and testable

### Best Practices Followed

- Single source of truth for theme and cluster state via `ApplicationContext`
- React Router v7 route-centric design using `createBrowserRouter`
- Dynamic route filtering using feature flags
- Layout separation (`LayoutWithSidebar`) with context-aware rendering
- Dynamic import of routes only after config load (avoids runtime crashes)

---

For teams using this structure, onboarding is faster, testing is easier, and feature gates (like Kubernetes or document-centric workflows) are cleanly separated from core logic.

> ✏️ To extend: add lazy-loading for pages, errorElement routes, or a public-only layout if login is skipped.

## Configuration Surfaces

This branch retains the existing product routes under manager admission guards.
The profile/legal pages retain their standalone presentation.
The frontend reads two configuration surfaces during startup:

| Surface                             | Owner                                           | Purpose                                                                                                                                                                                |
| ----------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/config.json`                      | frontend static asset / Helm frontend ConfigMap | Router base path, backend URLs, and static branding `properties` such as `siteDisplayName`, `siteTitle`, logos, favicons, agent nicknames, support links, and default avatars/banners. |
| `/control-plane/v1/frontend/config` | control-plane                                   | Public pre-auth runtime settings derived from backend config: `user_auth` and `gcu_version`.                                                                                           |

Authenticated manager state comes from `/me/onboarding`, then `/me` and
`/me/spaces` after consent. The former control-plane product bootstrap is not
called by this entry. Branding remains in frontend assets.

### Security Configuration

The frontend decides whether to use real Keycloak or local dev tokens from the
public manager `/frontend/config` response **before** React renders:

```json
{
  "user_auth": {
    "enabled": false,
    "realm_url": "http://keycloak:8080/realms/fred",
    "client_id": "fred-frontend"
  },
  "gcu_version": null
}
```

| Field                      | Effect                                                                                                                                                                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user_auth.enabled: false` | No Keycloak. A local dev token is minted with `admin` role using `VITE_DEV_USERNAME` (defaults to your Unix username via `make run`). All auth code paths still execute — the app runs production-shaped. |
| `user_auth.enabled: true`  | Full Keycloak OIDC PKCE flow. `realm_url` and `client_id` must match your deployment.                                                                                                                     |

**Important:** this is no longer a hand-edited frontend flag. The manager
derives it from backend `security.user`, the same configuration that drives API
JWT validation. For local dev it can be disabled there; for secure deployments it
must match the Keycloak/OIDC deployment.

In Kubernetes, frontend `config.json` is rendered from Helm values — no image
rebuild needed. Use it for static frontend settings and branding only; do not add
`user_auth` or control-plane `ui_settings` branding duplicates.

### Theme overlay (branding assets without a rebuild)

The same ZIP loader runs in Docker and in the local Vite server. For local
development, set these values in `apps/frontend/config/.env` (copy the template
if needed), then run `make run` or the VS Code frontend / All Services PROD task:

```dotenv
FRONTEND_THEME_URL=http://localhost:8333/fred-themes/theme.zip
FRONTEND_THEME_S3_ACCESS_KEY=your-access-key
FRONTEND_THEME_S3_SECRET_KEY=your-secret-key
FRONTEND_THEME_REQUIRED=false
```

Omit both credential settings for a public object. `file:///absolute/path/theme.zip`
also works for a local archive. Shell environment values override `config/.env`.
Local startup requires `curl`, `unzip` and `jq`. Vite serves the validated theme
from a temporary directory ahead of stock assets and never changes `public/`.
After replacing a ZIP, restart the frontend and reload the browser; unset
`FRONTEND_THEME_URL` and restart to return to stock assets. Docker/k3d uses the
same environment settings with its reachable internal storage hostname.

`config.json` selects assets by name, but the files themselves are baked into
the image. A deployment ships its own logos, favicons, default avatars, agent
icons and legal markdown as one **theme archive**: a zip laid out like
`public/`, fetched by the container at startup and served in place of the baked
files.

```
acme-theme-1.0.zip
|-- theme-catalog.json               # selectable themes
|-- themes/
|   |-- acme/
|   |   |-- theme-custom.css          # CSS scoped to acme
|   |   `-- images/acme-logo.svg      # unique image name across the ZIP
|   `-- partner/
|       |-- theme-custom.css
|       `-- images/partner-logo.svg
`-- shared/
    |-- images/icons/customAgent.svg  # image available to every theme
    |-- theme-properties.json         # global branding labels and image names
    |-- theme-translations/en.json    # global English UI label overrides
    |-- theme-translations/fr.json    # global French UI label overrides
    |-- gcu.md  gcu.fr.md  gdpr.md  gdpr.fr.md
    |-- team-admin-charter.md  team-admin-charter.fr.md
    |-- release.md
    `-- contrib/<brand>/...           # optional releaseBrand content
```

The installer assembles theme folders into the same public URLs as before.
Image paths in CSS and catalog metadata still refer to `/images/`; image names
must be unique across theme folders and `shared/images/`. Existing flat ZIPs
remain supported. Only `/images/**`, `/contrib/**`, root `*.md`, `theme-custom.css`,
`theme-catalog.json`, `theme-properties.json` and `theme-translations/{en,fr}.json` can be overridden;
`index.html`, `config.json` and the bundle never are. Translation JSON can
override UI message keys; omitted keys keep the shipped text. Use CSS selectors such as
`html[data-ui-theme="pebble"][data-theme="light"]` to override any token in
Pebble, Cobalt or Cloud, including colors, fonts and radii. The JSON may set
these branding keys: `siteDisplayName`, `siteTitle`, `siteSubtitle`,
`agentsNicknameSingular`, `agentsNicknamePlural`, `logoName`, `logoNameDark`,
`faviconName`, `faviconNameDark`, `defaultTeamAvatarFile`,
`defaultPersonalAvatarFile`, `agentIconName`, `releaseBrand` and
`contactSupportLink`. It cannot change authentication, feature flags or the
frontend base path. See `theme/` for a working example. Symlinks are dropped and
an archive with entries escaping its root is refused. A zip made from a folder
(`zip -r acme-theme.zip acme-theme/`) is accepted: the wrapper folder is skipped.

To add selectable themes, put entries in `theme-catalog.json`:

```json
{
  "themes": [
    {
      "id": "acme",
      "label": "Acme",
      "base": "pebble",
      "tabTitle": "Acme Portal",
      "faviconName": "acme-icon",
      "faviconNameDark": "acme-icon-dark"
    },
    { "id": "partner", "label": "Partner", "base": "cloud" }
  ]
}
```

Each ID must be unique, lowercase and at most 32 characters; `base` is
`pebble`, `cobalt` or `cloud`. The base supplies all tokens, fonts and shapes.
The optional `tabTitle` (at most 200 characters) and `faviconName` /
`faviconNameDark` (SVG basenames under `images/`, letters, digits, `_` and `-`)
brand the browser tab while that theme is active; without them the tab keeps
`siteDisplayName` and the global favicon, and a missing dark icon reuses the
light one.
Add only the differences in `theme-custom.css`, using selectors such as
`[data-ui-theme="acme"][data-ui-base-theme="pebble"][data-theme="light"]`
and the matching `dark` selector. Include the base attribute so the ZIP rule
wins over the shipped CSS, which loads later. Color tokens always need all
three attributes, even to adjust a shipped theme
(`[data-ui-theme="cobalt"][data-ui-base-theme="cobalt"][data-theme="dark"]`);
only mode-independent rules such as fonts can omit `[data-theme]`. A flat ZIP
holding a root `themes/` or `shared/` directory is read as a structured one. Do not prefix these selectors
with `html`: the admin previews also
need to match them. ZIP themes appear in the profile picker and the admin theme settings,
where an admin can choose a default or hide a theme. Images and fonts placed in
the ZIP are shared assets; CSS can select different assets for each theme.
The chat also exposes `[data-chat-main]`, `[data-chat-welcome-agent]` and
`[data-chat-agent-icon]` for theme-specific backgrounds and avatars. Scope
these rules under `html[data-ui-theme="<id>"]` so other themes stay unchanged.

To change UI text, copy a key's nesting from `src/locales/fr/translation.json`
into `theme-translations/fr.json`, for example:

```json
{
  "rework": {
    "uiSettings": { "title": "Mon interface" }
  }
}
```

Use `theme-translations/en.json` for English. Only supplied keys change; the
rest keep their shipped translations. These overrides apply to the whole
deployment, whichever theme is selected: one ZIP carries one set of labels, and
themes in the same ZIP cannot have different labels. Rename "Agents" with the
agent nicknames in `theme-properties.json`. Use `theme-catalog.json` for each theme's display name and
`theme-properties.json` for shared brand labels and image names.

| Variable                                                        | Meaning                                                                                                                                                                                                                                  |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FRONTEND_THEME_URL`                                            | `https://` (public bucket, presigned URL, or plain S3 object URL) or `file://` (archive mounted from a ConfigMap or volume). Unset: feature off, nothing changes.                                                                        |
| `FRONTEND_THEME_S3_ACCESS_KEY` / `FRONTEND_THEME_S3_SECRET_KEY` | When both are set the request is SigV4-signed, so a private bucket on MinIO, SeaweedFS, AWS or GCS interop works with a plain object URL. The key the control-plane uses for its `content_storage` is enough; a read-only key is better. |
| `FRONTEND_THEME_S3_REGION`                                      | Default `us-east-1`; S3-compatible stores ignore it.                                                                                                                                                                                     |
| `FRONTEND_THEME_REQUIRED`                                       | `false` (default): a fetch or unpack failure logs one warning and the stock assets are served. `true`: the container exits.                                                                                                              |

Behaviour to keep in mind:

- Logo and favicon properties get `.svg` appended; avatars and banners carry
  their extension. A property pointing at a missing file renders a broken
  image, not a 404.
- Browsers cache images: ship a new file name and update the property rather
  than overwriting a file in place. Theme CSS and properties are requested with
  `no-cache`; translation JSON and Markdown are fetched with `no-cache` too.
- A new `gcu.md` does not re-prompt users. Bump `gcu_version` in the
  manager configuration alongside it.
- The archive is applied at container start. After replacing the zip under the
  same name, restart the pods; pointing the URL at a new name rolls them.
- nginx does not listen until the fetch returns, so it gives up after ~16s to
  stay inside the default liveness window: an unreachable store costs a warning,
  not a crashloop. A store that is reachable but slow needs a `startupProbe`,
  which holds the liveness probe off while the archive downloads.

The archive is unpacked into `/var/lib/fred/theme`, outside the web root, and
nginx tries it before the baked file for the supported surfaces above.

Helm wiring is values only, no chart template change:

```yaml
applications:
  frontend:
    extraEnvVars:
      - name: FRONTEND_THEME_URL
        value: "http://minio.data.svc.cluster.local:9000/fred-themes/acme-1.0.zip"
    # Only under readOnlyRootFilesystem: gives the overlay a writable home.
    extraVolumes:
      - name: theme
        emptyDir: { sizeLimit: 256Mi }
    extraVolumeMounts:
      - name: theme
        mountPath: /var/lib/fred/theme
```

**Prefer a prefix your store serves anonymously.** Every byte of the archive is
about to be served unauthenticated by nginx to every browser, so a credential
guarding the fetch protects nothing, and one fewer secret is one fewer thing to
rotate. Grant read on that one prefix and `FRONTEND_THEME_URL` is the whole
configuration. A presigned URL works the same way, until it expires.

When the store insists on authentication, add the two key variables and point
them at a Secret the deployment already has:

```yaml
- name: FRONTEND_THEME_S3_ACCESS_KEY
  valueFrom:
    secretKeyRef: { name: fred-secrets, key: S3_ACCESS_KEY, optional: true }
- name: FRONTEND_THEME_S3_SECRET_KEY
  valueFrom:
    secretKeyRef: { name: fred-secrets, key: S3_SECRET_KEY, optional: true }
```

The Fred chart also creates `s3-credentials` from the control-plane content
storage keys when `applications.frontend.extraEnvVars` configures
`FRONTEND_THEME_URL`. You can reference its `MINIO_ACCESS_KEY` and
`MINIO_SECRET_KEY` keys instead of the example Secret above. It is absent when
the URL is unset or an empty literal, the frontend is disabled, or either key is missing.

`optional: true` matters: without it a missing Secret leaves the pod unschedulable,
which is a hard failure for what is only branding. With it the fetch degrades to
anonymous and the baked assets are served.

The k3d values (fred-deployment-factory's `k3d-apps/fred/values.yaml`) use
`http://seaweedfs:8333/fred-themes/theme.zip`, reusing the stack chart's own
`fred-secrets`.
Upload a new ZIP to the `fred-themes/theme.zip` object in SeaweedFS, then
restart the frontend pods. For example, with an S3 client configured for your
SeaweedFS endpoint and credentials:

```sh
aws --endpoint-url "$SEAWEED_S3_ENDPOINT" s3 cp theme.zip s3://fred-themes/theme.zip
```

`make theme-bundle` packages `theme/` into `theme.zip`, ready to upload. That
directory is a complete working example - round logo and its dark variant, an
agent icon silhouette, a team avatar, and the four legal files - so the target
produces a verifiable archive out of the box; copy it and point `THEME_SRC` at
your own. Its `theme-properties.json` selects `acme-team-avatar.svg` and
`icons/customAgent.svg`; its catalog adds an Acme theme based on Pebble, and
`theme-custom.css` customizes Acme in both light and dark modes.

The target also flags the two layout mistakes that are hard to spot from a
running pod: entries outside the supported surfaces, and an English legal
file with no language variant beside it. `make theme-container-smoke` exercises the whole path against
a locally built image.

## Chat UI

The chat interface is built around the `rework/` component tree and communicates with agent pods via **SSE (Server-Sent Events)** — no WebSocket.

### Rich message rendering

Assistant messages are rendered by `rework/components/shared/molecules/MarkdownRenderer` which supports:

| Feature                                            | Syntax                                 |
| -------------------------------------------------- | -------------------------------------- |
| CommonMark + GFM tables, task lists, strikethrough | Standard markdown                      |
| Math (KaTeX)                                       | `$inline$` and `$$block$$`             |
| Mermaid diagrams                                   | ` ```mermaid ` fenced blocks           |
| Syntax-highlighted code                            | ` ```python `, ` ```typescript `, …    |
| Collapsible sections                               | `:::details[Title] … :::`              |
| Citation badges                                    | `[1]`, `[2]`, … linked to source cards |

### SSE transport

`rework/core/hooks/useChatSse.ts` handles the full SSE lifecycle:

- calls control-plane `/prepare-execution` to obtain a short-lived `ExecutionGrant`
- POSTs to the runtime `execute_stream_url` and parses `assistant_delta`, `final`, `tool_call`, `tool_result`, `awaiting_human`, `turn_persisted`, and `node_error` frames
- supports HITL resume via `sendHitlResume()`

## React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

### Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default {
  // other rules...
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    project: ["./tsconfig.json", "./tsconfig.node.json"],
    tsconfigRootDir: __dirname,
  },
};
```

- Replace `plugin:@typescript-eslint/recommended` to `plugin:@typescript-eslint/recommended-type-checked` or `plugin:@typescript-eslint/strict-type-checked`
- Optionally add `plugin:@typescript-eslint/stylistic-type-checked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and add `plugin:react/recommended` & `plugin:react/jsx-runtime` to the `extends` list

## API slices generations

To query our backends, we use [RTK Query](https://redux-toolkit.js.org/rtk-query/overview).
RTK Query hooks (and slices, types...) are generated automaticaly base on our OpenApi specs using [RTK Query code gen](https://redux-toolkit.js.org/rtk-query/usage/code-generation#openapi).

If you need to update one of them, just run one of the command while the corresponding backends is running

- Agentic backend:

  ```sh
  make update-agentic-api
  ```

- Knowledge Flow backend:

  ```sh
  make update-knowledge-flow-api
  ```

- Control Plane backend:

  ```sh
  make update-control-plane-api
  ```

- Fred Runtime:

  ```sh
  make update-runtime-api
  ```

## Manager provisioning

This experimental branch uses Fred's existing `App`, router, layout and sidebar
for manager public configuration, Keycloak login, personal CGU, root bootstrap,
team/personal navigation and `/admin/provisioning` in the administration console. The
generated manager slice is the authority for each step. Root has no implicit
space; imported users accept their own terms and select their declared
teams and projects using the existing team list. For business users, organization
information appears only in Profile; original product routes and non-migrated service
consumers remain mounted. Platform owners land on `/admin/organizations`, beside
Provisioning, and can create an organization with exact existing owner/admin usernames.
This area reuses team-administration components/styles and exposes no business
navigation, including for owners holding team roles. Shared account/preferences,
legal texts and static release notes remain available. The account menu remains
available before admission. The terms assets and `app.gcu_version` are deployed together.

Provisioning imports a ZIP synchronously and shows server counts only after
completion. Errors retain explicit replay guidance because effects can survive
failure. The browser test starts without a prepared root, simulates unavailable
non-migrated services and switches accounts in the same browser.

```sh
make update-control-plane-api       # offline Rust OpenAPI + generated RTK client
make install-test-browser         # install Chromium once
make test-provisioning-browser    # isolated real import journey and integration suite
```

Browser-test prerequisites and isolation are documented in the
[manager README](../control-plane/README.md#import-through-the-frontend).
For interactive development, Vite proxies `/control-plane` to `http://localhost:8222`;
`VITE_BACKEND_URL_CONTROL_PLANE` overrides this target. Production nginx uses
`FRONTEND_CONTROL_PLANE_UPSTREAM` (default `http://control-plane-backend:8222`).
It resolves that service at request time. Browser calls retain `/control-plane/v1`
and the bearer header in both cases.
