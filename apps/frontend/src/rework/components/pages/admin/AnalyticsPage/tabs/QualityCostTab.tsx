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
  useAnalyticsQualityCostQuery,
  useAnalyticsUsageQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  AnalyticsAgentCostRow,
  AnalyticsModelRow,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import { CREATION_ASSISTANT_LABEL } from "@rework/utils/agentUsageRows";
import { AnalyticsSection, AnalyticsServiceDown, ChartHint } from "../AnalyticsSection";
import AnalyticsTable from "../AnalyticsTable";
import InfoTile from "../InfoTile";
import { bucketSeries, formatValue, NO_VALUE, type ValueFormat } from "../analyticsFormat";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, kpiArgs, zonedKpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

export default function QualityCostTab({ timeRange, teamIds, userFilter, days }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const quality = useAnalyticsQualityCostQuery(kpiArgs(timeRange, teamIds, userFilter, days), KPI_CACHE);
  const zoned = zonedKpiArgs(timeRange, teamIds, userFilter, days);
  const usage = useAnalyticsUsageQuery(zoned, KPI_CACHE);
  const activity = useAnalyticsActivityOverTimeQuery(zoned, KPI_CACHE);
  const data = quality.data;
  const tile = { isLoading: quality.isLoading, isError: quality.isError };
  const fmt = (v: number | null | undefined, f: ValueFormat) => (v == null ? NO_VALUE : formatValue(v, f, lng));
  const num = (text: string) => <span className={styles.numeric}>{text}</span>;

  const sent = data?.input_tokens;
  const generated = data?.output_tokens;
  const tokens = {
    current: sent?.current != null && generated?.current != null ? sent.current + generated.current : null,
    previous: sent?.previous != null && generated?.previous != null ? sent.previous + generated.previous : null,
  };
  const co2 = data?.co2e_grams;
  const footprintKg = co2 && {
    current: co2.current != null ? co2.current / 1000 : null,
    previous: co2.previous != null ? co2.previous / 1000 : null,
  };
  const series = {
    input_tokens: t("rework.analytics.charts.tokensOverTime.sent"),
    output_tokens: t("rework.analytics.charts.tokensOverTime.generated"),
  };

  const modelColumns: DataTableColumn<AnalyticsModelRow>[] = [
    { label: t("rework.analytics.tables.models.model"), size: "2fr", cellRenderer: (r) => r.model || NO_VALUE },
    {
      label: t("rework.analytics.tables.models.share"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.message_share ?? 0,
      cellRenderer: (r) => num(fmt(r.message_share, "percent")),
    },
    {
      label: t("rework.analytics.tables.models.tokens"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.input_tokens + r.output_tokens,
      cellRenderer: (r) => num(fmt(r.input_tokens + r.output_tokens, "compact")),
    },
    {
      label: t("rework.analytics.tables.models.cost"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.cost_eur,
      cellRenderer: (r) => num(fmt(r.cost_eur, "eur")),
    },
    {
      label: t("rework.analytics.tables.models.footprint"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.co2e_grams,
      cellRenderer: (r) => num(t("rework.analytics.units.kgCo2e", { value: fmt(r.co2e_grams / 1000, "decimal") })),
    },
  ];
  const agentRows = (data?.agents ?? []).map((row, i) => ({
    ...row,
    label:
      row.label === CREATION_ASSISTANT_LABEL ? t("rework.analytics.tokenUsage.byAgent.creationAssistant") : row.label,
    key: `${i}-${row.label}`,
  }));
  const agentColumns: DataTableColumn<AnalyticsAgentCostRow & { key: string }>[] = [
    { label: t("rework.analytics.tables.agentCost.agent"), size: "2fr", cellRenderer: (r) => r.label },
    {
      label: t("rework.analytics.tables.agentCost.tokens"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.tokens,
      cellRenderer: (r) => num(fmt(r.tokens, "compact")),
    },
    {
      label: t("rework.analytics.tables.agentCost.cost"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.cost_eur,
      cellRenderer: (r) => num(fmt(r.cost_eur, "eur")),
    },
    {
      label: t("rework.analytics.tables.agentCost.perUser"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.cost_eur_per_user ?? 0,
      cellRenderer: (r) => num(fmt(r.cost_eur_per_user, "eur")),
    },
  ];

  const tokensTitle = t(`rework.analytics.charts.tokensOverTime.title.${activity.data?.bucket ?? "day"}`);

  if (allFailed([quality, usage, activity])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <AnalyticsSection id="quality">
        <div className={styles.kpiRow}>
          <InfoTile
            id="failedAnswers"
            period={data?.failed_turn_rate}
            format="percent"
            deltaKind="points"
            lowerIsBetter
            {...tile}
          />
          <InfoTile
            id="singleExchange"
            period={usage.data?.single_exchange_share}
            format="percent"
            deltaKind="points"
            neutralDelta
            isLoading={usage.isLoading}
            isError={usage.isError}
          />
        </div>
      </AnalyticsSection>

      <AnalyticsSection id="cost">
        <div className={styles.kpiRow}>
          <InfoTile
            id="cost"
            period={data?.cost_eur}
            format="eur"
            neutralDelta
            caption={
              data?.cost_eur_per_active_user.current != null
                ? t("rework.analytics.tiles.cost.caption", {
                    value: fmt(data.cost_eur_per_active_user.current, "eur"),
                  })
                : ""
            }
            {...tile}
          />
          <InfoTile
            id="tokens"
            period={data ? tokens : undefined}
            format="compact"
            neutralDelta
            caption={
              data
                ? t("rework.analytics.tiles.tokens.caption", {
                    sent: fmt(sent?.current, "compact"),
                    generated: fmt(generated?.current, "compact"),
                  })
                : ""
            }
            {...tile}
          />
          <InfoTile
            id="footprint"
            period={footprintKg || undefined}
            format="decimal"
            neutralDelta
            caption={
              data?.kwh.current != null
                ? t("rework.analytics.tiles.footprint.caption", { value: fmt(data.kwh.current, "decimal") })
                : ""
            }
            {...tile}
          />
        </div>
        <MultiSeriesLineChart
          title={tokensTitle}
          titleAction={<ChartHint id="tokensOverTime" title={tokensTitle} />}
          rows={bucketSeries(activity.data?.points, activity.data?.bucket, series, lng, t)}
          series={Object.values(series)}
          barSeries={Object.values(series)}
          seriesColors={["--primary", "--primary"]}
          seriesOpacities={[1, 0.45]}
          formatValue={(v) => formatValue(v, "compact", lng)}
          labelled
          stacked
          valueLabel={t("rework.analytics.charts.tokensOverTime.valueLabel")}
          isFetching={activity.isFetching}
          isLoading={activity.isLoading}
          isError={activity.isError}
          flat
        />
        {sent?.current != null && generated?.current != null && (
          <p className={styles.note}>
            {t("rework.analytics.charts.tokensOverTime.periodTotals", {
              sent: fmt(sent.current, "compact"),
              generated: fmt(generated.current, "compact"),
            })}
          </p>
        )}
        <div className={styles.chartGrid}>
          <AnalyticsTable
            id="models"
            columns={modelColumns}
            rows={data?.models}
            rowKey={(r) => r.model}
            isLoading={quality.isLoading}
            isError={quality.isError}
          />
          <AnalyticsTable
            id="agentCost"
            columns={agentColumns}
            rows={agentRows}
            rowKey={(r) => r.key}
            isLoading={quality.isLoading}
            isError={quality.isError}
          />
        </div>
      </AnalyticsSection>
    </div>
  );
}
