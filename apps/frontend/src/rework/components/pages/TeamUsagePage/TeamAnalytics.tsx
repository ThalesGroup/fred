// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useTranslation } from "react-i18next";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";
import type { ConsumptionQuery } from "./ConsumptionUsage";
import { chartInteger, dimension } from "./personalUsage";
import { analyticsErrorKey } from "./teamAnalytics";
import styles from "./TeamUsagePage.module.css";

export default function TeamAnalytics({
  history,
  consumption,
  agents,
  inventory,
  tools,
}: {
  history: ConsumptionQuery;
  consumption: ConsumptionQuery;
  agents: boolean;
  inventory: ConsumptionQuery;
  tools: ConsumptionQuery;
}) {
  const { t, i18n } = useTranslation();
  const results = history.isError || history.isFetching ? undefined : history.currentData?.results;
  const sql = consumption.isError || consumption.isFetching ? undefined : consumption.currentData?.results;
  const loading = history.isLoading || history.isFetching;
  if (history.isError) return <p role="alert">{t(analyticsErrorKey(history.error))}</p>;
  const series = results?.turn_series;
  const rows = series?.rows.map((row) => ({
    ...dimension(row),
    exact: row.values["activity.completed_turns"],
    value: chartInteger(row.values["activity.completed_turns"]),
  }));
  const skills = results?.skills;
  return (
    <>
      <p>{t("rework.teamAnalytics.observed")}</p>
      <div className={styles.kpiRow}>
        {(agents
          ? (["agents_used"] as const)
          : ([
              "active_users",
              "observed_conversations",
              "completed_turns",
              "failed_turns",
              "single_turn_conversations",
            ] as const)
        ).map((key) => {
          const value = results?.turns?.rows[0]?.values[`activity.${key}`];
          const previous = results?.previous_turns?.rows[0]?.values[`activity.${key}`];
          return (
            <KpiStatCard
              key={key}
              label={t(`rework.teamAnalytics.${key}`)}
              hint={t(`rework.teamAnalytics.${key}Hint`)}
              value={value === undefined ? undefined : BigInt(value)}
              unavailable={value === undefined}
              noDataLabel={t("rework.teamAnalytics.unavailableValue")}
              caption={
                previous === undefined
                  ? undefined
                  : t("rework.teamAnalytics.previous", { value: BigInt(previous).toLocaleString(i18n.language) })
              }
              isLoading={loading}
              isError={history.isError}
            />
          );
        })}
        {!agents && (
          <KpiStatCard
            label={t("rework.teamAnalytics.conversations")}
            hint={t("rework.teamAnalytics.conversationsHint")}
            value={
              sql?.conversations?.rows[0]?.values["activity.retained_conversations"] === undefined
                ? undefined
                : BigInt(sql.conversations.rows[0].values["activity.retained_conversations"])
            }
            unavailable={!sql?.conversations}
            isLoading={consumption.isLoading || consumption.isFetching}
            isError={consumption.isError}
          />
        )}
      </div>
      {!agents &&
        (rows?.some((row) => row.value === undefined) ? (
          <>
            <p role="status">{t("rework.personalAnalytics.chartOverflow")}</p>
            <DataTable
              data={rows}
              rowKey={(row) => row.id}
              pageSize={20}
              columns={[
                { label: t("rework.personalAnalytics.dimension"), cellRenderer: (row) => row.label },
                {
                  label: t("rework.teamAnalytics.completed_turns"),
                  cellRenderer: (row) => BigInt(row.exact).toLocaleString(i18n.language),
                },
              ]}
            />
          </>
        ) : (
          <TimeSeriesLineChart
            title={t("rework.teamAnalytics.turnSeries")}
            rows={(rows ?? []).map((row) => ({ date: row.label, value: row.value! }))}
            interval={series?.bucket}
            isLoading={loading}
            isFetching={history.isFetching}
            isError={false}
          />
        ))}
      <MetricTable query={inventory} name={agents ? "inventory" : "creators"} />
      {!agents && <MetricTable query={history} name="statistics" />}
      {agents && <MetricTable query={tools} name="tools" />}
      {agents && <MetricTable query={tools} name="tool_ranking" />}
      {agents && (
        <>
          <h2>{t("rework.teamAnalytics.agentRanking")}</h2>
          {loading ? (
            <p role="status">{t("common.loading")}</p>
          ) : !results?.turn_agents ? (
            <p role="status">{t("rework.teamAnalytics.unavailable")}</p>
          ) : !results.turn_agents.rows.length ? (
            <p role="status">{t("common.noData")}</p>
          ) : (
            <DataTable
              data={results.turn_agents.rows}
              rowKey={(row) => dimension(row).id}
              pageSize={20}
              columns={[
                {
                  label: t("rework.personalAnalytics.agent"),
                  cellRenderer: (row) => (
                    <Tooltip content={dimension(row).id} asChild>
                      <span tabIndex={0}>{dimension(row).label}</span>
                    </Tooltip>
                  ),
                },
                {
                  label: t("rework.teamAnalytics.completed_turns"),
                  cellRenderer: (row) => BigInt(row.values["activity.completed_turns"]).toLocaleString(i18n.language),
                },
              ]}
            />
          )}
          {results?.turn_agents?.truncated && <p role="status">{t("rework.personalAnalytics.truncated")}</p>}
          <SkillUsageTable
            agentLabel={t("rework.personalAnalytics.agent")}
            data={
              skills
                ? {
                    truncated: skills.truncated,
                    rows: skills.rows.flatMap((row) =>
                      row.dimensions.kind === "skill"
                        ? [
                            {
                              skill_name: row.dimensions.name,
                              user_count: BigInt(row.values["skills.user_loads"]),
                              model_count: BigInt(row.values["skills.agent_loads"]),
                              total: BigInt(row.values["skills.total_loads"]),
                            },
                          ]
                        : [],
                    ),
                  }
                : undefined
            }
            isLoading={loading}
            isError={false}
          />
          <p>{t("rework.teamAnalytics.skillsHint")}</p>
        </>
      )}
    </>
  );
}

