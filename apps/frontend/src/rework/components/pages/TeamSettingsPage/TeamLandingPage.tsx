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
  const spaces = useMySpacesQuery();
  // The organization's panel is Home: its old landing keeps bookmarks working.
  if (!spaces.isError && spaces.currentData?.some((item) => item.id === teamId && item.kind === "organization"))
    return <Navigate to="/home" replace />;
  if (content.error || (content.allowed && spaces.isError))
    return <span role="alert">{t("rework.manager.unavailable")}</span>;
  if (!content.settled || (!spaces.currentData && !spaces.isError))
    return <span role="status">{t("common.loading")}</span>;
  // A team opens on its projects, other spaces on their agents.
  const kind = spaces.currentData?.find((item) => item.id === teamId)?.kind;
  if (content.allowed) return <Navigate to={`/team/${teamId}/${kind === "team" ? "projects" : "agents"}`} replace />;
  return <span role="alert">{t("rework.spaceMembers.forbidden")}</span>;
}
