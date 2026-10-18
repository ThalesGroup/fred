// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { PropsWithChildren } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";

const platformRoutes = new Set([
  "/admin/organizations",
  "/admin/provisioning",
  "/settings",
  "/gcu",
  "/gdpr",
  "/release-notes",
]);

/** Platform governance never mounts the business area, including for mixed-role owners. */
export default function ManagerArea({ children }: PropsWithChildren) {
  const access = useManagerPlatformAdmin();
  const { pathname } = useLocation();
  const { t } = useTranslation();
  useRefetchOnWindowFocus(access.refetch, false);
  if (access.isLoading || (access.isFetching && !access.currentData)) {
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
  if (access.isAdmin) {
    return platformRoutes.has(pathname.replace(/\/$/, "")) ? (
      <Outlet />
    ) : (
      <Navigate to="/admin/organizations" replace />
    );
  }
  return <>{children}</>;
}
