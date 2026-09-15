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

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useMatch } from "react-router-dom";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TeamAdminCharterPage from "@components/pages/TeamAdminCharterPage/TeamAdminCharterPage.tsx";
import { useSelectedTeam } from "../../../../../hooks/useSelectedTeam.ts";
import styles from "./TeamAdminCharterGate.module.css";

/** Leads a pending admin of the selected team to the charter. It replaces the team's pages only
 *  while no accepted admin vouches for the user's other roles; otherwise a notice points to it. */
export default function TeamAdminCharterGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { teamId, selectedTeam } = useSelectedTeam();
  const onResponsibilities = useMatch("/team/:teamId/settings/responsibilities") !== null;
  const pending =
    !!selectedTeam &&
    "my_relations" in selectedTeam &&
    (selectedTeam.my_relations ?? []).includes("pending_team_admin");

  if (!pending) return <>{children}</>;
  if ((selectedTeam?.admins ?? []).length === 0) return <TeamAdminCharterPage />;
  return (
    <>
      {!onResponsibilities && (
        <div className={styles.notice} role="status">
          <span className={styles.icon} aria-hidden>
            <Icon category="outlined" type="admin_panel_settings" />
          </span>
          <span className={styles.message}>{t("rework.teamAdminCharter.pendingNotice")}</span>
          <Link className={styles.action} to={`/team/${teamId}/settings/responsibilities`}>
            <Button color="primary" variant="filled" size="small">
              {t("rework.teamAdminCharter.review")}
            </Button>
          </Link>
        </div>
      )}
      <div className={styles.pages}>{children}</div>
    </>
  );
}
