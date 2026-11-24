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
  const spaces = useMySpacesQuery();
  // The organization's panel is Home: its old landing keeps bookmarks working.
  if (!spaces.isError && spaces.currentData?.some((item) => item.id === teamId && item.kind === "organization"))
    return <Navigate to="/home" replace />;
  if (content.error || manage.error || (content.allowed && spaces.isError))
    return <span role="alert">{t("rework.manager.unavailable")}</span>;
  if (!content.settled || !manage.settled || (!spaces.currentData && !spaces.isError))
    return <span role="status">{t("common.loading")}</span>;
  // A team opens on its projects; other spaces on their agents.
  const isTeam = spaces.currentData?.some((item) => item.id === teamId && item.kind === "team");
  if (content.allowed) return <Navigate to={`/team/${teamId}/${isTeam ? "projects" : "agents"}`} replace />;
  if (manage.allowed) return <Navigate to={`/team/${teamId}/settings/${isTeam ? "parameters" : "members"}`} replace />;
  return <span role="alert">{t("rework.spaceMembers.forbidden")}</span>;
}
