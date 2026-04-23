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
import { getProperty } from "../common/config";
import { useFrontendBootstrap } from "./useFrontendBootstrap";

export interface FrontendProperties {
  agentIconName: string;
  agentsNicknamePlural: string;
  agentsNicknameSingular: string;
  allowAgentSwitchInOneConversation: boolean;
  defaultPersonalAvatarFile: string;
  defaultPersonalBannerFile: string;
  defaultTeamAvatarFile: string;
  defaultTeamBannerFile: string;
  faviconName: string;
  faviconNameDark: string;
  logoName: string;
  logoNameDark: string;
  siteDisplayName: string;
  siteSubtitle: string;
  siteTitle: string;
}

/**
 * Expose frontend-facing labels and asset names with control-plane bootstrap
 * as the primary source and static config/defaults as fallback.
 *
 * Why this hook exists:
 * - the shell is migrating away from the legacy agentic frontend-settings
 *   endpoint
 * - components still need a stable property bag while the control-plane
 *   bootstrap is loading
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
      agentIconName: getProperty("agentIconName") || "widgets",
      agentsNicknamePlural: ui?.agentsNicknamePlural || "Agents",
      agentsNicknameSingular: ui?.agentsNicknameSingular || "Agent",
      allowAgentSwitchInOneConversation: getProperty("allowAgentSwitchInOneConversation") === "true",
      defaultPersonalAvatarFile: getProperty("defaultPersonalAvatarFile") || "default-team-avatar.png",
      defaultPersonalBannerFile: getProperty("defaultPersonalBannerFile") || "default-team-banner.png",
      defaultTeamAvatarFile: getProperty("defaultTeamAvatarFile") || "default-team-avatar.png",
      defaultTeamBannerFile: getProperty("defaultTeamBannerFile") || "default-team-banner.png",
      faviconName: getProperty("faviconName") || "fred",
      faviconNameDark: getProperty("faviconNameDark") || "fred-dark",
      logoName: getProperty("logoName") || "fred",
      logoNameDark: getProperty("logoNameDark") || "fred-dark",
      siteDisplayName: ui?.siteDisplayName || getProperty("siteDisplayName") || "Fred",
      siteSubtitle: getProperty("siteSubtitle") || "",
      siteTitle: getProperty("siteTitle") || ui?.siteDisplayName || "Fred",
    }),
    [ui],
  );
}
