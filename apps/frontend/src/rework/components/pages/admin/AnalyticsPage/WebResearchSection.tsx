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
import { AnalyticsSection } from "./AnalyticsSection";
import { RankedList } from "./RankedBars";
import { formatValue } from "./analyticsFormat";
import { type AnalyticsTabProps, KPI_CACHE, kpiArgs } from "./analyticsQuery";
import styles from "./AnalyticsPage.module.css";

/** Web research volume, estimated provider cost and refusals. Absent while the capability is
 *  enabled nowhere on the platform. */
export default function WebResearchSection({ timeRange, teamIds, userFilter }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const { data, isLoading, isError } = useWebResearchSummaryQuery(kpiArgs(timeRange, teamIds, userFilter), KPI_CACHE);
  const card = (key: string, value: number | null | undefined, displayValue?: string, caption?: string) => (
    <KpiStatCard
      label={t(`rework.analytics.webResearch.${key}`)}
      hint={t(`rework.analytics.webResearch.hints.${key}`)}
      value={value}
      displayValue={displayValue}
      caption={caption}
      isLoading={isLoading}
      isError={isError}
      nested
    />
  );
  if (data?.available === false) return null;
  const count = (v: number) => formatValue(v, "count", lng);
  const cost = data?.estimated_cost_eur;
  const refused = data ? data.blocked + data.saturated + data.failed : undefined;
  const p95 = data?.p95_ms;
  const reasons = (data?.by_reason ?? []).map((r) => ({
    key: r.label,
    label: t(`rework.analytics.webResearch.reasons.${r.label}`, { defaultValue: r.label }),
    value: r.value,
    valueText: count(r.value),
  }));

  return (
    <AnalyticsSection id="webResearch">
      <div className={styles.mainAside}>
        <div className={styles.kpiRowDense}>
          {card("toolCalls", data?.tool_calls)}
          {card("searches", data?.searches)}
          {card(
            "fetches",
            data?.fetches,
            undefined,
            data?.searches
              ? t("rework.analytics.webResearch.pagesPerSearch", {
                  value: formatValue(data.fetches / data.searches, "decimal", lng),
                })
              : undefined,
          )}
          {card("estimatedCost", cost, cost == null ? undefined : formatValue(cost, "eur", lng))}
          {card(
            "refused",
            refused,
            data ? `${count(data.blocked)} / ${count(data.saturated)} / ${count(data.failed)}` : undefined,
            data?.tool_calls
              ? t("rework.analytics.webResearch.shareOfCalls", {
                  value: formatValue(refused! / data.tool_calls, "percent", lng),
                })
              : undefined,
          )}
          {card("p95", p95, p95 == null ? undefined : formatSeconds(p95 / 1000, lng))}
        </div>
        <RankedList
          title={t("rework.analytics.webResearch.reasonsTitle")}
          rows={reasons}
          emptyMessage={t("rework.analytics.webResearch.noRefusal")}
          isLoading={isLoading}
          isError={isError}
        />
      </div>
    </AnalyticsSection>
  );
}

function formatSeconds(seconds: number, lng: string): string {
  return new Intl.NumberFormat(lng, { style: "unit", unit: "second", maximumFractionDigits: 1 }).format(seconds);
}
