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

import { useGetSessionQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";

export function useConversationAvailability(
  spaceId: string,
  agentInstanceId: string,
  sessionId: string | null,
  locallyCreated: boolean,
) {
  const skip = !spaceId || !sessionId || locallyCreated;
  const query = useGetSessionQuery(
    { spaceId, sessionId: sessionId ?? "" },
    { ...crossSessionRefreshOptions(skip), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(query.refetch, skip);
  // RTK retains currentData after errors. A current refusal must hide that snapshot.
  const mismatch =
    !!query.currentData &&
    (query.currentData.space_id !== spaceId || query.currentData.agent_instance_id !== agentInstanceId);
  const sessionData = !skip && !query.isError && !mismatch ? query.currentData : undefined;
  const isReadOnly = sessionData?.agent_deleted === true;
  const executionDisabled =
    !spaceId ||
    isReadOnly ||
    sessionData?.agent_disabled === true ||
    Boolean(sessionId && !locallyCreated && (!sessionData || sessionData.agent_instance_id !== agentInstanceId));
  return {
    sessionData,
    isReadOnly,
    executionDisabled,
    sessionUnavailable: Boolean(sessionId && (query.isError || mismatch) && !locallyCreated),
    sessionErrorKey: mismatch
      ? "rework.weaverAgents.scopeUnavailable"
      : query.isError
        ? typeof query.error === "object" &&
          query.error &&
          "status" in query.error &&
          [401, 403, 404].includes(Number(query.error.status))
          ? "rework.weaverAgents.scopeUnavailable"
          : "rework.weaverAgents.errors.server"
        : undefined,
    historyRevision: query.fulfilledTimeStamp,
    refetchSession: () => {
      if (!skip) void query.refetch();
    },
  };
}
