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
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import { resolvePreset, type TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import AnalyticsView from "../admin/AnalyticsPage/AnalyticsView";
import { ANALYTICS_PRESETS } from "../admin/AnalyticsPage/analyticsQuery";
import PersonalUsage from "./PersonalUsage";
import styles from "./TeamUsagePage.module.css";

/**
 * A team admin (`can_read_analytics`) sees the platform analytics limited to their team, plus
 * their own usage as a last tab. Everyone else, and any personal space, sees only their own usage.
 */
export default function TeamUsagePage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(() => resolvePreset("last30d"));
  const { teamId, selectedTeam, isPersonalTeam } = useSelectedTeam();
  const capabilities = useTeamCapabilities(selectedTeam);

  if (teamId && capabilities.canReadAnalytics && !isPersonalTeam) {
    return (
      <AnalyticsView
        title={t("rework.analytics.title")}
        mode="team"
        teamIds={[teamId]}
        extraTab={{
          label: t("rework.teamUsage.personalSectionTitle"),
          render: (range) => <PersonalUsage timeRange={range} withSkills={false} />,
        }}
      />
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <PageHeader
          title={t("rework.teamUsage.title")}
          actions={<TimeRangeSelector value={timeRange} onChange={setTimeRange} presetKeys={ANALYTICS_PRESETS} />}
        />
      </div>
      <div className={styles.body}>
        <PersonalUsage timeRange={timeRange} withSkills={isPersonalTeam} />
      </div>
    </div>
  );
}
