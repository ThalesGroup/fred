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

/** Public pre-auth control-plane config surface. */
const FRONTEND_CONFIG_URL = "/control-plane/v1/frontend/config";

/** Minimal auth config needed before the protected control-plane bootstrap call. */
export interface UserAuthConfig {
  enabled?: boolean;
  realm_url?: string;
  client_id?: string;
}

/** Final merged app config used by the UI before runtime bootstrap completes. */
export interface AppConfig {
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
}

type RawAppConfig = {
  frontend_basename?: string;
  feature_flags?: Record<string, boolean>;
  properties?: Record<string, string>;
};

export const FeatureFlagKey = {
  ENABLE_K8_FEATURES: "enableK8Features",
  ENABLE_ELEC_WARFARE: "enableElecWarfare",
} as const;
export type FeatureFlagKeyType = (typeof FeatureFlagKey)[keyof typeof FeatureFlagKey];

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

  const { user_auth, gcu_version } = await loadPublicConfig();

  config = {
    frontend_basename: base.frontend_basename ?? "/",
    feature_flags: base.feature_flags ?? {},
    properties: base.properties ?? {},
    user_auth,
    gcu_version,
  };

  if (config.user_auth?.enabled) {
    const { realm_url, client_id } = config.user_auth;
    if (!realm_url || !client_id) {
      throw new Error("user_auth is enabled but realm_url or client_id is missing.");
    }
    createKeycloakInstance(realm_url, client_id);
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
const loadPublicConfig = async (): Promise<{ user_auth: UserAuthConfig; gcu_version: string | null }> => {
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
    },
    gcu_version: payload.gcu_version ?? null,
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

/**
 * Read one pre-auth static feature flag by key.
 *
 * Why this function exists:
 * - a few startup decisions still read from the tiny static config before the
 *   control-plane bootstrap has hydrated the shell
 *
 * How to use it:
 * - call after `loadConfig()` and pass a `FeatureFlagKey` value
 *
 * Example:
 * - `const enabled = isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES);`
 */
export const isFeatureEnabled = (flag: FeatureFlagKeyType): boolean => !!getConfig().feature_flags?.[flag];

/**
 * Read one pre-auth static property by key.
 *
 * Why this function exists:
 * - the shell still keeps a tiny static fallback surface while the control-plane
 *   bootstrap query is loading
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
