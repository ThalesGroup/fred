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

import { useMemo } from "react";
import { getGcuVersion, getProperty } from "../common/config";
import { useFrontendBootstrap } from "./useFrontendBootstrap";

export interface FrontendProperties {
  agentIconName: string;
  agentsNicknamePlural: string;
  agentsNicknameSingular: string;
  contactSupportLink: string;
  defaultPersonalAvatarFile: string;
  defaultPersonalBannerFile: string;
  defaultTeamAvatarFile: string;
  defaultTeamBannerFile: string;
  faviconName: string;
  faviconNameDark: string;
  gcuVersion: string | null;
  logoName: string;
  logoNameDark: string;
  siteDisplayName: string;
  siteSubtitle: string;
  siteTitle: string;
}

/**
 * Expose frontend-facing labels and asset names from the static frontend config.
 *
 * Why this hook exists:
 * - branding must be available during the first render, before authenticated
 *   control-plane bootstrap calls can complete
 * - components need one stable property bag instead of reading `config.json`
 *   keys directly
 *
 * How to use it:
 * - call in UI components that need branding, labels, or asset names
 * - treat the returned values as always defined and ready for rendering
 *
 * Example:
 * - `const { siteDisplayName, agentIconName } = useFrontendProperties();`
 */
export function useFrontendProperties(): FrontendProperties {
  const { bootstrap } = useFrontendBootstrap();
  const ui = bootstrap?.ui_settings;

  return useMemo(
    () => ({
      agentIconName: getProperty("agentIconName") || "person",
      agentsNicknamePlural: ui?.agentsNicknamePlural || getProperty("agentsNicknamePlural") || "Agents",
      agentsNicknameSingular: ui?.agentsNicknameSingular || getProperty("agentsNicknameSingular") || "Agent",
      contactSupportLink: getProperty("contactSupportLink") || "",
      defaultPersonalAvatarFile: getProperty("defaultPersonalAvatarFile") || "",
      defaultPersonalBannerFile: getProperty("defaultPersonalBannerFile") || "",
      defaultTeamAvatarFile: getProperty("defaultTeamAvatarFile") || "",
      defaultTeamBannerFile: getProperty("defaultTeamBannerFile") || "",
      faviconName: getProperty("faviconName") || "fred",
      faviconNameDark: getProperty("faviconNameDark") || "fred-dark",
      // Sourced from the public pre-auth `/frontend/config` (via `getGcuVersion`),
      // never from the GCU-gated bootstrap — the bootstrap 403s until the user
      // accepts, which would hide the very version needed to render the
      // acceptance page (chicken-and-egg, FRONT-10). Static config stays as a
      // last-resort fallback.
      gcuVersion: getGcuVersion() ?? (getProperty("gcuVersion") || null),
      logoName: getProperty("logoName") || "fred",
      logoNameDark: getProperty("logoNameDark") || "fred-dark",
      siteDisplayName: ui?.siteDisplayName || getProperty("siteDisplayName") || "Fred",
      siteSubtitle: getProperty("siteSubtitle") || "",
      siteTitle: getProperty("siteTitle") || ui?.siteDisplayName || "Fred",
    }),
    // `gcuVersion` is read from the module-level pre-auth config which is loaded
    // once at startup and never changes during the app lifetime, so only `ui`
    // (from the bootstrap query) needs to drive recomputation.
    [ui],
  );
}
