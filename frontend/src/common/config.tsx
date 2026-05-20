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
  properties: Record<string, string>;
  user_auth: UserSecurity; // from OpenAPI types
  permissions: string[];
}

export type ConfigLoadFailureKind = "backend_unavailable" | "bootstrap_failed";

export interface ConfigLoadFailureDetails {
  kind: ConfigLoadFailureKind;
  url: string;
  status?: number;
  detail: string;
}

export const FeatureFlagKey = {
  ENABLE_K8_FEATURES: "enableK8Features",
  ENABLE_ELEC_WARFARE: "enableElecWarfare",
} as const;
export type FeatureFlagKeyType = (typeof FeatureFlagKey)[keyof typeof FeatureFlagKey];

let config: AppConfig | null = null;

class ConfigLoadError extends Error {
  readonly details: ConfigLoadFailureDetails;

  constructor(details: ConfigLoadFailureDetails) {
    super(details.detail);
    this.name = "ConfigLoadError";
    this.details = details;
  }
}

const BACKEND_UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

/**
 * Loads one JSON bootstrap dependency and upgrades transport failures into one typed startup error.
 *
 * The UI starts only after config bootstrap succeeds, so we need one place that converts
 * raw `fetch()` failures into actionable states for a startup fallback screen.
 *
 * Call it with the target URL and whether proxy/gateway failures should be treated as
 * temporary backend saturation instead of a generic bootstrap failure.
 *
 * Example:
 * `const settings = await fetchJsonOrThrow<FrontendConfigDto>("/agentic/v1/config/frontend_settings", { treatUnavailableAsBackendDown: true });`
 */
async function fetchJsonOrThrow<T>(
  url: string,
  options: {
    treatUnavailableAsBackendDown?: boolean;
  } = {},
): Promise<T> {
  const { treatUnavailableAsBackendDown = false } = options;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const isBackendUnavailable =
        treatUnavailableAsBackendDown && BACKEND_UNAVAILABLE_STATUSES.has(response.status);
      throw new ConfigLoadError({
        kind: isBackendUnavailable ? "backend_unavailable" : "bootstrap_failed",
        url,
        status: response.status,
        detail: `Cannot load ${url}: ${response.status} ${response.statusText}`,
      });
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ConfigLoadError) {
      throw error;
    }
    const detail = error instanceof Error ? error.message : `Unknown error while loading ${url}`;
    throw new ConfigLoadError({
      kind: treatUnavailableAsBackendDown ? "backend_unavailable" : "bootstrap_failed",
      url,
      detail,
    });
  }
}

/** Helpers to normalize typed DTO parts into simple records */
const normalizeFlags = (ff?: FrontendFlags): Record<string, boolean> => ({
  ...(ff?.enableK8Features !== undefined ? { enableK8Features: ff.enableK8Features } : {}),
  ...(ff?.enableElecWarfare !== undefined ? { enableElecWarfare: ff.enableElecWarfare } : {}),
});

const normalizeProps = (p?: Properties): Record<string, string> => {
  const out: Record<string, string> = {};
  if (p?.logoName !== undefined) out.logoName = String(p.logoName);
  if (p?.logoNameDark !== undefined) out.logoNameDark = String((p as any).logoNameDark);
  if (p?.siteDisplayName !== undefined) out.siteDisplayName = String((p as any).siteDisplayName);
  if ((p as any)?.releaseBrand !== undefined) out.releaseBrand = String((p as any).releaseBrand);
  if ((p as any)?.releaseCodename !== undefined) out.releaseCodename = String((p as any).releaseCodename);
  if ((p as any)?.logoHeight !== undefined) out.logoHeight = String((p as any).logoHeight);
  if ((p as any)?.logoWidth !== undefined) out.logoWidth = String((p as any).logoWidth);
  if ((p as any)?.faviconName !== undefined) out.faviconName = String((p as any).faviconName);
  if ((p as any)?.faviconNameDark !== undefined) out.faviconNameDark = String((p as any).faviconNameDark);
  return out;
};

/**
 * Loads /config.json for static settings, then queries backend /config/frontend_settings.
 * All API calls use relative URLs — the Vite proxy (dev) or nginx ingress (prod)
 * routes /agentic, /knowledge-flow, /control-plane to the correct backends.
 */
export const loadConfig = async () => {
  // 1) Static config (frontend_basename only)
  const base = await fetchJsonOrThrow<{
    frontend_basename: string;
  }>("/config.json");

  // 2) Dynamic config from backend (uses relative URL via proxy/ingress)
  const settings = await fetchJsonOrThrow<FrontendConfigDto>("/agentic/v1/config/frontend_settings", {
    treatUnavailableAsBackendDown: true,
  });

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

/**
 * Normalizes any startup failure into one render-safe shape for fatal bootstrap screens.
 *
 * The frontend startup runs before the router, auth context, and toast system exist,
 * so the entrypoint needs one small typed payload to render a dedicated fallback page.
 *
 * Call this inside `catch` blocks around `loadConfig()` or other bootstrap steps.
 *
 * Example:
 * `const failure = getConfigLoadFailureDetails(error);`
 */
export const getConfigLoadFailureDetails = (error: unknown): ConfigLoadFailureDetails => {
  if (error instanceof ConfigLoadError) {
    return error.details;
  }
  if (error instanceof Error) {
    return {
      kind: "bootstrap_failed",
      url: "bootstrap",
      detail: error.message,
    };
  }
  return {
    kind: "bootstrap_failed",
    url: "bootstrap",
    detail: "Unknown startup error",
  };
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
