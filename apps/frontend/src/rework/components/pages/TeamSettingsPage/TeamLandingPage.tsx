// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

export default function TeamLandingPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const content = useSpaceAccess(teamId, "read");
  const manage = useSpaceAccess(teamId, "manage");
  const spaces = useMySpacesQuery(undefined, { skip: !content.allowed });
  if (content.error || manage.error || (content.allowed && spaces.isError))
    return <p role="alert">{t("rework.manager.unavailable")}</p>;
  if (!content.settled || !manage.settled || (content.allowed && !spaces.currentData))
    return <p role="status">{t("common.loading")}</p>;
  if (content.allowed) {
    const space = spaces.currentData?.find((item) => item.id === teamId);
    return <Navigate to={`/team/${teamId}/${space?.kind === "organization" ? "resources" : "agents"}`} replace />;
  }
  if (manage.allowed) return <Navigate to={`/team/${teamId}/settings/members`} replace />;
  return <p role="alert">{t("rework.spaceMembers.forbidden")}</p>;
}
