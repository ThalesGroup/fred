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
import { useUserTopAgentsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import type { HomePeriod } from "../HomePage.tsx";
import { homePeriodRange } from "../homePeriod.ts";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection.tsx";
import RankedList, { type RankedItem } from "../RankedList/RankedList.tsx";

interface TopAgentsProps {
  period: HomePeriod;
}

/** Home page — the agents the current user used most over the period (live:
 * self-scoped `user_top_agents` preset, ranked by turn count). The origin team
 * comes back as a team_id, resolved to its display name via bootstrap. */
export default function TopAgents({ period }: TopAgentsProps) {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();

  // Memoise the range on `period` — see homePeriod.ts (a fresh `until` each
  // render would refetch in a loop). TTL 300s, like the analytics pages.
  const range = useMemo(() => homePeriodRange(period), [period]);
  const { data } = useUserTopAgentsQuery(range, { refetchOnMountOrArgChange: 300 });

  const teamNameById = useMemo(() => new Map(availableTeams.map((team) => [team.id, team.name])), [availableTeams]);

  const items: RankedItem[] = (data?.rows ?? []).map((row) => ({
    key: row.agent_instance_id,
    label: row.agent_name,
    sublabel: row.team_id ? teamNameById.get(row.team_id) : undefined,
    value: row.value,
    unit: t("rework.home.topAgents.unit"),
  }));

  return (
    <LeaderboardSection icon="auto_awesome" title={t("rework.home.topAgents.title")}>
      <RankedList items={items} emptyLabel={t("rework.home.topAgents.empty")} />
    </LeaderboardSection>
  );
}
