// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { createKeycloakInstance } from "../security/KeycloakService";
import type { FrontendConfig } from "../slices/controlPlane/controlPlaneOpenApi";
import { cachePlatformUiThemes, type PlatformUiThemes } from "../app/uiThemes.ts";

/** Public pre-auth control-plane config surface. */
const FRONTEND_CONFIG_URL = "/control-plane/v1/frontend/config";

/** Minimal auth config needed before the protected control-plane bootstrap call. */
export interface UserAuthConfig {
  enabled?: boolean;
  realm_url?: string;
  client_id?: string;
  provider?: "keycloak" | "oidc";
  scope?: string;
  user_directory?: "keycloak" | "local";
  uid_claim?: string;
  roles_claim?: string[] | null;
}

/** Final merged app config used by the UI before runtime bootstrap completes. */
export interface AppConfig {
  platform_access_enabled: boolean;
  supportLink: string | null;
  frontend_basename: string;
  feature_flags: Record<string, boolean>;
  properties: Record<string, string>;
  user_auth: UserAuthConfig;
  /**
   * Active Terms-of-Use / CGU version the deployment requires, or `null` when
   * gating is off. Sourced from the public pre-auth `/frontend/config` so the
   * GCU guard can decide before authentication — the authenticated bootstrap is
   * itself GCU-gated and cannot carry this value (chicken-and-egg).
   */
  gcu_version: string | null;
  /**
   * The authoritative frontend gating decision for `BootstrapGuard`: whether
   * root platform-admin bootstrap (AUTHZ-07) must still be shown. Sourced from
   * the public pre-auth `/frontend/config` so the guard can decide before
   * authentication (same chicken-and-egg as `gcu_version`). Deliberately not
   * the same as "has bootstrap ever completed" — on deployments where user
   * auth or ReBAC is disabled, `POST /bootstrap/platform-admin` can never
   * succeed, so this is `false` there even though the durable completion
   * marker is also `false`.
   */
  root_bootstrap_required: boolean;
  /** Platform default and hidden UI themes, or null when never saved (public pre-auth config). */
  ui_themes: PlatformUiThemes | null;
}

type RawAppConfig = {
  frontend_basename?: string;
  feature_flags?: Record<string, boolean>;
  properties?: Record<string, string>;
};

let config: AppConfig | null = null;

/**
 * Load the small pre-auth frontend configuration.
 *
 * Why this function exists:
 * - the migrated shell still needs a tiny static bootstrap before protected
 *   control-plane requests can run
 * - `frontend_basename` stays in `/config.json` (a pre-network static value),
 *   while the user-auth decision now comes from the public control-plane
 *   endpoint so the backend `security.user` config is the single source of
 *   truth and dev/secure mode no longer requires editing a static asset
 *
 * How to use it:
 * - call once during app startup before rendering React
 * - read the resolved values later through `getConfig()`
 *
 * Example:
 * - `await loadConfig();`
 */
export const loadConfig = async () => {
  const res = await fetch("/config.json");
  if (!res.ok) throw new Error(`Cannot load /config.json: ${res.status} ${res.statusText}`);

  const base = (await res.json()) as RawAppConfig;

  const { user_auth, gcu_version, root_bootstrap_required, ui_themes, platform_access_enabled, supportLink } =
    await loadPublicConfig();

  config = {
    frontend_basename: base.frontend_basename ?? "/",
    feature_flags: base.feature_flags ?? {},
    properties: base.properties ?? {},
    user_auth,
    platform_access_enabled,
    supportLink,
    gcu_version,
    root_bootstrap_required,
    ui_themes,
  };
  cachePlatformUiThemes(ui_themes);

  if (config.user_auth?.enabled) {
    const { realm_url, client_id } = config.user_auth;
    if (!realm_url || !client_id) {
      throw new Error("user_auth is enabled but realm_url or client_id is missing.");
    }
    createKeycloakInstance(realm_url, client_id, {
      provider: config.user_auth.provider,
      scope: config.user_auth.scope,
      user_directory: config.user_auth.user_directory,
      uid_claim: config.user_auth.uid_claim,
      roles_claim: config.user_auth.roles_claim,
      redirect_uri: new URL(config.frontend_basename || "/", window.location.origin).toString(),
    });
  }
};

