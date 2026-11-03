// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";

export default function TeamLandingPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const content = useSpaceAccess(teamId, "read");
  const manage = useSpaceAccess(teamId, "manage");
  if (content.error || manage.error) return <p role="alert">{t("rework.manager.unavailable")}</p>;
  if (!content.settled || !manage.settled) return <p role="status">{t("common.loading")}</p>;
  if (content.allowed) return <Navigate to={`/team/${teamId}/agents`} replace />;
  if (manage.allowed) return <Navigate to={`/team/${teamId}/settings/members`} replace />;
  return <p role="alert">{t("rework.spaceMembers.forbidden")}</p>;
}
