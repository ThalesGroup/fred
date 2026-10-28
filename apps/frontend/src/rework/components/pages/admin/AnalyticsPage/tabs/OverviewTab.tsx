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
  useAnalyticsActivityOverTimeQuery,
  useAnalyticsAdoptionQuery,
  useAnalyticsOverviewQuery,
  useAnalyticsTeamsCatalogQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import { AnalyticsServiceDown, ChartHint } from "../AnalyticsSection";
import InfoTile from "../InfoTile";
import { bucketSeries, formatValue } from "../analyticsFormat";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, kpiArgs, zonedKpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

export default function OverviewTab({ timeRange, teamIds, mode = "platform", userFilter }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const overview = useAnalyticsOverviewQuery(kpiArgs(timeRange, teamIds, userFilter), KPI_CACHE);
  const zoned = zonedKpiArgs(timeRange, teamIds, userFilter);
  const activity = useAnalyticsActivityOverTimeQuery(zoned, KPI_CACHE);
  // Same arguments as the Adoption tab: one cached read serves both.
  const adoption = useAnalyticsAdoptionQuery(zoned, KPI_CACHE);
  // Active teams out of all teams is a platform figure: a team's page neither shows nor reads it.
  const crossTeam = mode === "platform";
  const catalog = useAnalyticsTeamsCatalogQuery({}, { ...KPI_CACHE, skip: !crossTeam });
  const data = overview.data;
  const totalTeams = teamIds.length > 0 ? teamIds.length : catalog.data?.rows.length;
  // Headline figures: the large value size.
  const tile = { isLoading: overview.isLoading, isError: overview.isError, size: "large" as const };
  const lifecycleTile = { isLoading: adoption.isLoading, isError: adoption.isError, size: "large" as const };
  const perUser = data?.cost_eur_per_active_user.current;
  const activeUsers = t("rework.analytics.charts.activityOverTime.activeUsers");
  const visitors = t("rework.analytics.charts.activityOverTime.visitors");

  const activityTitle = t(`rework.analytics.charts.activityOverTime.title.${activity.data?.bucket ?? "day"}`);

  if (allFailed([overview, activity])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <div className={styles.kpiRow}>
        <InfoTile id="activeUsers" period={data?.active_users} trendArgs={zoned} {...tile} />
        <InfoTile id="newUsers" period={adoption.data?.new_users} {...lifecycleTile} />
        {crossTeam && (
          <InfoTile
            id="activeTeams"
            period={data?.active_teams}
            deltaKind="absolute"
            caption={totalTeams != null ? t("rework.analytics.tiles.activeTeams.caption", { count: totalTeams }) : ""}
            {...tile}
          />
        )}
        <InfoTile
          id="nextMonthReturn"
          period={adoption.data?.next_month_return}
          format="percent"
          deltaKind="points"
          {...lifecycleTile}
        />
      </div>
      <MultiSeriesLineChart
        title={activityTitle}
        titleAction={<ChartHint id="activityOverTime" title={activityTitle} />}
        rows={bucketSeries(
          activity.data?.points,
          activity.data?.bucket,
          { active_users: activeUsers, visitors },
          i18n.language,
          t,
        )}
        series={[activeUsers, visitors]}
        barSeries={[activeUsers]}
        seriesColors={["--primary", "--tertiary"]}
        labelled
        valueLabel={t("rework.analytics.charts.activityOverTime.valueLabel")}
        isFetching={activity.isFetching}
        isLoading={activity.isLoading}
        isError={activity.isError}
      />
      <div className={styles.kpiRow}>
        <InfoTile id="conversations" period={data?.conversations} trendArgs={zoned} {...tile} />
        <InfoTile id="messages" period={data?.messages} trendArgs={zoned} {...tile} />
        <InfoTile
          id="cost"
          period={data?.cost_eur}
          format="eur"
          neutralDelta
          trendArgs={zoned}
          caption={
            perUser != null
              ? t("rework.analytics.tiles.cost.caption", { value: formatValue(perUser, "eur", i18n.language) })
              : ""
          }
          {...tile}
        />
      </div>
    </div>
  );
}
