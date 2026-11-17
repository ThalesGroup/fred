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

import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@hooks/crossSessionRefresh.ts";
import { useSpaceApplicationsQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements.ts";

/** One bounded, team-keyed subscription shared by the sidebar and app pages. */
export function useTeamApplications(teamId: string | undefined, skip = false) {
  const shouldSkip = skip || !teamId || teamId === "personal";
  // Security-sensitive catalog: a grant revoked in another session has to
  // replace an already-open app without waiting for the next poll.
  const result = useSpaceApplicationsQuery({ spaceId: teamId ?? "" }, crossSessionRefreshOptions(shouldSkip));
  useRefetchOnWindowFocus(result.refetch, shouldSkip);

  return { ...result, data: result.currentData };
}
