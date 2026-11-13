// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { Fragment, type PropsWithChildren } from "react";
import { matchPath, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";

/** A bookmarked resource cannot render under another organization's working context. */
export default function WorkingOrganizationRoute({
  children,
  silent = false,
}: PropsWithChildren<{ silent?: boolean }>) {
  const context = useWorkingOrganization();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const teamId = matchPath("/team/:teamId/*", pathname)?.params.teamId;
  const catalogue = pathname.startsWith("/marketplace/") ? new URLSearchParams(search).get("catalogue") : null;
  const scoped =
    /^\/(home|team|marketplace)(\/|$)/.test(pathname) || /^\/admin\/(features|supervision)\/?$/.test(pathname);
  if (!scoped) return children;
  if (context.loading) return silent ? null : <Spinner size={20} />;
  if (context.error || !context.organizationId)
    return silent ? null : (
      <ServiceNotice
        icon="lock"
        title={t("rework.manager.unavailable")}
        description={t("rework.profileMenu.workingOrganization")}
      />
    );
  if (teamId === "personal") {
    if (silent) return null;
    const personal = context.memberships.currentData?.find(
      (space) => space.kind === "personal" && space.organization_id === context.organizationId,
    );
    return personal ? (
      <Navigate replace to={{ pathname: pathname.replace("/team/personal", `/team/${personal.id}`), search }} />
    ) : (
      <ServiceNotice icon="lock" title={t("rework.home.noSpaces")} />
    );
  }
  const targetId = teamId
    ? context.memberships.currentData?.find((space) => space.id === teamId)?.organization_id
    : catalogue;
  // An unknown/revoked space has no trusted organization placement. Do not
  // mount its consumers under the currently selected organization.
  if (teamId && !targetId) return silent ? null : <ServiceNotice icon="lock" title={t("rework.manager.unavailable")} />;
  if (targetId && targetId !== context.organizationId) {
    if (silent) return null;
    const target = context.organizations.find((item) => item.id === targetId);
    return (
      <ServiceNotice
        icon="groups"
        title={t(target ? "rework.profileMenu.organizationLink" : "rework.manager.unavailable", { name: target?.name })}
        action={
          target ? (
            <Button
              variant="outlined"
              color="primary"
              size="small"
              onClick={() => context.selectOrganization(target.id)}
            >
              {t("rework.profileMenu.continueInOrganization", { name: target.name })}
            </Button>
          ) : (
            <Button variant="outlined" color="primary" size="small" onClick={() => navigate("/home")}>
              {t("rework.home.title")}
            </Button>
          )
        }
      />
    );
  }
  return <Fragment key={context.organizationId}>{children}</Fragment>;
}
