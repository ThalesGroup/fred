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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  useAnalyticsTeamsCatalogQuery,
  useAnalyticsTeamsQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PeriodValue } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import { AnalyticsSection, AnalyticsServiceDown } from "../AnalyticsSection";
import AnalyticsTable, { TableHint } from "../AnalyticsTable";
import { BarCell } from "../RankedBars";
import { formatValue, NO_VALUE, periodDelta, type TeamRow, teamRows } from "../analyticsFormat";
import { type AnalyticsTabProps, KPI_CACHE, kpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

/** Colors a change as shown (one decimal): a displayed 0 % stays uncolored. */
function changeClass(change: number): string {
  const shown = Math.round(change * 1000);
  return shown > 0 ? styles.positive : shown < 0 ? styles.negative : "";
}

/** ▲/▼ for a change as shown, so it reads without colour. */
function changeGlyph(change: number): string {
  const shown = Math.round(change * 1000);
  return shown > 0 ? "▲" : shown < 0 ? "▼" : "";
}

interface ConversationScopeBarProps {
  team: number;
  personal: number;
  /** Team share now and before: its change closes the counts line. */
  share?: PeriodValue;
  emptyMessage: string;
  isLoading: boolean;
  isError: boolean;
}

/** Team and personal conversations as one horizontal bar of two labelled shares. */
function ConversationScopeBar({ team, personal, share, emptyMessage, isLoading, isError }: ConversationScopeBarProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const total = team + personal;
  const change = periodDelta(share, "points", t, lng);
  const segments = [
    { key: "team", value: team, className: styles.scopeTeam },
    { key: "personal", value: personal, className: styles.scopePersonal },
  ]
    .filter((s) => s.value > 0)
    .map((s) => ({
      ...s,
      label: `${t(`rework.analytics.conversationsByScope.${s.key}`)} · ${formatValue(s.value / total, "percent", lng)}`,
    }));
  return (
    <div className={styles.stack}>
      {isError ? (
        <p role="alert" className={styles.note}>
          {t("common.loadingError")}
        </p>
      ) : isLoading ? (
        <p role="status" className={styles.note}>
          {t("common.loading")}
        </p>
      ) : total === 0 ? (
        <p role="status" className={styles.note}>
          {emptyMessage}
        </p>
      ) : (
        <>
          <div className={styles.scopeBar} role="img" aria-label={segments.map((s) => s.label).join(", ")}>
            {segments.map((s) => (
              <span key={s.key} className={s.className} style={{ width: `${(s.value / total) * 100}%` }}>
                {s.label}
              </span>
            ))}
          </div>
          <p className={`${styles.note} ${styles.scopeLegend}`}>
            <span>
              {t("rework.analytics.conversationsByScope.teamCount", {
                count: team,
                value: formatValue(team, "count", lng),
              })}
            </span>
            <span>
              {t("rework.analytics.conversationsByScope.personalCount", {
                count: personal,
                value: formatValue(personal, "count", lng),
              })}
            </span>
            {change && (
              <span
                className={
                  change.tone === "positive" ? styles.positive : change.tone === "negative" ? styles.negative : ""
                }
              >
                {change.direction && <span aria-hidden>{change.direction === "up" ? "▲ " : "▼ "}</span>}
                {t("rework.analytics.conversationsByScope.shareChange", { change: change.label })}
              </span>
            )}
          </p>
        </>
      )}
    </div>
  );
}

export default function TeamsTab({ timeRange, teamIds, mode = "platform", userFilter }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language;
  const teams = useAnalyticsTeamsQuery(kpiArgs(timeRange, teamIds, userFilter), KPI_CACHE);
  // A team admin may only list their own team.
  const catalog = useAnalyticsTeamsCatalogQuery(mode === "team" ? { teamIds } : {}, KPI_CACHE);
  const data = teams.data;
  const teamScoped = teamIds.length > 0;

  const rows = useMemo(
    () => teamRows(data?.rows ?? [], catalog.data?.rows ?? [], teamIds),
    [data, catalog.data, teamIds],
  );

  const column = (
    key: string,
    size: string,
    render: (r: TeamRow) => string,
    sortValue: (r: TeamRow) => number | string | null,
  ) =>
    ({
      label: t(`rework.analytics.tables.teams.${key}`),
      size,
      sortable: true,
      sortValue,
      cellRenderer: (r: TeamRow) => <span className={styles.numeric}>{render(r)}</span>,
    }) satisfies DataTableColumn<TeamRow>;
  const columns: DataTableColumn<TeamRow>[] = [
    {
      label: t("rework.analytics.tables.teams.team"),
      size: "2fr",
      sortable: true,
      sortValue: (r) => r.name,
      cellRenderer: (r) => r.name,
    },
    column(
      "members",
      "1fr",
      (r) => (r.members == null ? NO_VALUE : formatValue(r.members, "count", lng)),
      (r) => r.members,
    ),
    column(
      "active",
      "1fr",
      (r) => formatValue(r.active, "count", lng),
      (r) => r.active,
    ),
    {
      label: t("rework.analytics.tables.teams.share"),
      size: "2fr",
      sortable: true,
      sortValue: (r) => r.share,
      cellRenderer: (r) => <BarCell share={r.share} />,
    },
    column(
      "messages",
      "1fr",
      (r) => formatValue(r.messages, "count", lng),
      (r) => r.messages,
    ),
    {
      label: t("rework.analytics.tables.teams.change"),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.change,
      cellRenderer: (r) =>
        r.change == null ? (
          NO_VALUE
        ) : (
          <span className={`${styles.numeric} ${changeClass(r.change)}`}>
            {changeGlyph(r.change) && <span aria-hidden>{changeGlyph(r.change)} </span>}
            {(Math.round(r.change * 1000) > 0 ? "+" : "") + formatValue(r.change, "percent", lng)}
          </span>
        ),
    },
  ];

  if (teams.isError && catalog.isError) return <AnalyticsServiceDown />;

  // One team: its own members, without the cross-team split or table.
  if (mode === "team") {
    const row = rows[0];
    const card = { isLoading: teams.isLoading, isError: teams.isError, nested: true };
    return (
      <div className={styles.tabContent}>
        <AnalyticsSection id="members">
          <div className={styles.kpiRow}>
            <KpiStatCard label={t("rework.analytics.tables.teams.members")} value={row?.members} {...card} />
            <KpiStatCard label={t("rework.analytics.tables.teams.active")} value={row?.active} {...card} />
            <KpiStatCard
              label={t("rework.analytics.tables.teams.share")}
              value={row?.share}
              displayValue={row?.share != null ? formatValue(row.share, "percent", lng) : undefined}
              {...card}
            />
          </div>
        </AnalyticsSection>
      </div>
    );
  }

  return (
    <div className={styles.tabContent}>
      <AnalyticsSection id="collective">
        <ConversationScopeBar
          team={teamScoped ? 0 : (data?.team_conversations?.current ?? 0)}
          personal={teamScoped ? 0 : (data?.personal_conversations?.current ?? 0)}
          share={teamScoped ? undefined : data?.team_share}
          emptyMessage={t(
            teamScoped ? "rework.analytics.scope.notForTeams" : "rework.analytics.conversationsByScope.empty",
          )}
          isLoading={teams.isLoading}
          isError={teams.isError}
        />
      </AnalyticsSection>
      <AnalyticsSection
        id="diffusion"
        aside={
          <>
            {data &&
              t("rework.analytics.tables.teams.activeTeams", {
                active: formatValue(data.active_teams.current ?? 0, "count", lng),
                count: teamScoped ? teamIds.length : (catalog.data?.rows.length ?? 0),
              })}
            <TableHint id="teams" />
          </>
        }
      >
        <AnalyticsTable
          id="teams"
          hideTitle
          columns={columns}
          rows={rows}
          rowKey={(r) => r.teamId}
          isLoading={teams.isLoading}
          isError={teams.isError}
        />
      </AnalyticsSection>
    </div>
  );
}
