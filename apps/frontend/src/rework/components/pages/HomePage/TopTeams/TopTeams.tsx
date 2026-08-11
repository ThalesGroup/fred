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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials.tsx";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor.ts";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useUserTopTeamsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import type { HomePeriod } from "../HomePage.tsx";
import { homePeriodRange } from "../homePeriod.ts";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection.tsx";
import RankedList, { type RankedItem } from "../RankedList/RankedList.tsx";
import styles from "./TopTeams.module.scss";

const TOP_N = 5;
const ROLE_ORDER = ["team_admin", "team_editor", "team_analyst", "team_member"] as const;

interface TopTeamsProps {
  period: HomePeriod;
}

/** Home page — the teams the current user has been most active in over the
 * period (live: self-scoped `user_top_teams` preset — the caller's own turn
 * count per team). The team list, avatar and roles are the caller's real
 * membership from bootstrap; the personal space is excluded. */
export default function TopTeams({ period }: TopTeamsProps) {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();

  const range = useMemo(() => homePeriodRange(period), [period]);
  const { data } = useUserTopTeamsQuery(range, { refetchOnMountOrArgChange: 300 });

  // team_id → the caller's turn count over the period (0 when they've been idle
  // in a team they belong to).
  const activityByTeamId = useMemo(() => new Map((data?.rows ?? []).map((row) => [row.label, row.value])), [data]);

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
        value: activityByTeamId.get(team.id) ?? 0,
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
