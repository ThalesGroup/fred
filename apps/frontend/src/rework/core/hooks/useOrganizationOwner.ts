// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useOrganizationSupervisionAccess } from "./useOrganizationSupervisionAccess";

/** Organization authority comes from manager membership, never platform roles. */
export function useOrganizationOwner() {
  const { memberships, organization } = useOrganizationSupervisionAccess();
  const isOwner = organization?.roles.includes("owner") === true;
  return { ...memberships, organizationId: isOwner ? organization.id : undefined, isOwner };
}
