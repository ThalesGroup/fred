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
`/agentic`, `/knowledge-flow`, and `/control-plane` to backend upstreams.
The image defaults are cluster-friendly service DNS names
(`agentic-backend`, `knowledge-flow-backend:8000`, `control-plane-backend:8222`).
`make docker-run` overrides those upstreams for local use and points them to
services running on the host through `host.docker.internal`.

Override the upstreams when your backends run elsewhere:

```bash
make docker-run \
  FRONTEND_DOCKER_NETWORK=fred-shared-network \
  FRONTEND_AGENTIC_UPSTREAM=http://agentic-backend:8000 \
  FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://knowledge-flow-backend:8111 \
  FRONTEND_CONTROL_PLANE_UPSTREAM=http://control-plane-backend:8222
```

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
              ├── ThemeProvider (dark/light via ApplicationContext)
              ├── RouterProvider (createBrowserRouter)
              ├── ToastProvider + ConfirmationDialogProvider
              └── ApplicationContextProvider
                   └── LayoutWithSidebar
                         ├── SideBar (toggle + cluster + theme)
                         └── Outlet (all pages go here)
```

### Component Responsibilities

| Component            | Responsibility                                                        |
| -------------------- | --------------------------------------------------------------------- |
| `index.tsx`          | Loads config, triggers Keycloak login, renders the root app component |
| `FredUi.tsx`         | Wraps all providers and initializes routing based on loaded config    |
| `ApplicationContext` | Holds global app state (cluster, theme, sidebar, namespaces, etc.)    |
| `ThemeProvider`      | Applies the MUI theme (light/dark) dynamically using context          |
| `RouterProvider`     | Powers the app's route tree using `createBrowserRouter()`             |
| `LayoutWithSidebar`  | Defines app layout with optional sidebar and main outlet              |
| `SideBar`            | Navigation + cluster selection + theme toggle                         |
| `Outlet`             | Displays the active page route                                        |

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

## Security Configuration

The frontend decides whether to use real Keycloak or local dev tokens by reading `frontend/public/config.json` **before** React renders.

```json
{
  "frontend_basename": "/",
  "user_auth": {
    "enabled": false,
    "realm_url": "http://keycloak:8080/realms/fred",
    "client_id": "fred-frontend"
  }
}
```

| Field | Effect |
|---|---|
| `user_auth.enabled: false` | No Keycloak. A local dev token is minted with `admin` role using `VITE_DEV_USERNAME` (defaults to your Unix username via `make run`). All auth code paths still execute — the app runs production-shaped. |
| `user_auth.enabled: true` | Full Keycloak OIDC PKCE flow. `realm_url` and `client_id` must match your deployment. |

**Important:** this is a frontend-only flag, independent of the backend `KEYCLOAK_ENABLED` env var. In a real deployment both must be `true`. For local dev both default to disabled.

In Kubernetes, `config.json` is rendered by `deploy/charts/fred/templates/configmap-frontend.yaml` from Helm values — no image rebuild needed. For local dev, edit `frontend/public/config.json` directly.

## Chat UI

The chat interface is built around the `rework/` component tree and communicates with agent pods via **SSE (Server-Sent Events)** — no WebSocket.

### Rich message rendering

Assistant messages are rendered by `rework/components/shared/molecules/MarkdownRenderer` which supports:

| Feature | Syntax |
|---|---|
| CommonMark + GFM tables, task lists, strikethrough | Standard markdown |
| Math (KaTeX) | `$inline$` and `$$block$$` |
| Mermaid diagrams | ` ```mermaid ` fenced blocks |
| Syntax-highlighted code | ` ```python `, ` ```typescript `, … |
| Collapsible sections | `:::details[Title] … :::` |
| Citation badges | `[1]`, `[2]`, … linked to source cards |

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
