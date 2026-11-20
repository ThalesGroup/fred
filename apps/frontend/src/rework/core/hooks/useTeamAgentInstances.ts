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

import { useEffect, useRef, useState } from "react";
import {
  ManagedAgentInstanceSummary,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
} from "../../../slices/controlPlane/controlPlaneOpenApi";

export const PREPARING_POLL_MS = 5_000;
export const PREPARING_POLL_MAX_MS = 60_000;
export const PREPARING_POLL_BUDGET_MS = 10 * 60_000;

export function isPreparing(instance: ManagedAgentInstanceSummary): boolean {
  return instance.suspension_reason === "capability_pending" && !instance.suspension_detail;
}

/** Delay before the next listing: doubles from 5 s up to 60 s, and 0 (stop) once the budget is spent. */
export function preparingPollDelay(attempt: number, elapsedMs: number): number {
  if (elapsedMs >= PREPARING_POLL_BUDGET_MS) return 0;
  return Math.min(PREPARING_POLL_MS * 2 ** attempt, PREPARING_POLL_MAX_MS);
}

// The team agent list, re-polled with back-off while an agent is preparing: listing
// makes the control plane re-check readiness. `base` options apply when no poll runs.
export function useTeamAgentInstances(
  teamId: string | undefined,
  base?: { pollingInterval?: number; refetchOnMountOrArgChange?: number | boolean },
) {
  const [pollingInterval, setPollingInterval] = useState(0);
  const result = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId ?? "" },
    { ...base, skip: !teamId, pollingInterval: pollingInterval || base?.pollingInterval || 0 },
  );
  const preparingKey =
    result.data
      ?.filter(isPreparing)
      .map((instance) => instance.agent_instance_id)
      .sort()
      .join(",") ?? "";
  // A new set of preparing agents restarts the schedule; each new answer advances it.
  const schedule = useRef<{ key: string; startedAt: number; attempt: number; fetchedAt?: number }>({
    key: "",
    startedAt: 0,
    attempt: 0,
  });
  const fetchedAt = result.fulfilledTimeStamp;
  useEffect(() => {
    if (!preparingKey) {
      setPollingInterval(0);
      return;
    }
    const current = schedule.current;
    if (current.key !== preparingKey) {
      schedule.current = { key: preparingKey, startedAt: Date.now(), attempt: 0, fetchedAt };
    } else if (current.fetchedAt !== fetchedAt) {
      schedule.current = { ...current, attempt: current.attempt + 1, fetchedAt };
    }
    const { attempt, startedAt } = schedule.current;
    setPollingInterval(preparingPollDelay(attempt, Date.now() - startedAt));
  }, [preparingKey, fetchedAt]);
  return result;
}
