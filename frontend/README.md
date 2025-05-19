# Fred Frontend

Fred frontend is a node React/Typescript application. It uses vite.js.

A makefile is available to help you compile package and run, with or without docker.
Note that the package-lock.json is generated from a dockerfile to avoid macos/linux issues with natives packages. It is then
committed to ensure all developers share the same configuration.


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

* **Dark/Light Theme**: Toggles dynamically using `ApplicationContext`
* **Sidebar Toggle**: Can be collapsed or hidden via `isSidebarCollapsed`
* **Cluster Navigation**: Sidebar reflects cluster state, query params updated
* **Feature Flags**: Routes are conditionally included via `isFeatureEnabled`
* **Config Loading**: `/config.json` is loaded before any routing occurs
* **Clean Routing**: Uses `createBrowserRouter` and `Outlet` pattern for clarity
* **Fully Modular**: Providers, theme, layout, and routes are decoupled and testable

### Best Practices Followed

* Single source of truth for theme and cluster state via `ApplicationContext`
* React Router v7 route-centric design using `createBrowserRouter`
* Dynamic route filtering using feature flags
* Layout separation (`LayoutWithSidebar`) with context-aware rendering
* Dynamic import of routes only after config load (avoids runtime crashes)

---

For teams using this structure, onboarding is faster, testing is easier, and feature gates (like Kubernetes or document-centric workflows) are cleanly separated from core logic.

> ✏️ To extend: add lazy-loading for pages, errorElement routes, or a public-only layout if login is skipped.


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
    ecmaVersion: 'latest',
    sourceType: 'module',
    project: ['./tsconfig.json', './tsconfig.node.json'],
    tsconfigRootDir: __dirname,
  },
}
```

- Replace `plugin:@typescript-eslint/recommended` to `plugin:@typescript-eslint/recommended-type-checked` or `plugin:@typescript-eslint/strict-type-checked`
- Optionally add `plugin:@typescript-eslint/stylistic-type-checked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and add `plugin:react/recommended` & `plugin:react/jsx-runtime` to the `extends` list
