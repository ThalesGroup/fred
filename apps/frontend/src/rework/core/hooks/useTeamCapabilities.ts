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

import { useMemo } from "react";
import { mapTeamPermissions, type TeamCapabilities } from "./teamCapabilities";
import type { TeamWithPermissions } from "../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * Turn a `TeamWithPermissions` you already hold (from `useGetTeamQuery`,
 * `useSelectedTeam`, or a prop) into named capability booleans. Deliberately
 * takes the team object rather than a `teamId` and fetching it itself: every
 * call site already resolves its team through the RTK Query hook that fits
 * its own loading/caching needs (bootstrap-cached active team, a dedicated
 * `useGetTeamQuery`, a prop from a parent that already fetched it) — this
 * hook's only job is the one part that used to be duplicated everywhere,
 * turning `permissions: TeamPermission[]` into `canX: boolean`.
 */
export function useTeamCapabilities(team: TeamWithPermissions | null | undefined): TeamCapabilities {
  return useMemo(() => mapTeamPermissions(team?.permissions), [team]);
}
