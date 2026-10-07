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
import { useWebResearchSummaryQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import BarChart from "@shared/molecules/BarChart/BarChart";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import styles from "./AnalyticsPage.module.css";

/** Admin-only web research volume, estimated provider cost and refusals. */
export default function WebResearchSection({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useWebResearchSummaryQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );
  const card = (key: string, value: number | null | undefined) => (
    <KpiStatCard
      label={t(`rework.analytics.webResearch.${key}`)}
      value={value}
      isLoading={isLoading}
      isError={isError}
    />
  );
  const reasons = (data?.by_reason ?? []).map((r) => ({
    ...r,
    label: t(`rework.analytics.webResearch.reasons.${r.label}`, { defaultValue: r.label }),
  }));

  return (
    <Disclosure title={t("rework.analytics.sections.webResearch")} defaultOpen>
      <p className={styles.sectionDescription}>
        {t("rework.analytics.webResearch.costExplanation", {
          searches: data?.billable_searches ?? 0,
          cost: (data?.estimated_cost_usd ?? 0).toFixed(2),
        })}
      </p>
      <div className={styles.kpiRow}>
        {card("requests", data?.requests)}
        {card("estimatedCost", data?.estimated_cost_usd)}
        {card("blocked", data?.blocked)}
        {card("saturated", data?.saturated)}
        {card("failed", data?.failed)}
        {card("p95", data?.p95_ms)}
        {card("users", data?.unique_users)}
      </div>
      <div className={styles.sectionStack}>
        <BarChart
          title={t("rework.analytics.webResearch.reasonsTitle")}
          rows={reasons}
          emptyMessage={t("rework.analytics.webResearch.noRefusal")}
          isLoading={isLoading}
          isError={isError}
        />
        <p className={styles.sectionDescription}>{t("rework.analytics.webResearch.detailsHint")}</p>
      </div>
    </Disclosure>
  );
}
