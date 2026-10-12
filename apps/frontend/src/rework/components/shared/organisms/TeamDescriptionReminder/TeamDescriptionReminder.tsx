// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Button from "@shared/atoms/Button/Button.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import type { TeamWithPermissions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamDescriptionReminder.module.scss";

export interface TeamDescriptionReminderProps {
  team: TeamWithPermissions | null | undefined;
  /** Adds a link to the team settings; omit it on the settings page itself. */
  withSettingsLink?: boolean;
}

/** Asks a team admin to replace the default description. Renders nothing for
 *  other members, for a described team and for a personal space. */
export default function TeamDescriptionReminder({ team, withSettingsLink }: TeamDescriptionReminderProps) {
  const { t } = useTranslation();
  const { canUpdateInfo } = useTeamCapabilities(team);

  if (!team?.description_is_placeholder || !canUpdateInfo) return null;
  return (
    <div className={styles.reminder} role="status">
      <div className={styles.notice}>
        <ServiceNotice
          color="info"
          title={t("rework.teamDescription.reminder.title")}
          description={t("rework.teamDescription.reminder.description")}
        />
      </div>
      {withSettingsLink && (
        <Link to={`/team/${team.id}/settings/parameters`}>
          <Button color="primary" variant="outlined" size="small">
            {t("rework.teamDescription.reminder.action")}
          </Button>
        </Link>
      )}
    </div>
  );
}
