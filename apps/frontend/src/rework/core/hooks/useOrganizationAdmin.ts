// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "./crossSessionRefresh";

/** Organization authority comes from manager membership, never platform roles. */
export function useOrganizationAdmin() {
  const query = useMySpacesQuery(undefined, crossSessionRefreshOptions(false));
  useRefetchOnWindowFocus(query.refetch, false);
  const organization =
    !query.isError && !query.error
      ? query.currentData?.find((space) => space.kind === "organization" && space.roles.includes("admin"))
      : undefined;
  return { ...query, organizationId: organization?.id, isAdmin: !!organization };
}
