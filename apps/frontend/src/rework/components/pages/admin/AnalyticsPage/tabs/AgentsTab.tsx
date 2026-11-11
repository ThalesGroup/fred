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
  useAgentsTotalQuery,
  useAnalyticsAgentsQuery,
  useSkillUsageQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AnalyticsCapabilityRow, SkillUsageRow } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import { AnalyticsSection, AnalyticsServiceDown, ChartHint } from "../AnalyticsSection";
import { BarCell, RankedList, SplitCell } from "../RankedBars";
import AnalyticsTable, { TableHint } from "../AnalyticsTable";
import InfoTile from "../InfoTile";
import { formatValue, NO_VALUE } from "../analyticsFormat";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, kpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

export default function AgentsTab({ timeRange, teamIds, mode = "platform", userFilter }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const args = kpiArgs(timeRange, teamIds, userFilter);
  const agents = useAnalyticsAgentsQuery(args, KPI_CACHE);
  // Agents existing today: configuration, not narrowed by a user filter.
  const agentsTotal = useAgentsTotalQuery(kpiArgs(timeRange, teamIds), KPI_CACHE);
  const skills = useSkillUsageQuery(args, KPI_CACHE);
  const data = agents.data;
  const tile = { isLoading: agents.isLoading, isError: agents.isError };
  const existing = agentsTotal.data?.value;
  const published = data?.agents_created_published.current;

  // Rate cells are empty when there is nothing to divide by.
  const ratio = (part: number, whole: number) => (whole > 0 ? part / whole : null);
  const numeric = (value: number | null, format: "count" | "percent") => (
    <span className={styles.numeric}>{value == null ? NO_VALUE : formatValue(value, format, i18n.language)}</span>
  );
  const capabilityColumn = (
    key: string,
    value: (r: AnalyticsCapabilityRow) => number | null,
    format: "count" | "percent" = "count",
  ) => ({
    label: t(`rework.analytics.tables.capabilities.${key}`),
    size: "1fr",
    sortable: true,
    sortValue: (r: AnalyticsCapabilityRow) => value(r) ?? -1,
    cellRenderer: (r: AnalyticsCapabilityRow) => numeric(value(r), format),
  });
  // Under this rate a capability is mostly on "just in case": shown in warning colour.
  const LOW_USAGE = 0.3;
  const capabilityColumns = [
    {
      label: t("rework.analytics.tables.capabilities.capability"),
      size: "2fr",
      sortable: true,
      sortValue: (r: AnalyticsCapabilityRow) => r.capability_id,
      // Capability names are catalog keys; an unknown one shows its id.
      cellRenderer: (r: AnalyticsCapabilityRow) =>
        t(`capability.${r.capability_id}.name`, { defaultValue: r.capability_id }),
    },
    capabilityColumn("equipped", (r) => r.agents_equipped),
    capabilityColumn("used", (r) => r.agents_used ?? 0),
    {
      ...capabilityColumn("usageRate", (r) => ratio(r.agents_used ?? 0, r.agents_equipped), "percent"),
      size: "2fr",
      cellRenderer: (r: AnalyticsCapabilityRow) => {
        const rate = ratio(r.agents_used ?? 0, r.agents_equipped);
        const low = rate != null && rate < LOW_USAGE;
        return <BarCell share={rate} theme={low ? "warning" : "tertiary"} emphasize={low} />;
      },
    },
    capabilityColumn("calls", (r) => r.calls ?? 0),
    capabilityColumn("users", (r) => r.users ?? 0),
    capabilityColumn("failed", (r) => ratio(r.failed_calls ?? 0, r.calls ?? 0), "percent"),
  ];

  const skillKey = "rework.analytics.tables.skills";
  const skillColumns: DataTableColumn<SkillUsageRow>[] = [
    {
      label: t(`${skillKey}.skill`),
      size: "2fr",
      sortable: true,
      sortValue: (r) => r.skill_name,
      cellRenderer: (r) => r.skill_name,
    },
    {
      label: t(`${skillKey}.loads`),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.total,
      cellRenderer: (r) => numeric(r.total, "count"),
    },
    {
      label: t(`${skillKey}.split`),
      size: "3fr",
      sortable: true,
      sortValue: (r) => (r.total ? r.user_count / r.total : 0),
      cellRenderer: (r) => <SplitCell first={r.user_count} second={r.model_count} label={t(`${skillKey}.split`)} />,
    },
  ];
  const topAgentsTitle = t("rework.analytics.charts.topAgents.title");

  if (allFailed([agents, skills])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <AnalyticsSection id="agents">
        <div className={styles.asideMain}>
          <div className={styles.stack}>
            <InfoTile
              id="agentsUsed"
              period={data?.agents_used}
              caption={
                existing != null ? t("rework.analytics.tiles.agentsUsed.caption", { count: existing }) : undefined
              }
              {...tile}
            />
            <InfoTile
              id="agentsCreated"
              period={data?.agents_created}
              caption={
                published != null
                  ? t("rework.analytics.tiles.agentsCreated.published", { count: published })
                  : undefined
              }
              {...tile}
            />
          </div>
          <RankedList
            title={topAgentsTitle}
            titleAction={<ChartHint id="topAgents" title={topAgentsTitle} />}
            rows={(data?.top_agents ?? []).map((a, i) => ({
              key: `${i}-${a.label}`,
              label: a.label,
              value: a.conversations,
              valueText: `${t("rework.analytics.charts.topAgents.conversations", {
                count: a.conversations,
                value: formatValue(a.conversations, "count", i18n.language),
              })} · ${t("rework.analytics.charts.topAgents.users", {
                count: a.users,
                value: formatValue(a.users, "count", i18n.language),
              })}`,
            }))}
            emptyMessage={t("rework.analytics.charts.topAgents.empty")}
            isLoading={agents.isLoading}
            isError={agents.isError}
          />
        </div>
      </AnalyticsSection>

      <AnalyticsSection id="capabilities" aside={<TableHint id="capabilities" />}>
        <AnalyticsTable
          id="capabilities"
          hideTitle
          columns={capabilityColumns}
          rows={data?.capabilities}
          rowKey={(r) => r.capability_id}
          isLoading={agents.isLoading}
          isError={agents.isError}
        />
      </AnalyticsSection>

      {/* currentData, not data: a previous range's rows must not show while the new one loads. */}
      <AnalyticsSection id="skills">
        <AnalyticsTable
          id="skills"
          hideTitle
          columns={skillColumns}
          rows={skills.currentData?.rows}
          rowKey={(r) => r.skill_name}
          isLoading={skills.isLoading || (skills.isFetching && !skills.currentData)}
          isError={skills.isError}
        />
        {!!skills.currentData?.rows.length && (
          <ul className={styles.legend}>
            <li>
              <span className={`${styles.legendSwatch} ${styles.splitFirst}`} aria-hidden />
              {t(`${skillKey}.byUser`)}
            </li>
            <li>
              <span className={`${styles.legendSwatch} ${styles.splitSecond}`} aria-hidden />
              {t(`${skillKey}.byModel`)}
            </li>
          </ul>
        )}
        {skills.currentData?.truncated && <p className={styles.note}>{t("rework.analytics.skillUsage.truncated")}</p>}
      </AnalyticsSection>

      <AnalyticsSection id="knowledge">
        <div className={styles.kpiRow}>
          <InfoTile id="documentsAdded" period={data?.documents_added} {...tile} />
          {/* Cross-team figures: a team's page has nothing to show there. */}
          {mode === "platform" && (
            <>
              <InfoTile id="teamsFeedingCorpus" period={data?.teams_feeding_corpus} deltaKind="absolute" {...tile} />
              <InfoTile
                id="corpusSearches"
                period={teamIds.length > 0 ? null : data?.corpus_searches}
                {...(teamIds.length > 0 && { noDataLabel: t("rework.analytics.scope.notForTeamsShort") })}
                {...tile}
              />
            </>
          )}
        </div>
      </AnalyticsSection>
    </div>
  );
}
