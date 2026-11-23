// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { isWeaverContentRoute } from "@core/utils/weaverContentRoute";
import { isPlatformAdminRoute } from "@core/hooks/usePlatformArea";

/** Organization admin pages served by the platform shell. */
export function isOrganizationAdminRoute(pathname: string): boolean {
  return ["/admin/features", "/admin/supervision", "/admin/platform-prompt", "/admin/home-settings"].includes(
    pathname.replace(/\/$/, ""),
  );
}

/** Pages that never need the business bootstrap (content routes read their own access). */
export function skipsBusinessBootstrap(pathname: string): boolean {
  return isWeaverContentRoute(pathname) || isPlatformAdminRoute(pathname) || isOrganizationAdminRoute(pathname);
}
