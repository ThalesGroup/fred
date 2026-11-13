// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useState, type PropsWithChildren } from "react";
import { useWorkingOrganization } from "./useWorkingOrganization";
import { useSpaceAccess } from "./useSpaceAccess";

function useAccess() {
  const { memberships: context, organizationId: workingId, loading } = useWorkingOrganization();
  const organization = context.currentData?.find((space) => space.id === workingId && space.kind === "organization");
  const organizationId = organization?.id;
  const access = useSpaceAccess(organizationId, "administer_organization");
  const stamp = context.fulfilledTimeStamp;
  const check = `${organizationId}:${stamp}`;
  // A refused metric read revokes until the next context refresh rechecks.
  const [revoked, setRevoked] = useState<string>();
  const revoke = useCallback(() => setRevoked(check), [check]);
  return {
    memberships: context,
    organization,
    organizationId,
    allowed: !!organizationId && access.allowed && revoked !== check,
    offered: !!organizationId && access.offered,
    loading:
      !context.isError && (loading || context.isFetching || context.isLoading || (!!organizationId && !access.settled)),
    revoke,
    error: context.error || access.error,
    refresh: context.refetch,
  };
}

const AccessContext = createContext<ReturnType<typeof useAccess> | null>(null);

export function OrganizationSupervisionAccessProvider({ children }: PropsWithChildren) {
  const access = useAccess();
  return <AccessContext.Provider value={access}>{children}</AccessContext.Provider>;
}

export function useOrganizationSupervisionAccess() {
  const access = useContext(AccessContext);
  if (!access) throw new Error("Organization supervision access provider missing");
  return access;
}
