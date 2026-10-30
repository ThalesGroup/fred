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
import {
  useUserSkillUsageQuery,
  useUserTokenUsageByAgentQuery,
  useUserTokenUsageByModelQuery,
  useUserTokenUsageOverTimeQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import BarChart from "@shared/molecules/BarChart/BarChart";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
import { agentUsageRows } from "@rework/utils/agentUsageRows";
import styles from "./TeamUsagePage.module.css";

const CACHE = { refetchOnMountOrArgChange: 300 } as const;

interface PersonalUsageProps {
  timeRange: TimeRange;
  /** In a personal space the viewer's own skill loads are shown too. */
  withSkills: boolean;
}

/** The viewer's own token usage: self-scoped reads, never another person's data. */
export default function PersonalUsage({ timeRange, withSkills }: PersonalUsageProps) {
  const { t } = useTranslation();
  const args = { since: timeRange.since, until: timeRange.until };
  const overTime = useUserTokenUsageOverTimeQuery(args, CACHE);
  const byAgent = useUserTokenUsageByAgentQuery(args, CACHE);
  const byModel = useUserTokenUsageByModelQuery(args, CACHE);
  const skills = useUserSkillUsageQuery(args, { ...CACHE, skip: !withSkills });

  if (overTime.isError && byAgent.isError && byModel.isError) {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.controlPlane.title")}
        description={t("rework.serviceNotice.controlPlane.description")}
        centered
      />
    );
  }

  return (
    <>
      {withSkills && (
        <Disclosure title={t("rework.teamUsage.personalSkillsSectionTitle")} defaultOpen>
          {/* currentData: a previous range's rows must not show while the new one loads. */}
          <SkillUsageTable
            data={skills.currentData}
            isLoading={skills.isLoading || (skills.isFetching && !skills.currentData)}
            isError={skills.isError}
          />
        </Disclosure>
      )}
      <Disclosure title={t("rework.teamUsage.personalSectionTitle")} defaultOpen>
        <div className={styles.chartGrid}>
          <div className={styles.cellFull}>
            <TimeSeriesLineChart
              title={t("rework.teamUsage.tokensOverTime.title")}
              rows={overTime.data?.rows ?? []}
              interval={overTime.data?.interval}
              valueLabel={t("rework.teamUsage.tokensOverTime.valueLabel")}
              isFetching={overTime.isFetching}
              isLoading={overTime.isLoading}
              isError={overTime.isError}
            />
            <TokenUsageImpact rows={overTime.data?.rows} isLoading={overTime.isLoading} />
          </div>
          <BarChart
            title={t("rework.teamUsage.byAgent.title")}
            rows={agentUsageRows(byAgent.data?.rows, t)}
            valueLabel={t("rework.teamUsage.byAgent.valueLabel")}
            emptyMessage={t("rework.teamUsage.byAgent.empty")}
            isLoading={byAgent.isLoading}
            isError={byAgent.isError}
          />
          <BarChart
            title={t("rework.teamUsage.byModel.title")}
            rows={byModel.data?.rows ?? []}
            valueLabel={t("rework.teamUsage.byModel.valueLabel")}
            emptyMessage={t("rework.teamUsage.byModel.empty")}
            isLoading={byModel.isLoading}
            isError={byModel.isError}
          />
        </div>
      </Disclosure>
    </>
  );
}
