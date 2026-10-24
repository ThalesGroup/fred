// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { useAuthorizeSpaceMutation, useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useRefetchOnWindowFocus } from "./crossSessionRefresh";

function useAccess() {
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  // /me/spaces rejects ambiguous attachments; every row carries the same organization.
  const organizationId = context.currentData?.[0]?.organization_id;
  const [authorize] = useAuthorizeSpaceMutation();
  const [decision, setDecision] = useState<{
    organizationId: string;
    stamp: number;
    allowed: boolean;
    error?: unknown;
  }>();
  const stamp = context.fulfilledTimeStamp;

  useEffect(() => {
    if (!organizationId || !stamp || context.isFetching || context.isError) return;
    let active = true;
    const request = authorize({ spaceCheck: { space_id: organizationId, permission: "own_organization" } });
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
