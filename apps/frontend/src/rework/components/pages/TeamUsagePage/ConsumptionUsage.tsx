// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import type { AnalyticsResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import BarChart from "@shared/molecules/BarChart/BarChart";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact";
import { chartRows } from "./personalUsage";
import styles from "./TeamUsagePage.module.css";

export interface ConsumptionQuery {
  currentData?: AnalyticsResponse;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
}

/** Scopes and authorization stay with callers; exact counters and estimates share one view. */
export default function ConsumptionUsage({ title, usage }: { title: string; usage: ConsumptionQuery }) {
  const { t, i18n } = useTranslation();
  const results = usage.isError || usage.isFetching ? undefined : usage.currentData?.results;
  const loading = usage.isLoading || usage.isFetching;
  return (
    <Disclosure title={title} defaultOpen>
      <div className={styles.kpiRow}>
        {(["total_tokens", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"] as const).map(
          (key) => {
            const value = results?.total?.rows[0]?.values[`usage.${key}`];
            return (
              <KpiStatCard
                key={key}
                label={t(`rework.consumption.${key}`)}
                value={value === undefined ? undefined : BigInt(value)}
                unavailable={value === undefined}
                isLoading={loading}
                isError={usage.isError}
              />
            );
          },
        )}
      </div>
      {results && <p>{t("rework.consumption.recorded")}</p>}
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
