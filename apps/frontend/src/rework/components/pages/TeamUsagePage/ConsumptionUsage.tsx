// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import type { AnalyticsResponse, AnalyticsRow } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import BarChart from "@shared/molecules/BarChart/BarChart";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import TokenUsageImpact, { formatImpactEstimate } from "@shared/molecules/TokenUsageImpact/TokenUsageImpact";
import { chartRows, dimension } from "./personalUsage";
import styles from "./TeamUsagePage.module.css";

export interface ConsumptionQuery {
  currentData?: AnalyticsResponse;
  error?: unknown;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
}

/** Scopes and authorization stay with callers; exact counters and estimates share one view. */
export default function ConsumptionUsage({
  title,
  usage,
  detailed = false,
}: {
  title: string;
  usage: ConsumptionQuery;
  detailed?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const results = usage.isError || usage.isFetching ? undefined : usage.currentData?.results;
  const loading = usage.isLoading || usage.isFetching;
  return (
    <Disclosure title={title} defaultOpen>
      <div className={styles.kpiRow}>
        {(["total_tokens", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"] as const).map(
          (key) => {
            const value = results?.total?.rows[0]?.values[`usage.${key}`];
            const previous = results?.previous_total?.rows[0]?.values[`usage.${key}`];
            return (
              <KpiStatCard
                key={key}
                label={t(`rework.consumption.${key}`)}
                value={value === undefined ? undefined : BigInt(value)}
                caption={
                  previous === undefined
                    ? undefined
                    : t("rework.teamAnalytics.previous", { value: BigInt(previous).toLocaleString(i18n.language) })
                }
                unavailable={value === undefined}
                isLoading={loading}
                isError={usage.isError}
              />
            );
          },
        )}
      </div>
      {results && <p>{t("rework.consumption.recorded")}</p>}
      {detailed && results?.previous_impact && (
        <p>
          {t("rework.teamAnalytics.previous", {
            value: formatImpactEstimate(
              results.previous_impact.rows[0]?.estimates?.["usage.cost_eur"],
              "EUR",
              i18n.language,
              t,
            ),
          })}
        </p>
      )}
      <div className={styles.chartGrid}>
        {(["series", "agents", "models"] as const).map((key) => {
          const result = results?.[key];
          const data = chartRows(result);
          const title = t(
            `rework.teamUsage.${key === "series" ? "tokensOverTime" : key === "agents" ? "byAgent" : "byModel"}.title`,
          );
          const rows = data.overflow ? [] : data.rows.map((row) => ({ ...row, value: row.value! }));
          return (
            <div key={key} className={key === "series" ? styles.cellFull : undefined}>
              {data.overflow ? (
                <section aria-label={title}>
                  <h2>{title}</h2>
                  <p role="status">{t("rework.personalAnalytics.chartOverflow")}</p>
                  <DataTable
                    data={data.rows}
                    rowKey={(row) => row.id}
                    pageSize={20}
                    columns={[
                      {
                        label: t("rework.personalAnalytics.dimension"),
                        cellRenderer: (row) => <span title={row.id}>{row.label}</span>,
                      },
                      {
                        label: t("rework.teamUsage.tokensOverTime.valueLabel"),
                        cellRenderer: (row) => BigInt(row.exact).toLocaleString(i18n.language),
                      },
                    ]}
                  />
                </section>
              ) : key === "series" ? (
                <TimeSeriesLineChart
                  title={title}
                  rows={rows.map((row) => ({ date: row.label, value: row.value }))}
                  interval={result?.bucket}
                  isLoading={loading}
                  isFetching={usage.isFetching}
                  isError={usage.isError}
                />
              ) : (
                <BarChart title={title} rows={rows} isLoading={loading} isError={usage.isError} />
              )}
              {detailed && key !== "series" && result && result.rows.length > 0 && (
                <DataTable
                  data={result.rows}
                  rowKey={(row) => dimension(row).id}
                  pageSize={20}
                  columns={[
                    {
                      label: t("rework.personalAnalytics.dimension"),
                      cellRenderer: (row) => <span title={dimension(row).id}>{dimension(row).label}</span>,
                    },
                    ...(["input_tokens", "output_tokens"] as const).map((measure) => ({
                      label: t(`rework.consumption.${measure}`),
                      cellRenderer: (row: AnalyticsRow) =>
                        row.values[`usage.${measure}`] === undefined
                          ? t("common.noData")
                          : BigInt(row.values[`usage.${measure}`]).toLocaleString(i18n.language),
                    })),
                    ...(
                      [
                        ["cost_eur", "EUR"],
                        ["co2e_grams", "g CO2e"],
                        ["energy_kwh", "kWh"],
                      ] as const
                    ).map(([measure, unit]) => ({
                      label: t(`rework.teamAnalytics.${measure}`),
                      cellRenderer: (row: AnalyticsRow) =>
                        formatImpactEstimate(row.estimates?.[`usage.${measure}`], unit, i18n.language, t),
                    })),
                  ]}
                />
              )}
              {result?.truncated && <p role="status">{t("rework.personalAnalytics.truncated")}</p>}
              {key === "series" && (
                <TokenUsageImpact
                  estimates={results?.impact?.rows[0]?.estimates ?? {}}
                  isLoading={loading}
                  isError={usage.isError}
                />
              )}
            </div>
          );
        })}
      </div>
    </Disclosure>
  );
}