/** Exact decimal strings are rendered as returned; missing values never become zero. */
function MetricTable({ query, name }: { query: ConsumptionQuery; name: string }) {
  const { t } = useTranslation();
  if (query.isError) return <p role="alert">{t(analyticsErrorKey(query.error))}</p>;
  if (query.isFetching || query.isLoading) return <p role="status">{t("common.loading")}</p>;
  const result = query.currentData?.results[name];
  const previous = query.currentData?.results[`previous_${name}`];
  const rows =
    result?.rows.flatMap((row) =>
      result.measures.map((measure) => ({
        id: `${dimension(row).id}/${measure.id}`,
        stock: measure.id === "inventory.enabled_agents",
        notCollected: measure.id === "inventory.agents_published",
        label: t(`rework.teamAnalytics.metrics.${measure.id}`),
        hint: t(`rework.teamAnalytics.metricHints.${measure.id}`),
        tool: row.dimensions.kind === "tool" ? row.dimensions.name : undefined,
        value: row.values[measure.id],
        previous: measure.id === "inventory.enabled_agents" ? undefined : previous?.rows[0]?.values[measure.id],
      })),
    ) ?? [];
  return (
    <>
      <h2>{t(`rework.teamAnalytics.${name}Title`)}</h2>
      <p>{t(`rework.teamAnalytics.${name}Hint`)}</p>
      <DataTable
        data={rows}
        rowKey={(row) => row.id}
        pageSize={20}
        columns={[
          {
            label: t("rework.teamAnalytics.measure"),
            cellRenderer: (row) => (
              <Tooltip content={row.hint} asChild>
                <span tabIndex={0}>
                  {row.tool ? `${row.tool} · ` : ""}
                  {row.label}
                </span>
              </Tooltip>
            ),
          },
          {
            label: t("rework.teamAnalytics.currentValue"),
            cellRenderer: (row) =>
              row.notCollected
                ? t("rework.teamAnalytics.notCollected")
                : (row.value ?? t("rework.teamAnalytics.unavailableValue")),
          },
          {
            label: t("rework.teamAnalytics.previousValue"),
            cellRenderer: (row) =>
              row.stock
                ? t("rework.teamAnalytics.notApplicable")
                : row.notCollected
                  ? t("rework.teamAnalytics.notCollected")
                  : (row.previous ?? t("rework.teamAnalytics.unavailableValue")),
          },
        ]}
      />
      {!result && <p role="status">{t("rework.teamAnalytics.unavailable")}</p>}
      {result?.truncated && <p role="status">{t("rework.personalAnalytics.truncated")}</p>}
    </>
  );
}
