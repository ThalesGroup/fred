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

import TeamSelectionItem from "./TeamSelectionItem/TeamSelectionItem.tsx";
import styles from "./TeamSelectionNavbar.module.scss";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { PERSONAL_TEAM_COLOR } from "@shared/atoms/TeamInitials/teamColor.ts";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";

/**
 * Left-side team selector.
 *
 * Derives the team list exclusively from `useFrontendBootstrap` — no
 * per-team API fetches at load time. Renders the personal team, the
 * marketplace entry (when collaborative teams exist), and all collaborative
 * teams as `TeamSelectionItem` rows.
 *
 * Mount inside the main sidebar layout.
 */
export default function TeamSelectionNavbar() {
  const { siteTitle, siteSubtitle } = useFrontendProperties();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const { pathname } = useLocation();
  const { t } = useTranslation();

  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId);

  return (
    <div className={styles.teamNavbarContainer}>
      <div>
        <div className={styles.titleContainer}>
          <span className={styles.title}>{siteTitle}</span>
          <span className={styles.subTitle}>{siteSubtitle}</span>
        </div>
        <TeamSelectionItem
          redirection={`/team/${personalTeamId}/agents`}
          teamName={t("rework.sidebar.team.userTeam")}
          selected={pathname.startsWith(`/team/${personalTeamId}`)}
          avatarName={KeyCloakService.GetUserFullName()}
          avatarColor={PERSONAL_TEAM_COLOR}
        />
        {collaborativeTeams.length > 0 && (
          <TeamSelectionItem
            redirection={"/marketplace/teams"}
            teamName={t("rework.sidebar.team.marketplace")}
            selected={pathname.startsWith(`/marketplace`)}
            icon={{ category: "outlined", type: "storefront", filled: false }}
          />
        )}
      </div>
      <Separator margin={"var(--spacing-xs)"} />
      <div className={styles.teamContainer}>
        {collaborativeTeams.map((team) => {
          return (
            <TeamSelectionItem
              key={team.id}
              redirection={`/team/${team.id}/agents`}
              teamName={team.name}
              selected={pathname.startsWith(`/team/${team.id}`)}
              imgUrl={team.banner_image_url ?? undefined}
              avatarName={team.name}
            />
          );
        })}
      </div>
    </div>
  );
}
