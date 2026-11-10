// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";
import { useManagerPlatformAdmin } from "./useManagerPlatformAdmin";

export function useSelfTestAccess(skip = false) {
  const manager = useManagerPlatformAdmin(skip, true);
  const skipMemberships = skip || !manager.isAdmin;
  const spaces = useMySpacesQuery(undefined, crossSessionRefreshOptions(skipMemberships));
  useRefetchOnWindowFocus(spaces.refetch, skipMemberships);
  const loading =
    !skip &&
    (manager.isLoading ||
      (manager.isFetching && !manager.currentData) ||
      (manager.isAdmin && (spaces.isLoading || (spaces.isFetching && !spaces.currentData))));
  const owner = spaces.currentData?.some(
    (space) => ["organization", "team", "project"].includes(space.kind) && space.roles.includes("owner"),
  );
  return {
    allowed: !skip && !loading && manager.isAdmin && !spaces.isError && !spaces.error && owner === true,
    loading,
    userId: manager.currentData?.user_id,
  };
}
