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

// src/config/AppConfig.ts
// Copyright Thales 2025
// SPDX-License-Identifier: Apache-2.0

import { createKeycloakInstance } from "../security/KeycloakService";
import { KeyCloakService } from "../security/KeycloakService.ts";
import type { FrontendConfigDto, FrontendFlags, Properties, UserSecurity } from "../slices/agentic/agenticOpenApi";

/** Final merged app config used by the UI. */
export interface AppConfig {
  backend_url_api: string; // Base URL of the Agentic backend
  backend_url_knowledge: string; // Base URL of the Knowledge Flow backend
  websocket_url: string; // WebSocket server URL
  feature_flags: Record<string, boolean>;
  properties: Record<string, string>;
  user_auth: UserSecurity; // from OpenAPI types
  permissions: string[];
}

export const FeatureFlagKey = {
  ENABLE_K8_FEATURES: "enableK8Features",
  ENABLE_ELEC_WARFARE: "enableElecWarfare",
} as const;
export type FeatureFlagKeyType = (typeof FeatureFlagKey)[keyof typeof FeatureFlagKey];

let config: AppConfig | null = null;

/** Helpers to normalize typed DTO parts into simple records */
const normalizeFlags = (ff?: FrontendFlags): Record<string, boolean> => ({
  ...(ff?.enableK8Features !== undefined ? { enableK8Features: ff.enableK8Features } : {}),
  ...(ff?.enableElecWarfare !== undefined ? { enableElecWarfare: ff.enableElecWarfare } : {}),
});

const normalizeProps = (p?: Properties): Record<string, string> => {
  const out: Record<string, string> = {};
  if (p?.logoName !== undefined) out.logoName = String(p.logoName);
  return out;
};

/**
 * Loads /config.json then queries backend /config/frontend_settings (typed via OpenAPI).
 * Backend returns FrontendConfigDto: { frontend_settings: { feature_flags, properties }, user_auth }
 */
export const loadConfig = async () => {
  // 1) Static config
  const res = await fetch("/config.json");
  if (!res.ok) throw new Error(`Cannot load /config.json: ${res.status} ${res.statusText}`);
  const base = (await res.json()) as {
    backend_url_api: string;
    backend_url_knowledge: string;
    websocket_url: string;
  };

  // 2) Dynamic config (typed)
  const r = await fetch(`${base.backend_url_api}/agentic/v1/config/frontend_settings`);
  if (!r.ok) throw new Error(`Cannot load frontend settings: ${r.status} ${r.statusText}`);
  const settings = (await r.json()) as FrontendConfigDto;

  const frontend = settings.frontend_settings ?? { feature_flags: {}, properties: {} };

  // Assemble final config
  const feature_flags = normalizeFlags(frontend.feature_flags);
  const properties = normalizeProps(frontend.properties);

  config = {
    ...base,
    feature_flags,
    properties,
    user_auth: settings.user_auth,
    permissions: [],
  };

  // Initialize PKCE if enabled
  if (config.user_auth?.enabled) {
    const { realm_url, client_id } = config.user_auth;
    if (!realm_url || !client_id) {
      throw new Error("user_auth is enabled but realm_url or client_id is missing.");
    }
    createKeycloakInstance(realm_url, client_id);
  }
};

/** Accessor after loadConfig() */
export const getConfig = (): AppConfig => {
  if (!config) throw new Error("Config not loaded yet. Call loadConfig() first.");
  return config;
};

/** Feature flags helper */
export const isFeatureEnabled = (flag: FeatureFlagKeyType): boolean => !!getConfig().feature_flags?.[flag];

/** Properties helper */
export const getProperty = (key: string): string => getConfig().properties?.[key];

export const loadPermissions = async () => {
  try {
    const token = KeyCloakService.GetToken();
    if (!token) throw new Error("No Keycloak token available");

    const res = await fetch(`${getConfig().backend_url_api}/agentic/v1/config/permissions`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) throw new Error(`Cannot load permissions: ${res.status} ${res.statusText}`);
    const perms: string[] = await res.json();
    if (config) config.permissions = perms;
    return perms;
  } catch (err) {
    console.error("Failed to load user permissions:", err);
    if (config) config.permissions = [];
    return [];
  }
};
