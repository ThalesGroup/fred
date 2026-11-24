// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useWorkingOrganization } from "./useWorkingOrganization";

/** Direct organization grants only; platform and Admin roles never imply trace reading. */
export function useConversationTraceAccess() {
  const context = useWorkingOrganization();
  const organization = !context.memberships.isError
    ? context.memberships.currentData?.find(
        (space) => space.id === context.organizationId && space.kind === "organization",
      )
    : undefined;
  return {
    organizationId: organization?.id ?? "",
    canRead: organization?.roles.includes("organization_observer") === true,
    canManage: organization?.roles.includes("organization_admin") === true,
    isLoading: context.loading || context.memberships.isLoading,
  };
}
