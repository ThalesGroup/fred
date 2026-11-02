// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { useAuthorizeSpaceMutation, useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";
import { KeyCloakService } from "../../../security/KeycloakService";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";

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
  const [authorize] = useAuthorizeSpaceMutation();
  const [decision, setDecision] = useState<{
    organizationId: string;
    stamp: number;
    allowed: boolean;
    error?: unknown;
  }>();
  const stamp = context.fulfilledTimeStamp;

  useEffect(() => {
    // Do not reuse A's decision if the person returns to A while B is still pending.
    setDecision(undefined);
    if (!organizationId || !stamp || context.isFetching || context.isError) return;
    let active = true;
    const request = authorize({ spaceCheck: { space_id: organizationId, permission: "administer_organization" } });
    void request.unwrap().then(
      ({ allowed }) => {
        if (active) setDecision({ organizationId, stamp, allowed });
      },
      (error: unknown) => {
        if (active) setDecision({ organizationId, stamp, allowed: false, error });
      },
    );
    return () => {
      active = false;
      request.abort();
    };
  }, [authorize, organizationId, stamp, context.isFetching, context.isError]);

  useRefetchOnWindowFocus(context.refetch, false);
  const current =
    !context.isFetching &&
    !context.isError &&
    decision &&
    decision.stamp === stamp &&
    decision.organizationId === organizationId
      ? decision
      : undefined;
  const revoke = useCallback(() => {
    setDecision((previous) => (previous ? { ...previous, allowed: false } : previous));
  }, []);
  return {
    memberships: context,
    organizations,
    organization,
    selectOrganization,
    organizationId,
    allowed: !!organizationId && current?.allowed === true,
    loading: !context.isError && (context.isFetching || context.isLoading || (!!organizationId && !current)),
    revoke,
    error: context.error || current?.error,
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
