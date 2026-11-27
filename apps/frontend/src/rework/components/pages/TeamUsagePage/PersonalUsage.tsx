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
import { bucketSpan, formatBucketLabel, viewerTimeZone } from "../admin/AnalyticsPage/analyticsFormat";
import { useAnalyticsTranslation } from "../admin/AnalyticsPage/useAnalyticsTranslation";
import {
  useUserSkillUsageQuery,
  useUserTokenUsageByAgentQuery,
  useUserTokenUsageByModelQuery,
  useUserTokenUsageOverTimeQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import BarChart from "@shared/molecules/BarChart/BarChart";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
import { agentUsageRows } from "@rework/utils/agentUsageRows";
import styles from "./TeamUsagePage.module.css";

const CACHE = { refetchOnMountOrArgChange: 300 } as const;
const BUCKETS = [
  { value: "day", label: "1D" },
  { value: "week", label: "1W" },
  { value: "month", label: "1M" },
] as const;

interface PersonalUsageProps {
  timeRange: TimeRange;
  /** In a personal space the viewer's own skill loads are shown too. */
  withSkills: boolean;
}

/** The viewer's own token usage: self-scoped reads, never another person's data. */
export default function PersonalUsage({ timeRange, withSkills }: PersonalUsageProps) {
  const { t, i18n } = useAnalyticsTranslation();
  const [bucket, setBucket] = useState<(typeof BUCKETS)[number]["value"]>("day");
  const args = { since: timeRange.since, until: timeRange.until };
  const overTime = useUserTokenUsageOverTimeQuery({ ...args, bucket, tz: viewerTimeZone() }, CACHE);
  const byAgent = useUserTokenUsageByAgentQuery(args, CACHE);
  const byModel = useUserTokenUsageByModelQuery(args, CACHE);
  const skills = useUserSkillUsageQuery(args, { ...CACHE, skip: !withSkills });
  const points = (overTime.currentData?.rows ?? []).map((point) => ({
    ...point,
    date: point.date.replace(" ", "T"),
  }));
  const span = bucketSpan(points.map(({ date }) => ({ start: date })));
  const interval = overTime.currentData?.interval;
  const displayedBucket =
    interval === "1M" ? "month" : interval === "1w" ? "week" : interval === "1d" ? "day" : interval ? "hour" : bucket;

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
              rows={points.map((point) => ({
                ...point,
                date: point.date.includes("-")
                  ? formatBucketLabel(point.date, displayedBucket, i18n.language, t, span)
                  : point.date,
              }))}
              headerActions={
                <ButtonGroup
                  variant="radio"
                  size="small"
                  color="on-surface"
                  surface="surface-container-high"
                  aria-label={t("rework.teamUsage.tokensOverTime.groupBy")}
                  items={BUCKETS.map(({ label }) => ({ label }))}
                  selectedIndex={BUCKETS.findIndex(({ value }) => value === displayedBucket)}
                  onSelectedIndexChange={(index) => setBucket(BUCKETS[index].value)}
                />
              }
              valueLabel={t("rework.teamUsage.tokensOverTime.valueLabel")}
              isFetching={overTime.isFetching}
              isLoading={overTime.isLoading || (overTime.isFetching && !overTime.currentData)}
              isError={overTime.isError}
            />
            <TokenUsageImpact
              rows={overTime.currentData?.rows}
              isLoading={overTime.isLoading || (overTime.isFetching && !overTime.currentData)}
            />
          </div>
          <BarChart
            title={t("rework.teamUsage.byAgent.title")}
            rows={agentUsageRows(byAgent.currentData?.rows, t)}
            valueLabel={t("rework.teamUsage.byAgent.valueLabel")}
            emptyMessage={t("rework.teamUsage.byAgent.empty")}
            isLoading={byAgent.isLoading || (byAgent.isFetching && !byAgent.currentData)}
            isError={byAgent.isError}
          />
          <BarChart
            title={t("rework.teamUsage.byModel.title")}
            rows={byModel.currentData?.rows ?? []}
            valueLabel={t("rework.teamUsage.byModel.valueLabel")}
            emptyMessage={t("rework.teamUsage.byModel.empty")}
            isLoading={byModel.isLoading || (byModel.isFetching && !byModel.currentData)}
            isError={byModel.isError}
          />
        </div>
      </Disclosure>
    </>
  );
}
