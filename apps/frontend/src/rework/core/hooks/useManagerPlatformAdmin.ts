// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMeQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";

/** Manager authority is independent of the control-plane's bootstrap roles. */
export function useManagerPlatformAdmin(skip = false, refresh = false) {
  const query = useMeQuery(undefined, {
    refetchOnMountOrArgChange: 60,
    ...(refresh ? crossSessionRefreshOptions(skip) : { skip }),
  });
  useRefetchOnWindowFocus(query.refetch, skip || !refresh);
  return {
    ...query,
    isAdmin: !query.isError && !query.error && query.currentData?.platform_roles.includes("platform_admin") === true,
  };
}
