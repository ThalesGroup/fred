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
import TeamInitials from "@shared/atoms/TeamInitials/TeamInitials";
import { teamColor } from "@shared/atoms/TeamInitials/teamColor";
import type { AnalyticsResult, MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection";
import RankedList, { type RankedItem } from "../RankedList/RankedList";
import styles from "./TopTeams.module.scss";

export default function TopTeams({
  result,
  memberships,
  status,
}: {
  result?: AnalyticsResult;
  memberships: MySpace[];
  status?: string;
}) {
  const { t } = useTranslation();
  // Membership restriction, zeros, ordering and truncation are computed by the server.
  // Membership data here supplies labels and roles only, never authorization or ranking.
  const items: RankedItem[] = (result?.rows ?? []).flatMap((row) => {
    if (row.dimensions.kind !== "space") return [];
    const id = row.dimensions.space_id;
    const space = memberships.find((s) => s.id === id);
    const personal = space?.kind === "personal";
    const label = personal
      ? t("rework.home.topTeams.personalSpace")
      : (space?.name ?? t("rework.home.activity.unavailableSpace"));
    return [
      {
        key: id,
        label,
        sublabel: personal ? undefined : space?.roles.map((role) => t(`rework.home.topTeams.role.${role}`)).join(" · "),
        value: BigInt(row.values["activity.completed_turns"]),
        unit: t("rework.home.topTeams.unit"),
        leading: (
          <TeamInitials className={styles.avatar} name={label} size="small" shape="square" color={teamColor(label)} />
        ),
      },
    ];
  });
  return (
    <LeaderboardSection
      icon="groups"
      title={t("rework.home.topTeams.title")}
      status={status}
      truncated={result?.truncated}
    >
      <RankedList items={items} emptyLabel={t("rework.home.topTeams.empty")} />
    </LeaderboardSection>
  );
}
