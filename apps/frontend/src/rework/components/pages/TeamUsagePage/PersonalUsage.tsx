// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import type { AnalyticsResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import BarChart from "@shared/molecules/BarChart/BarChart";
import DataTable from "@shared/molecules/DataTable/LocalizedDataTable";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact";
import { chartRows } from "./personalUsage";
import styles from "./TeamUsagePage.module.css";

interface Query {
  currentData?: AnalyticsResponse;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
}

export default function PersonalUsage({
  organizationId,
  usage,
  skills,
  withSkills,
}: {
  organizationId?: string;
  usage: Query;
  skills: Query;
  withSkills: boolean;
}) {
  const { t, i18n } = useTranslation();
  if (!organizationId)
    return (
      <>
        <Disclosure title={t("rework.teamUsage.personalSectionTitle")} defaultOpen>
          <p role="status">{t("rework.personalAnalytics.organizationRequired")}</p>
        </Disclosure>
        {withSkills && (
          <Disclosure title={t("rework.teamUsage.personalSkillsSectionTitle")} defaultOpen>
            <p role="status">{t("rework.personalAnalytics.organizationRequired")}</p>
          </Disclosure>
        )}
      </>
    );
  const results = usage.isError ? undefined : usage.currentData?.results;
  const skillResult = !withSkills || skills.isError ? undefined : skills.currentData?.results.skills;
  const loading = usage.isLoading || (usage.isFetching && !results);
  const total = results?.total?.rows[0]?.values["usage.total_tokens"];
  const skillRows = skillResult?.rows.flatMap((row) =>
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
  );
  return (
    <>
      {withSkills && (
        <Disclosure title={t("rework.teamUsage.personalSkillsSectionTitle")} defaultOpen>
          <SkillUsageTable
            agentLabel={t("rework.personalAnalytics.agent")}
            data={skillRows ? { rows: skillRows, truncated: skillResult?.truncated } : undefined}
            isLoading={skills.isLoading || (skills.isFetching && !skillResult)}
            isError={skills.isError}
          />
          {!skills.isError && skillResult && <p>{t("rework.personalAnalytics.observed")}</p>}
        </Disclosure>
      )}
      <Disclosure title={t("rework.teamUsage.personalSectionTitle")} defaultOpen>
        {total !== undefined && (
          <p>{t("rework.personalAnalytics.total", { value: BigInt(total).toLocaleString(i18n.language) })}</p>
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
                {result?.truncated && <p role="status">{t("rework.personalAnalytics.truncated")}</p>}
                {key === "series" && (
                  <TokenUsageImpact
                    estimates={results?.impact?.rows[0]?.estimates}
                    isLoading={loading}
                    isError={usage.isError}
                  />
                )}
              </div>
            );
          })}
        </div>
      </Disclosure>
    </>
  );
}