/**
 * Fetch the public pre-auth control-plane config (`/frontend/config`).
 *
 * Why this function exists:
 * - the frontend must decide whether to initialize Keycloak before any login,
 *   so the auth flag is read from an unauthenticated control-plane endpoint
 *   rather than from a hand-edited `config.json`
 * - the active CGU version must likewise be known before authentication: the
 *   authenticated `/frontend/bootstrap` is GCU-gated (it 403s until the user
 *   accepts), so it cannot be the source of the version that decides whether to
 *   show the acceptance page (chicken-and-egg)
 *
 * How to use it:
 * - called by `loadConfig()` at Stage 0; failures abort startup like a missing
 *   `/config.json`, since the control-plane is required to run the app
 */
const loadPublicConfig = async (): Promise<
  Pick<
    AppConfig,
    "user_auth" | "gcu_version" | "root_bootstrap_required" | "ui_themes" | "platform_access_enabled" | "supportLink"
  >
> => {
  const res = await fetch(FRONTEND_CONFIG_URL);
  if (!res.ok) {
    throw new Error(`Cannot load ${FRONTEND_CONFIG_URL}: ${res.status} ${res.statusText}`);
  }
  const payload = (await res.json()) as FrontendConfig;
  return {
    user_auth: {
      enabled: payload.user_auth.enabled,
      realm_url: payload.user_auth.realm_url ?? undefined,
      client_id: payload.user_auth.client_id ?? undefined,
      provider: payload.user_auth.provider === "oidc" ? "oidc" : "keycloak",
      scope: payload.user_auth.scope ?? undefined,
      user_directory: payload.user_auth.user_directory === "local" ? "local" : "keycloak",
      uid_claim: payload.user_auth.uid_claim ?? "sub",
      roles_claim: payload.user_auth.roles_claim ?? null,
    },
    platform_access_enabled: payload.platform_access_enabled ?? false,
    supportLink: payload.supportLink ?? null,
    gcu_version: payload.gcu_version ?? null,
    // Rolling-compatibility fallback only: a control-plane deployed before
    // `root_bootstrap_required` existed omits the field, so this re-derives
    // the old (incorrect) predicate for that transition window. Once
    // `root_bootstrap_required` is present, it is always authoritative — the
    // frontend must not otherwise re-derive ReBAC/auth policy itself.
    root_bootstrap_required:
      payload.root_bootstrap_required ?? (payload.user_auth.enabled && !payload.root_bootstrap_completed),
    ui_themes: payload.ui_themes ?? null,
  };
};

/**
 * Return the already loaded static frontend configuration.
 *
 * Why this function exists:
 * - callers should not re-fetch `/config.json`
 * - the app startup path guarantees the config is loaded before use
 *
 * How to use it:
 * - call after `loadConfig()` has completed successfully
 *
 * Example:
 * - `const basename = getConfig().frontend_basename;`
 */
export const getConfig = (): AppConfig => {
  if (!config) throw new Error("Config not loaded yet. Call loadConfig() first.");
  return config;
};

/** Platform UI theme settings, or null before loadConfig() or when never saved. */
export const getPlatformUiThemes = (): PlatformUiThemes | null => config?.ui_themes ?? null;

/**
 * Read one static frontend property by key.
 *
 * Why this function exists:
 * - deployment branding lives in `/config.json` so it is available before
 *   authenticated control-plane bootstrap calls can complete
 *
 * How to use it:
 * - call after `loadConfig()` with the property name you need
 *
 * Example:
 * - `const logoName = getProperty("logoName");`
 */
export const getProperty = (key: string): string => getConfig().properties?.[key];

/**
 * Return the active Terms-of-Use / CGU version required by the deployment, or
 * `null` when gating is off.
 *
 * Why this function exists:
 * - the GCU guard must know the required version *before* authentication; the
 *   authenticated bootstrap is GCU-gated and cannot supply it (chicken-and-egg),
 *   so the value comes from the public pre-auth `/frontend/config`
 *
 * How to use it:
 * - call after `loadConfig()`; `null` means no acceptance screen is shown
 */
export const getGcuVersion = (): string | null => getConfig().gcu_version;

/**
 * Return whether root platform-admin bootstrap (AUTHZ-07) must still be shown.
 *
 * Why this function exists:
 * - `BootstrapGuard` must know this *before* authentication has produced any
 *   per-user state; the value is the backend's authoritative gating decision,
 *   not a per-user one, and not simply "has bootstrap ever completed" — it is
 *   also `false` on deployments where user auth or ReBAC is disabled, since
 *   `POST /bootstrap/platform-admin` can never succeed there
 *
 * How to use it:
 * - call after `loadConfig()`; `true` means the bootstrap screen must be shown
 */
export const getRootBootstrapRequired = (): boolean => getConfig().root_bootstrap_required;
