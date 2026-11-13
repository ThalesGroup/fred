// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { MySpace } from "../../../slices/controlPlane/controlPlaneOpenApi";

/** UI prefilter from direct server memberships; analytics still authorizes each read. */
export function canReadSpaceUsage(space: MySpace | undefined, organizationId: string | undefined): boolean {
  return (
    !!organizationId &&
    space?.organization_id === organizationId &&
    (space.kind === "team" || space.kind === "project") &&
    space.roles.some((role) => role === "owner" || role === "analyst")
  );
}
