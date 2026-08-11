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
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import type { HomePeriod } from "../HomePage.tsx";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection.tsx";
import RankedList, { type RankedItem } from "../RankedList/RankedList.tsx";
import styles from "./TopTeams.module.scss";

const TOP_N = 5;
const ROLE_ORDER = ["team_admin", "team_editor", "team_analyst", "team_member"] as const;

// Deterministic pseudo-activity per team id (8..40 at the 7-day baseline).
// PLACEHOLDER: real per-team activity over the period has no endpoint yet. The
// team list and the caller's membership/role are real; only the activity count
// is derived. Swap for a real period-scoped team-activity KPI before shipping.
function baseActivity(teamId: string): number {
  let h = 0;
  for (let i = 0; i < teamId.length; i++) h = (h * 31 + teamId.charCodeAt(i)) >>> 0;
  return 8 + (h % 33);
}

interface TopTeamsProps {
  period: HomePeriod;
}

/** Home page — the 5 most active teams the current user is at least a member of
 * (any role), scoped to the selected period. */
export default function TopTeams({ period }: TopTeamsProps) {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();

  const memberTeams = availableTeams.filter((team) => team.is_member && !isPersonalTeamId(team.id));

  const items: RankedItem[] = memberTeams
    .map((team) => {
      const roles = ROLE_ORDER.filter((role) => (team.my_relations ?? []).includes(role));
      const avatar = team.avatar_image_url ? (
        <img className={styles.avatar} src={team.avatar_image_url} alt="" aria-hidden="true" />
      ) : (
        <TeamInitials
          className={styles.avatar}
          name={team.name}
          size="small"
          shape="square"
          color={teamColor(team.name)}
        />
      );
      return {
        key: team.id,
        label: team.name,
        sublabel: roles.length ? roles.map((role) => t(`rework.home.topTeams.role.${role}`)).join(" · ") : undefined,
        value: Math.round((baseActivity(team.id) * period) / 7),
        unit: t("rework.home.topTeams.unit"),
        leading: avatar,
      };
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, TOP_N);

  return (
    <LeaderboardSection icon="groups" title={t("rework.home.topTeams.title")}>
      <RankedList items={items} emptyLabel={t("rework.home.topTeams.empty")} />
    </LeaderboardSection>
  );
}
