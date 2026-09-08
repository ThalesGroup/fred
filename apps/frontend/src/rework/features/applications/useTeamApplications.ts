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

import { useEffect } from "react";
import { useFrontendFeatureFlag } from "@hooks/useFrontendFeatureFlag.ts";
import { useTeamApplicationsQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements.ts";

export const TEAM_APPLICATIONS_REFRESH_INTERVAL_MS = 60_000;

/** One bounded, team-keyed subscription shared by the sidebar and app pages. */
export function useTeamApplications(teamId: string | undefined, skip = false) {
  const { enabled: applicationsEnabled } = useFrontendFeatureFlag("enableApplications");
  const shouldSkip = !applicationsEnabled || skip || !teamId;
  const result = useTeamApplicationsQuery(
    { teamId: teamId ?? "" },
    {
      skip: shouldSkip,
      pollingInterval: shouldSkip ? 0 : TEAM_APPLICATIONS_REFRESH_INTERVAL_MS,
      refetchOnMountOrArgChange: TEAM_APPLICATIONS_REFRESH_INTERVAL_MS / 1000,
    },
  );

  // This store does not install RTK Query's global focus listeners. Keep the
  // security-sensitive catalog fresh explicitly so a grant revoked in another
  // session replaces an already-open app without waiting for the poll.
  useEffect(() => {
    if (shouldSkip || typeof window === "undefined") return;
    const refetchOnFocus = () => void result.refetch();
    window.addEventListener("focus", refetchOnFocus);
    return () => window.removeEventListener("focus", refetchOnFocus);
  }, [result.refetch, shouldSkip]);

  return result;
}
