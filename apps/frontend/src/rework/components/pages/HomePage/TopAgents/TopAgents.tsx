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
import type { AnalyticsResult, MySpace } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection";
import RankedList, { type RankedItem } from "../RankedList/RankedList";

export default function TopAgents({
  result,
  memberships,
  status,
}: {
  result?: AnalyticsResult;
  memberships: MySpace[];
  status?: string;
}) {
  const { t } = useTranslation();
  const items: RankedItem[] = (result?.rows ?? []).flatMap((row) => {
    if (row.dimensions.kind !== "agent") return [];
    const dimension = row.dimensions;
    const space = memberships.find((s) => s.id === dimension.space_id);
    return [
      {
        key: dimension.agent_instance_id,
        label: dimension.display_name ?? t("rework.home.activity.deletedAgent"),
        sublabel: space?.kind === "personal" ? t("rework.home.topTeams.personalSpace") : space?.name,
        value: BigInt(row.values["activity.completed_turns"]),
        unit: t("rework.home.topAgents.unit"),
      },
    ];
  });
  return (
    <LeaderboardSection
      icon="auto_awesome"
      title={t("rework.home.topAgents.title")}
      status={status}
      truncated={result?.truncated}
    >
      <RankedList items={items} emptyLabel={t("rework.home.topAgents.empty")} />
    </LeaderboardSection>
  );
}
