# Fred Frontend

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
`/fred/agents/v2`, `/knowledge-flow`, and `/control-plane` to backend
upstreams.
The image defaults are cluster-friendly service DNS names
(`fred-agents`, `knowledge-flow-backend:8000`, `control-plane-backend:8222`).
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

Applications are not built into Fred. Each one is an independently built and
deployed UI container (optionally with its own API), registered in deployment
configuration. The frontend serves two prefixes for them, and the dev server
and the nginx container resolve both the same way:

| Prefix                    | Proxied to         | Seen by                       |
| ------------------------- | ------------------ | ----------------------------- |
| `/apps/<app_id>/`         | `ui_upstream`      | the browser, in the app frame |
| `/app-services/<app_id>/` | `service_upstream` | the app's own code            |

```bash
FRONTEND_ENABLE_APPLICATIONS=true \
FRONTEND_APPLICATIONS_JSON='[{"app_id":"acme-forecast","ui_upstream":"http://localhost:8300","service_upstream":"http://localhost:8301","service_required":true}]' \
make run
```

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
└── loadConfig() (async)
    └── Keycloak login
        └── render <FredUi />
              └── ApplicationContextProvider
                   └── AppWithTheme (sets [data-theme] light/dark/system on <html>)
                        └── AuthProvider
                             └── GcuGuard → BootstrapGuard
                                  ├── ConfirmationDialogProvider + ToastProvider
                                  └── RouterProvider (createBrowserRouter)
                                       └── LayoutWithSidebar
                                             ├── SideBar (toggle + cluster + theme)
                                             └── Outlet (all pages go here)
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

The frontend reads two configuration surfaces during startup:

| Surface                             | Owner                                           | Purpose                                                                                                                                                                                |
| ----------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/config.json`                      | frontend static asset / Helm frontend ConfigMap | Router base path, backend URLs, and static branding `properties` such as `siteDisplayName`, `siteTitle`, logos, favicons, agent nicknames, support links, and default avatars/banners. |
| `/control-plane/v1/frontend/config` | control-plane backend                           | Public pre-auth runtime settings derived from backend config: `user_auth` and `gcu_version`.                                                                                           |

Authenticated product state is separate: `/control-plane/v1/frontend/bootstrap`
returns current user, active team, visible teams, permissions, feature flags, and
the post-auth `gcu_version` mirror. It does **not** carry branding labels; do not
reintroduce `ui_settings` there. Branding belongs in `config.json.properties`.

### Security Configuration

The frontend decides whether to use real Keycloak or local dev tokens from the
public control-plane `/frontend/config` response **before** React renders:

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

**Important:** this is no longer a hand-edited frontend flag. The control-plane
derives it from backend `security.user`, the same configuration that drives API
JWT validation. For local dev it can be disabled there; for secure deployments it
must match the Keycloak/OIDC deployment.

In Kubernetes, frontend `config.json` is rendered from Helm values — no image
rebuild needed. Use it for static frontend settings and branding only; do not add
`user_auth` or control-plane `ui_settings` branding duplicates.

### Theme overlay (branding assets without a rebuild)

`config.json` selects assets by name, but the files themselves are baked into
the image. A deployment ships its own logos, favicons, default avatars, agent
icons and legal markdown as one **theme archive**: a zip laid out like
`public/`, fetched by the container at startup and served in place of the baked
files.

```
acme-theme-1.0.zip
├── images/acme-logo.svg             # new name, referenced from properties: logoName: "acme-logo"
├── images/icons/customAgent.svg     # agent icon silhouette (rendered as a CSS mask)
├── images/default-team-avatar.png   # same name as a stock file: shadows it
├── gcu.md  gcu.fr.md  gdpr.md  gdpr.fr.md
├── release.md
└── contrib/<brand>/...              # optional, the releaseBrand cascade still applies
```

Only `/images/**`, `/contrib/**` and root `*.md` files can be overridden;
`index.html`, `config.json` and the bundle never are. Symlinks are dropped and
an archive with entries escaping its root is refused. A zip made from a folder
(`zip -r acme-theme.zip acme-theme/`) is accepted: the wrapper folder is skipped.

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
  than overwriting a file in place. Markdown is fetched with `cache: no-cache`,
  so shadowing `gcu.md` in place is fine.
- A new `gcu.md` does not re-prompt users. Bump `gcu_version` in the
  control-plane configuration alongside it.
- The archive is applied at container start. After replacing the zip under the
  same name, restart the pods; pointing the URL at a new name rolls them.
- nginx does not listen until the fetch returns, so it gives up after ~16s to
  stay inside the default liveness window: an unreachable store costs a warning,
  not a crashloop. Add the startup probe from the example values for a store
  that is reachable but slow.

The archive is unpacked into `/var/lib/fred/theme`, outside the web root, and
nginx tries it before the baked file for the three surfaces above. Helm wiring
(the URL and the key from a Secret through `extraEnvVars`, plus an `emptyDir`
for a pod with a read-only root filesystem) is in
`deploy/charts/custom-values-examples/frontend-theme.yaml`.
`make theme-container-smoke` exercises the whole path against a locally built
image.

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
