// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useLocation } from "react-router-dom";
import { useMySpacesQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useManagerPlatformAdmin } from "./useManagerPlatformAdmin";

/** Pages of the platform admin space; every other admin page belongs to the organization. */
const PLATFORM_ADMIN_ROUTES = new Set(["/admin/organizations", "/admin/provisioning"]);

export const isPlatformAdminRoute = (pathname: string) => PLATFORM_ADMIN_ROUTES.has(pathname.replace(/\/$/, ""));

/**
 * The route belongs to the platform area: a platform page, or any page for a platform
 * admin with no organization membership. A member keeps their own pages elsewhere.
 */
export function usePlatformArea(skip = false) {
  const { pathname } = useLocation();
  const manager = useManagerPlatformAdmin(skip);
  const spaces = useMySpacesQuery(undefined, { skip: skip || !manager.isAdmin });
  // Last known membership: a failed refetch keeps it; an error before any data means none.
  const member = !!spaces.data?.length;
  return {
    platformArea: manager.isAdmin && (isPlatformAdminRoute(pathname) || !member),
    platformOnly: manager.isAdmin && !member,
    loading: manager.isAdmin && (spaces.isLoading || (spaces.isFetching && !spaces.data)),
  };
}
