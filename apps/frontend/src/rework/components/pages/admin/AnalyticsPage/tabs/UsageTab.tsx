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

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  useAnalyticsActivityOverTimeQuery,
  useAnalyticsUsageQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import BarChart from "@shared/molecules/BarChart/BarChart";
import { AnalyticsSection, AnalyticsServiceDown, ChartHint } from "../AnalyticsSection";
import { RankedList } from "../RankedBars";
import InfoTile from "../InfoTile";
import { bucketSpan, formatBucketLabel, formatValue } from "../analyticsFormat";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, zonedKpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

export default function UsageTab({ timeRange, teamIds, userFilter, days }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const args = zonedKpiArgs(timeRange, teamIds, userFilter, days);
  const usage = useAnalyticsUsageQuery(args, KPI_CACHE);
  const activity = useAnalyticsActivityOverTimeQuery(args, KPI_CACHE);
  const data = usage.data;
  const tile = { isLoading: usage.isLoading, isError: usage.isError };
  const topShare = data?.top_decile_conversation_share.current;
  const bucket = activity.data?.bucket ?? "day";
  const span = bucketSpan(activity.data?.points);
  const messageRows = (activity.data?.points ?? []).map((p) => ({
    label: formatBucketLabel(p.start, bucket, i18n.language, t, span),
    value: p.values.messages ?? 0,
  }));

  const messagesTitle = t(`rework.analytics.charts.messagesOverTime.title.${bucket}`);
  const distributionTitle = t("rework.analytics.charts.conversationDistribution.title");
  const distribution = data?.conversation_distribution ?? [];
  const distributionTotal = distribution.reduce((sum, row) => sum + row.value, 0);
  // An all-zero distribution is "no activity", not five empty bars.
  const distributionRows = distributionTotal
    ? distribution.map((row) => ({
        key: row.label,
        label: bucketLabel(row.label, t),
        value: row.value,
        valueText: t("rework.analytics.charts.conversationDistribution.users", {
          count: row.value,
          value: formatValue(row.value, "count", i18n.language),
          share: formatValue(row.value / distributionTotal, "percent", i18n.language),
        }),
      }))
    : [];

  if (allFailed([usage, activity])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <AnalyticsSection id="volumes">
        <div className={styles.mainAside}>
          <BarChart
            title={messagesTitle}
            titleAction={<ChartHint id="messagesOverTime" title={messagesTitle} />}
            rows={messageRows}
            orientation="vertical"
            sortOrder="none"
            valueLabel={t("rework.analytics.charts.messagesOverTime.valueLabel")}
            isLoading={activity.isLoading}
            isError={activity.isError}
            flat
            labelled
            maxBarSize={48}
          />
          <div className={styles.stack}>
            <InfoTile id="conversations" period={data?.conversations} {...tile} />
            <InfoTile id="messages" withHow={false} period={data?.messages} {...tile} />
          </div>
        </div>
      </AnalyticsSection>

      <AnalyticsSection id="frequency">
        <div className={styles.kpiRow}>
          <InfoTile id="daysPerWeek" period={data?.days_per_week_median} format="decimal" {...tile} />
          <InfoTile id="conversationsPerUser" period={data?.conversations_per_user_median} format="decimal" {...tile} />
          <InfoTile
            id="messagesPerConversation"
            period={data?.messages_per_conversation_median}
            format="decimal"
            {...tile}
          />
          <InfoTile id="dailyUsage" period={data?.daily_usage_share} format="percent" deltaKind="points" {...tile} />
        </div>
      </AnalyticsSection>

      <AnalyticsSection id="distribution">
        <RankedList
          title={distributionTitle}
          titleAction={<ChartHint id="conversationDistribution" title={distributionTitle} />}
          rows={distributionRows}
          emptyMessage={t("rework.analytics.charts.conversationDistribution.empty")}
          isLoading={usage.isLoading}
          isError={usage.isError}
          keepOrder
        />
        {topShare != null && (
          <p className={styles.topDecile}>
            {t("rework.analytics.charts.conversationDistribution.topDecile.lead")}{" "}
            <strong className={styles.topDecileValue}>{formatValue(topShare, "percent", i18n.language)}</strong>{" "}
            {t("rework.analytics.charts.conversationDistribution.topDecile.rest", {
              users: formatValue(data?.active_users.current ?? 0, "count", i18n.language),
            })}
          </p>
        )}
      </AnalyticsSection>
    </div>
  );
}

/** "2-3" → "2 to 3 conversations", "31+" → "31 conversations or more", "1" → "1 conversation". */
function bucketLabel(label: string, t: TFunction): string {
  const key = "rework.analytics.charts.conversationDistribution.bucket";
  const atLeast = /^(\d+)\+$/.exec(label);
  if (atLeast) return t(`${key}.atLeast`, { low: atLeast[1] });
  const range = /^(\d+)-(\d+)$/.exec(label);
  if (range) return t(`${key}.range`, { low: range[1], high: range[2] });
  return t(`${key}.exact`, { count: Number(label), value: label });
}
