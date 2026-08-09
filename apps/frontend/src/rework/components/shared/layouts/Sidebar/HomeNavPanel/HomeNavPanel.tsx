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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./HomeNavPanel.module.scss";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import TeamSelectionListItem from "@shared/molecules/TeamSelectionListItem/TeamSelectionListItem.tsx";
import { PERSONAL_TEAM_COLOR } from "@shared/atoms/TeamInitials/teamColor.ts";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";
import { KeyCloakService } from "../../../../../../security/KeycloakService.ts";

/**
 * Home view of the main nav panel (mainNavPanel): the app's team switcher,
 * moved off the former far-left avatar rail. Lists the personal space and every
 * team the user belongs to; each row navigates into that space. The search box
 * filters the "Vos équipes" list only — the personal space is a fixed home
 * anchor, not one of the user's teams.
 *
 * Reached via the mainNavBar Home icon (`/home`). Team/roles come from
 * `useFrontendBootstrap` (`available_teams[].my_relations`, #2298) — no per-team
 * fetch.
 */
export default function HomeNavPanel() {
  const { t } = useTranslation();
  const { defaultTeamAvatarFile } = useFrontendProperties();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const [search, setSearch] = useState("");

  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId && team.is_member);
  const query = search.trim().toLowerCase();
  const visibleTeams = query
    ? collaborativeTeams.filter((team) => team.name.toLowerCase().includes(query))
    : collaborativeTeams;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleContainer}>
          <span className={styles.title}>{t("rework.home.title")}</span>
        </div>
        <SearchInput
          size="xs"
          value={search}
          onChange={setSearch}
          placeholder={t("rework.home.searchPlaceholder")}
          ariaLabel={t("rework.home.searchPlaceholder")}
          clearAriaLabel={t("rework.home.searchClear")}
        />
      </div>

      <div className={styles.personalSpace}>
        <TeamSelectionListItem
          redirection={`/team/${personalTeamId}/agents`}
          name={t("rework.sidebar.team.userTeam")}
          personal
          avatarName={KeyCloakService.GetUserFullName()}
          avatarColor={PERSONAL_TEAM_COLOR}
        />
      </div>

      <div className={styles.teamList}>
        <div className={styles.teamListHeader}>
          <span className={styles.teamListHeaderLabel}>{t("rework.home.yourTeams")}</span>
        </div>
        <div className={styles.scroll}>
          {visibleTeams.map((team) => (
            <TeamSelectionListItem
              key={team.id}
              redirection={`/team/${team.id}/agents`}
              name={team.name}
              roles={team.my_relations}
              imgUrl={team.avatar_image_url ?? (defaultTeamAvatarFile ? `/images/${defaultTeamAvatarFile}` : undefined)}
              avatarName={team.name}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
