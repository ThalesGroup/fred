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
}

type RawAppConfig = {
  frontend_basename?: string;
  feature_flags?: Record<string, boolean>;
  properties?: Record<string, string>;
  user_auth?: UserAuthConfig;
};

export const FeatureFlagKey = {
  ENABLE_K8_FEATURES: "enableK8Features",
  ENABLE_ELEC_WARFARE: "enableElecWarfare",
} as const;
export type FeatureFlagKeyType = (typeof FeatureFlagKey)[keyof typeof FeatureFlagKey];

let config: AppConfig | null = null;

/**
 * Load the small pre-auth frontend configuration from `/config.json`.
 *
 * Why this function exists:
 * - the migrated shell still needs a tiny static bootstrap before protected
 *   control-plane requests can run
 * - this keeps basename and optional auth hints outside the application
 *   bootstrap payload
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

  config = {
    frontend_basename: base.frontend_basename ?? "/",
    feature_flags: base.feature_flags ?? {},
    properties: base.properties ?? {},
    user_auth: base.user_auth ?? { enabled: false },
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
