// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMeQuery } from "../../../slices/fredManager/fredManagerApiEnhancements";

/** Manager authority is independent of the control-plane's bootstrap roles. */
export function useManagerPlatformAdmin() {
  const query = useMeQuery(undefined, { refetchOnMountOrArgChange: 60 });
  return {
    ...query,
    isAdmin: !query.isError && query.data?.platform_roles.includes("platform_owner") === true,
  };
}
