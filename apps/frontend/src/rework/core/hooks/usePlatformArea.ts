// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { isPromptPublicationRoute } from "../utils/weaverContentRoute";
import { useLocation } from "react-router-dom";
import { useMySpacesQuery, usePromptMarketplacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useManagerPlatformAdmin } from "./useManagerPlatformAdmin";

/** Pages of the platform admin space; every other admin page belongs to the organization. */
const PLATFORM_ADMIN_ROUTES = new Set([
  "/admin/organizations",
  "/admin/provisioning",
  "/admin/monitor",
  "/admin/skills",
]);

export const isPlatformAdminRoute = (pathname: string) => PLATFORM_ADMIN_ROUTES.has(pathname.replace(/\/$/, ""));

/**
 * The route belongs to the platform area: a platform page, or any page for a platform
 * admin with no organization membership. A member keeps their own pages elsewhere.
 */
export function usePlatformArea(skip = false) {
  const { pathname } = useLocation();
  const manager = useManagerPlatformAdmin(skip);
  const platformRole = manager.isAdmin || manager.isFeatureManager;
  const spaces = useMySpacesQuery(undefined, { skip: skip || !platformRole });
  // Last known membership: a failed refetch keeps it; an error before any data means none.
  const member = !!spaces.data?.length;
  const publications = usePromptMarketplacesQuery(
    {},
    {
      skip: skip || !manager.isAdmin || member,
      refetchOnMountOrArgChange: true,
    },
  );
  const promptReader = !publications.isError && !!publications.currentData?.items.length;
  return {
    platformArea:
      (manager.isFeatureManager && pathname.replace(/\/$/, "") === "/admin/skills") ||
      (manager.isAdmin &&
        (isPlatformAdminRoute(pathname) || (!member && !(promptReader && isPromptPublicationRoute(pathname))))),
    platformOnly: platformRole && !member && !promptReader,
    loading:
      platformRole && (spaces.isLoading || (spaces.isFetching && !spaces.data) || (!member && publications.isLoading)),
  };
}
