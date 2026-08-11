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

import { useParams } from "react-router-dom";
import { useGetTeamQuery } from "../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamWithPermissions } from "../slices/controlPlane/controlPlaneOpenApi";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useFrontendBootstrap } from "./useFrontendBootstrap.ts";
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
}

/**
 * Single source of truth for "which team is the shell showing". Shared by the
 * second sidebar (`TeamContentNavbar`) and the routed team-settings page so both
 * resolve the same team from the same derivation — no duplicated selection
 * logic, no chance of the two drifting apart.
 */
export function useSelectedTeam(): SelectedTeamState {
  const { teamId } = useParams<{ teamId: string }>();
  const { activeTeam, availableTeams } = useFrontendBootstrap();

  // Identity is derived from the id shape (`personal-<uuid>`), not from a
  // comparison against the bootstrap-loaded activeTeam.id. On the very first
  // landing activeTeam is still loading, so the old comparison fell through to
  // the non-personal path until the user switched teams and came back.
  const isPersonalTeam = isPersonalTeamId(teamId) || teamId === activeTeam?.id;

  const { data: team } = useGetTeamQuery({ teamId: teamId }, { skip: !teamId || isPersonalTeam });
  const bootstrapTeam = isPersonalTeam ? activeTeam : availableTeams.find((candidate) => candidate.id === teamId);
  const selectedTeam = isPersonalTeam ? activeTeam : (team ?? bootstrapTeam);

  const { canReadMembers: canOpenTeamSettings } = useTeamCapabilities(selectedTeam);

  return { teamId, isPersonalTeam, selectedTeam, canOpenTeamSettings };
}
