// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";
import { KeyCloakService } from "../../../security/KeycloakService";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";
import { useSpaceAccess } from "./useSpaceAccess";

function useAccess() {
  const context = useMySpacesQuery(undefined, {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  const [selectedId, selectOrganization] = useLocalStorageState<string | undefined>(
    `admin.organization:${KeyCloakService.GetSessionIdentity()}`,
    undefined,
  );
  // Direct organization roles offer a context; platform and child-space roles grant none.
  const organizations = context.isError
    ? []
    : (context.currentData?.filter(
        (space) =>
          space.kind === "organization" &&
          (space.roles.includes("owner") || space.roles.includes("organization_admin")),
      ) ?? []);
  const organization = organizations.find((space) => space.id === selectedId) ?? organizations[0];
  const organizationId = organization?.id;
  // A stored preference is never authority. Replace revoked/unknown choices only
  // after a successful refresh, retaining the preference on transient failures.
  useEffect(() => {
    if (context.currentData && !context.isFetching && !context.isError && selectedId !== organizationId)
      selectOrganization(organizationId);
  }, [context.currentData, context.isFetching, context.isError, selectedId, organizationId, selectOrganization]);
  const access = useSpaceAccess(organizationId, "administer_organization");
  const stamp = context.fulfilledTimeStamp;
  const check = `${organizationId}:${stamp}`;
  // A refused metric read revokes until the next context refresh rechecks.
  const [revoked, setRevoked] = useState<string>();
  useRefetchOnWindowFocus(context.refetch, false);
  const revoke = useCallback(() => setRevoked(check), [check]);
  return {
    memberships: context,
    organizations,
    organization,
    selectOrganization,
    organizationId,
    allowed: !!organizationId && access.allowed && revoked !== check,
    offered: !!organizationId && access.offered,
    loading: !context.isError && (context.isFetching || context.isLoading || (!!organizationId && !access.settled)),
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
