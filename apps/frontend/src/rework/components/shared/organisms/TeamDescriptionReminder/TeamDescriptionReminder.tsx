// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import type { Space } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

export default function TeamDescriptionReminder({ space }: { space: Space }) {
  const { t } = useTranslation();
  const access = useSpaceAccess(space.kind === "team" ? space.id : undefined, "manage");
  if (space.kind !== "team" || space.description !== null || !access.offered) return null;
  return (
    <div role="status">
      <ServiceNotice
        color="info"
        title={t("rework.teamDescription.reminder.title")}
        description={t("rework.teamDescription.reminder.description")}
        action={
          <Link to={`/team/${space.id}/settings/parameters`}>
            <Button color="info" variant="filled" size="small">
              {t("rework.teamDescription.reminder.action")}
            </Button>
          </Link>
        }
      />
    </div>
  );
}
