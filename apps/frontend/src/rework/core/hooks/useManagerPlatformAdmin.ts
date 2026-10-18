// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMeQuery } from "../../../slices/fredManager/fredManagerApiEnhancements";

/** Manager authority is independent of the control-plane's bootstrap roles. */
export function useManagerPlatformAdmin(skip = false) {
  const query = useMeQuery(undefined, { refetchOnMountOrArgChange: 60, skip });
  return {
    ...query,
    isAdmin: !query.isError && !query.error && query.currentData?.platform_roles.includes("platform_owner") === true,
  };
}
