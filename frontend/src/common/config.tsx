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
  frontend_basename: string; // Base name used by the frontend
  feature_flags: Record<string, boolean>;
  properties: Properties;
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

/**
 * Keeps the supported frontend properties provided by backend configuration.
 *
 * Why this exists:
 * - Several UI components read frontend settings during the first render.
 * - Copying each supported field explicitly avoids silently dropping config keys such as `agentsNicknamePlural`.
 *
 * How to use it:
 * - Pass the `frontend_settings.properties` payload from the backend.
 * - Read the returned object through `getConfig().properties` or `useFrontendProperties()`.
 *
 * Example:
 * - `const properties = normalizeProps(settings.frontend_settings.properties);`
 */
const normalizeProps = (p?: Properties): Properties => {
  const out: Properties = {};
  if (p?.logoName !== undefined) out.logoName = p.logoName;
  if (p?.logoNameDark !== undefined) out.logoNameDark = p.logoNameDark;
  if (p?.logoHeight !== undefined) out.logoHeight = p.logoHeight;
  if (p?.logoWidth !== undefined) out.logoWidth = p.logoWidth;
  if (p?.faviconName !== undefined) out.faviconName = p.faviconName;
  if (p?.faviconNameDark !== undefined) out.faviconNameDark = p.faviconNameDark;
  if (p?.siteDisplayName !== undefined) out.siteDisplayName = p.siteDisplayName;
  if (p?.siteTitle !== undefined) out.siteTitle = p.siteTitle;
  if (p?.siteSubtitle !== undefined) out.siteSubtitle = p.siteSubtitle;
  if (p?.releaseBrand !== undefined) out.releaseBrand = p.releaseBrand;
  if (p?.agentsNicknameSingular !== undefined) out.agentsNicknameSingular = p.agentsNicknameSingular;
  if (p?.agentsNicknamePlural !== undefined) out.agentsNicknamePlural = p.agentsNicknamePlural;
  if (p?.agentIconName !== undefined) out.agentIconName = p.agentIconName;
  if (p?.contactSupportLink !== undefined) out.contactSupportLink = p.contactSupportLink;
  if (p?.showAgentRestoreFromConfiguration !== undefined) {
    out.showAgentRestoreFromConfiguration = p.showAgentRestoreFromConfiguration;
  }
  if (p?.showAgentDisableButton !== undefined) out.showAgentDisableButton = p.showAgentDisableButton;
  if (p?.showAgentCode !== undefined) out.showAgentCode = p.showAgentCode;
  if (p?.allowAgentSwitchInOneConversation !== undefined) {
    out.allowAgentSwitchInOneConversation = p.allowAgentSwitchInOneConversation;
  }
  if (p?.defaultTeamBannerFile !== undefined) out.defaultTeamBannerFile = p.defaultTeamBannerFile;
  if (p?.defaultPersonalBannerFile !== undefined) out.defaultPersonalBannerFile = p.defaultPersonalBannerFile;
  if (p?.defaultTeamAvatarFile !== undefined) out.defaultTeamAvatarFile = p.defaultTeamAvatarFile;
  if (p?.defaultPersonalAvatarFile !== undefined) out.defaultPersonalAvatarFile = p.defaultPersonalAvatarFile;
  if (p?.gcuVersion !== undefined) out.gcuVersion = p.gcuVersion;
  if (p?.uploadWarning !== undefined) out.uploadWarning = p.uploadWarning;
  return out;
};

/**
 * Loads /config.json for static settings, then queries backend /config/frontend_settings.
 * All API calls use relative URLs — the Vite proxy (dev) or nginx ingress (prod)
 * routes /agentic, /knowledge-flow, /control-plane to the correct backends.
 */
export const loadConfig = async () => {
  // 1) Static config (frontend_basename only)
  const res = await fetch("/config.json");
  if (!res.ok) throw new Error(`Cannot load /config.json: ${res.status} ${res.statusText}`);
  const base = (await res.json()) as {
    frontend_basename: string;
  };

  // 2) Dynamic config from backend (uses relative URL via proxy/ingress)
  const r = await fetch("/agentic/v1/config/frontend_settings");
  if (!r.ok) throw new Error(`Cannot load frontend settings: ${r.status} ${r.statusText}`);
  const settings = (await r.json()) as FrontendConfigDto;

  const frontend = settings.frontend_settings;

  // Assemble final config
  const feature_flags = normalizeFlags(frontend.feature_flags);
  feature_flags.is_rebac_enabled = settings.is_rebac_enabled;

  const properties = normalizeProps(frontend.properties);

  config = {
    frontend_basename: base.frontend_basename,
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
export const getProperty = <K extends keyof Properties>(key: K): Properties[K] => getConfig().properties?.[key];

const normalizeBasename = (basename: string): string => {
  if (!basename || basename === "/") return "";
  return basename.endsWith("/") ? basename.slice(0, -1) : basename;
};

const redirectToComingSoon = () => {
  const base = normalizeBasename(getConfig().frontend_basename);
  const target = `${base}/coming-soon`;
  if (window.location.pathname !== target) {
    window.location.replace(target);
  }
};

export const loadPermissions = async () => {
  try {
    const token = KeyCloakService.GetToken();
    if (!token) throw new Error("No Keycloak token available");

    const res = await fetch("/agentic/v1/config/permissions", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      if (res.status === 403) {
        let detail: unknown = null;
        try {
          const body = await res.json();
          detail = body?.detail;
        } catch {
          detail = null;
        }
        if (typeof detail === "string" && detail.toLowerCase().includes("whitelist")) {
          redirectToComingSoon();
        }
      }
      throw new Error(`Cannot load permissions: ${res.status} ${res.statusText}`);
    }
    const perms: string[] = await res.json();
    if (config) config.permissions = perms;
    return perms;
  } catch (err) {
    console.error("Failed to load user permissions:", err);
    if (config) config.permissions = [];
    return [];
  }
};
