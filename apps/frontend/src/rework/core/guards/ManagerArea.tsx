// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { usePlatformArea } from "@core/hooks/usePlatformArea";

const platformRoutes = new Set([
  "/admin/organizations",
  "/admin/provisioning",
  "/settings",
  "/gcu",
  "/gdpr",
  "/release-notes",
]);

// These business routes have their own organization guard, including for mixed roles.
const ORGANIZATION_ROUTES = new Set(["/admin", "/admin/features", "/admin/supervision", "/unauthorized"]);

/**
 * Platform governance stays separate; organization routes have their own authority. A
 * platform admin who is also a member keeps their own pages, each guarded as for anyone.
 */
export default function ManagerArea({ children }: { children: (business: boolean) => ReactNode }) {
  const access = useManagerPlatformAdmin();
  const area = usePlatformArea();
  const { pathname } = useLocation();
  const { t } = useTranslation();
  useRefetchOnWindowFocus(access.refetch, false);
  if (access.isLoading || (access.isFetching && !access.currentData) || area.loading) {
    return (
      <MainLayout navigation={false}>
        <p role="status">{t("common.loading")}</p>
      </MainLayout>
    );
  }
  if (access.isError || access.error || !access.currentData) {
    return (
      <MainLayout navigation={false}>
        <div role="alert">
          <p>{t("rework.manager.unavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => void access.refetch()}>
            {t("rework.provisioning.retryAuthority")}
          </Button>
        </div>
      </MainLayout>
    );
  }
  const path = pathname.replace(/\/$/, "");
  if (area.platformArea && !platformRoutes.has(path) && !ORGANIZATION_ROUTES.has(path))
    return <Navigate to="/admin/organizations" replace />;
  // One output shape for every route, so the layout stays mounted across a space change;
  // only the business consumers (announcements, patch notes) depend on the route.
  return <>{children(!area.platformArea && !ORGANIZATION_ROUTES.has(path))}</>;
}
