// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { MySpace } from "../../../slices/controlPlane/controlPlaneOpenApi";

/** A team's projects among the person's memberships, by name; memberships decide what is visible. */
export function teamProjects(memberships: MySpace[] | undefined, team: MySpace | undefined): MySpace[] {
  if (team?.kind !== "team") return [];
  return (memberships ?? [])
    .filter(
      (item) => item.kind === "project" && item.parent_id === team.id && item.organization_id === team.organization_id,
    )
    .sort((a, b) => a.name.localeCompare(b.name));
}
