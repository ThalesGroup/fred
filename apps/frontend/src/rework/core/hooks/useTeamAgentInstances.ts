import { useEffect, useState } from "react";
import {
  ManagedAgentInstanceSummary,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
} from "../../../slices/controlPlane/controlPlaneOpenApi";

export const PREPARING_POLL_MS = 5_000;

export function isPreparing(instance: ManagedAgentInstanceSummary): boolean {
  return instance.suspension_reason === "capability_pending" && !instance.suspension_detail;
}

// The team agent list, re-fetched while an agent is still preparing: listing is what
// makes the control plane re-check readiness, so the agent turns available on its own.
// `base` options (e.g. a cross-session refresh) apply whenever no preparing poll runs.
export function useTeamAgentInstances(
  teamId: string | undefined,
  base?: { pollingInterval?: number; refetchOnMountOrArgChange?: number | boolean },
) {
  const [pollingInterval, setPollingInterval] = useState(0);
  const result = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId ?? "" },
    { ...base, skip: !teamId, pollingInterval: pollingInterval || base?.pollingInterval || 0 },
  );
  const preparing = result.data?.some(isPreparing) ?? false;
  useEffect(() => setPollingInterval(preparing ? PREPARING_POLL_MS : 0), [preparing]);
  return result;
}
