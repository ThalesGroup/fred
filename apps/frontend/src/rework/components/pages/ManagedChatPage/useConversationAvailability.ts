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

import { useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";

export function useConversationAvailability(
  teamId: string,
  agentInstanceId: string,
  sessionId: string | null,
  locallyCreated: boolean,
) {
  const skip = !teamId || !sessionId;
  const {
    currentData: sessionData,
    isError,
    refetch,
  } = useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery(
    { teamId, sessionId: sessionId ?? "" },
    crossSessionRefreshOptions(skip),
  );
  useRefetchOnWindowFocus(refetch, skip);
  const isReadOnly = sessionData?.agent_deleted === true;
  const executionDisabled =
    isReadOnly ||
    Boolean(
      sessionId &&
        ((!sessionData && !locallyCreated) || (sessionData && sessionData.agent_instance_id !== agentInstanceId)),
    );
  return {
    sessionData,
    isReadOnly,
    executionDisabled,
    sessionUnavailable: Boolean(sessionId && isError && !sessionData && !locallyCreated),
    refetchSession: () => {
      if (!skip) void refetch();
    },
  };
}
