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
import {
  cachePlatformUiThemes,
  setCustomUiThemes,
  UI_THEMES,
  type CustomUiTheme,
  type PlatformUiThemes,
} from "../app/uiThemes.ts";

/** Public pre-auth manager configuration. */
const FRONTEND_CONFIG_URL = "/control-plane/v1/frontend/config";

/** Authentication settings needed before login. */
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

/** Branding-only keys the deployment theme may supply before login. */
const THEME_PROPERTY_KEYS = [
  "agentIconName",
  "agentsNicknamePlural",
  "agentsNicknameSingular",
  "contactSupportLink",
  "defaultPersonalAvatarFile",
  "defaultTeamAvatarFile",
  "faviconName",
  "faviconNameDark",
  "logoName",
  "logoNameDark",
  "releaseBrand",
  "siteDisplayName",
  "siteSubtitle",
  "siteTitle",
] as const;

async function loadThemeProperties(): Promise<Record<string, string>> {
  const response = await fetch("/theme-properties.json", { cache: "no-cache" });
  if (response.status === 404) return {};
  if (!response.ok) throw new Error(`Cannot load /theme-properties.json: ${response.status}`);
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Invalid theme properties");
  return Object.fromEntries(
    THEME_PROPERTY_KEYS.flatMap((key) =>
      typeof (payload as Record<string, unknown>)[key] === "string"
        ? [[key, (payload as Record<string, string>)[key]]]
        : [],
    ),
  );
}

async function loadThemeCatalog(): Promise<void> {
  const response = await fetch("/theme-catalog.json", { cache: "no-cache" });
  if (response.status === 404) {
    setCustomUiThemes([]);
    return;
  }
  if (!response.ok) throw new Error(`Cannot load /theme-catalog.json: ${response.status}`);
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Invalid theme catalog");
  const themes = (payload as { themes?: unknown }).themes;
  if (!Array.isArray(themes) || themes.length > 16) throw new Error("Invalid theme catalog");
  const ids = new Set<string>(UI_THEMES);
  for (const theme of themes as CustomUiTheme[]) {
    if (
      !theme ||
      typeof theme !== "object" ||
      typeof theme.id !== "string" ||
      !/^[a-z][a-z0-9-]{0,31}$/.test(theme.id) ||
      ids.has(theme.id) ||
      typeof theme.label !== "string" ||
      !theme.label.trim() ||
      theme.label.length > 80 ||
      !UI_THEMES.includes(theme.base)
    )
      throw new Error("Invalid theme catalog");
    ids.add(theme.id);
  }
  setCustomUiThemes(themes);
}

// Theme files are cosmetic: a broken one must leave the stock look, never block startup.
const ignoreThemeFile =
  <T,>(fallback: T) =>
  (error: unknown): T => {
    console.warn("Theme file ignored, using stock values:", error);
    return fallback;
  };

let config: AppConfig | null = null;

/** Load deployment branding and manager authentication settings before login. */
export const loadConfig = async () => {
  const res = await fetch("/config.json");
  if (!res.ok) throw new Error(`Cannot load /config.json: ${res.status} ${res.statusText}`);

  const base = (await res.json()) as RawAppConfig;

  const [{ user_auth, gcu_version, root_bootstrap_required, ui_themes, platform_access_enabled }, themeProperties] =
    await Promise.all([
      loadPublicConfig(),
      loadThemeProperties().catch(ignoreThemeFile({})),
      loadThemeCatalog().catch((error: unknown) => {
        setCustomUiThemes([]);
        ignoreThemeFile(undefined)(error);
      }),
    ]);

  config = {
    frontend_basename: base.frontend_basename ?? "/",
    feature_flags: base.feature_flags ?? {},
    properties: { ...base.properties, ...themeProperties },
    user_auth,
    platform_access_enabled,
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

/** Manager is the sole public configuration authority for this experimental entry. */
const loadPublicConfig = async (): Promise<
  Pick<AppConfig, "user_auth" | "gcu_version" | "root_bootstrap_required" | "ui_themes" | "platform_access_enabled">
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
      user_directory: "keycloak",
      uid_claim: payload.user_auth.uid_claim ?? "sub",
      roles_claim: payload.user_auth.roles_claim ?? null,
    },
    platform_access_enabled: false,
    gcu_version: payload.gcu_version ?? null,
    root_bootstrap_required: payload.root_bootstrap_required,
    ui_themes: null,
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
