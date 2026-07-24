// Copyright Thales 2026
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

import type React from "react";
import { useParams } from "react-router-dom";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamWithPermissions } from "../slices/controlPlane/controlPlaneOpenApi";
import { PERSONAL_TEAM_COLOR, teamColor, type TeamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useFrontendBootstrap } from "./useFrontendBootstrap.ts";
import { useFrontendProperties } from "./useFrontendProperties.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";

export interface SelectedTeamState {
  /** The `:teamId` route param, verbatim (may be the `personal` alias). */
  teamId: string | undefined;
  isPersonalTeam: boolean;
  /** Full team once loaded; a permission-less bootstrap summary while the
   *  per-team fetch is in flight; `undefined` before either resolves. */
  selectedTeam: TeamWithPermissions | undefined;
  /** True only once permissions are loaded AND include team membership
   *  (AUTHZ-09: the settings entry point is open to every member, not just
   *  admins — sections within it are gated individually per role). */
  canOpenTeamSettings: boolean;
  /** Derived identity hue for the banner, or `null` until a name is known. */
  bannerColor: TeamColor | null;
  /** Ready-to-apply banner background/text style. */
  bannerStyle: React.CSSProperties;
}

/**
 * Single source of truth for "which team is the shell showing, and in what
 * colour". Shared by the second sidebar (`TeamContentNavbar`) and the routed
 * team-settings page so both render the same identity from the same derivation
 * — no duplicated selection logic, no chance of the two drifting apart.
 */
export function useSelectedTeam(): SelectedTeamState {
  const { teamId } = useParams<{ teamId: string }>();
  const { defaultPersonalBannerFile, defaultTeamBannerFile } = useFrontendProperties();
  const { activeTeam, availableTeams } = useFrontendBootstrap();

  // Identity is derived from the id shape (`personal-<uuid>`), not from a
  // comparison against the bootstrap-loaded activeTeam.id. On the very first
  // landing activeTeam is still loading, so the old comparison fell through to
  // the non-personal colour path and the banner rendered mustard instead of the
  // personal brand violet until the user switched teams and came back.
  const isPersonalTeam = isPersonalTeamId(teamId) || teamId === activeTeam?.id;

  const { data: team } = useGetTeamQuery({ teamId: teamId }, { skip: !teamId || isPersonalTeam });
  const bootstrapTeam = isPersonalTeam ? activeTeam : availableTeams.find((candidate) => candidate.id === teamId);
  const selectedTeam = isPersonalTeam ? activeTeam : (team ?? bootstrapTeam);

  const { canReadMembers: canOpenTeamSettings } = useTeamCapabilities(selectedTeam);

  // Banner hue is derived from the team name. Prefer the bootstrap-cached name
  // (present app-wide on the first paint) over the slower per-team fetch, and
  // never hash an empty string: teamColor("") returns a real but WRONG hue
  // (pale cold-green, PALETTE[0]) that reads as "uncoloured". That empty-string
  // fallback is what rendered on first connection until the per-team fetch
  // resolved — or the user switched teams and came back with a warm cache.
  // Until a name is known we render the neutral surface (bannerColor = null) so
  // the banner never flashes the wrong colour; personal space keeps its fixed
  // brand violet, which no longer depends on the async team fetch at all.
  const teamName = isPersonalTeam ? undefined : (bootstrapTeam?.name ?? selectedTeam?.name);
  const bannerColor = isPersonalTeam ? PERSONAL_TEAM_COLOR : teamName ? teamColor(teamName) : null;
  const defaultBannerFile = isPersonalTeam ? defaultPersonalBannerFile : defaultTeamBannerFile;
  const bannerImageUrl = selectedTeam?.banner_image_url ?? (defaultBannerFile ? `/images/${defaultBannerFile}` : null);
  // Keep the brand gradient as a base layer underneath the banner image so the
  // white banner text stays legible even when the configured image is missing.
  const bannerStyle = {
    backgroundImage: bannerColor
      ? bannerImageUrl
        ? `url(${bannerImageUrl}), ${bannerColor.banner}`
        : bannerColor.banner
      : undefined,
    color: bannerColor?.onSolid,
  } as React.CSSProperties;

  return { teamId, isPersonalTeam, selectedTeam, canOpenTeamSettings, bannerColor, bannerStyle };
}
