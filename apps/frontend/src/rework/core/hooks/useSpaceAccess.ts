// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useEffect, useMemo } from "react";
import type { SpacePermission } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { useMySpacesQuery, useSpaceAccessQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";

/**
 * One person's right on a space, rechecked each time their memberships refresh.
 * `offered` keeps the last answer so the UI never blinks; only `allowed`, newer
 * than those memberships, may drive an action. The server still decides.
 */
export function useSpaceAccess(spaceId: string | undefined, permission: SpacePermission) {
  const context = useMySpacesQuery();
  const query = useSpaceAccessQuery(spaceId ? { space_id: spaceId, permission } : skipToken);
  // A cached answer may be shown, never trusted: it must be newer than this request.
  const askedAt = useMemo(() => Date.now(), [spaceId, permission]);
  const { isFetching, isUninitialized, refetch } = query;
  const outdated = (query.startedTimeStamp ?? 0) < Math.max(askedAt, context.fulfilledTimeStamp ?? 0);
  useEffect(() => {
    if (outdated && !isFetching && !isUninitialized) void refetch();
  }, [outdated, isFetching, isUninitialized, refetch]);
  const settled = !context.isFetching && !context.isError && !isFetching && !isUninitialized && !outdated;
  const offered = !query.isError && query.currentData?.allowed === true;
  return { offered, allowed: settled && offered, settled, error: query.isError ? query.error : undefined, refetch };
}
