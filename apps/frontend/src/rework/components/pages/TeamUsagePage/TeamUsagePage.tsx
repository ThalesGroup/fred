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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./TeamUsagePage.module.css";
import {
  useAgentsTotalQuery,
  useDocumentsTotalQuery,
  useSessionsOverTimeQuery,
  useStorageByTeamQuery,
  useTeamActivitySummaryQuery,
  useTokenUsageByAgentQuery,
  useTokenUsageByModelQuery,
  useTokenUsageOverTimeQuery,
  useTopAgentsByConversationsQuery,
  useUserTokenUsageOverTimeQuery,
  useUserTokenUsageByAgentQuery,
  useUserTokenUsageByModelQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { TIME_PRESETS } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import BarChart from "@shared/molecules/BarChart/BarChart";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
import TaskActivity from "@shared/organisms/TaskActivity/TaskActivity.tsx";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { hasElevatedTeamRole } from "@hooks/teamCapabilities.ts";

const defaultPreset = TIME_PRESETS.find((p) => p.key === "last30d")!;
const defaultRange: TimeRange = { ...defaultPreset.resolve(), presetKey: "last30d" };

/**
 * Personal token-usage dashboard — OBSERV-02 / BACKLOG.md §7b — extended in
 * place (v3, §2.5 Page 2) with capability-conditional team sections prepended
 * above it. In-page gating only, no route guard (`FRONTEND-AUTHZ-PATTERN.md`):
 * a plain `team_member` (or anyone on a personal team, which has no elevated
 * roles at all) sees only the personal section below, unchanged.
 */
export default function TeamUsagePage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);

  const { teamId, selectedTeam } = useSelectedTeam();
  const capabilities = useTeamCapabilities(selectedTeam);
  const elevated = hasElevatedTeamRole(capabilities);
  // §2.4/schema.fga: can_update_info is team_admin-only; can_update_resources
  // (like can_update_agents) is team_editor-only — the two roles this page's
  // additional sections are gated on.
  const isTeamAdmin = capabilities.canUpdateInfo;
  const isTeamEditor = capabilities.canUpdateResources;

  const {
    data: overTimeData,
    isLoading: overTimeIsLoading,
    isFetching: overTimeIsFetching,
    isError: overTimeIsError,
  } = useUserTokenUsageOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  const {
    data: byAgentData,
    isLoading: byAgentIsLoading,
    isError: byAgentIsError,
  } = useUserTokenUsageByAgentQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  const {
    data: byModelData,
    isLoading: byModelIsLoading,
    isError: byModelIsError,
  } = useUserTokenUsageByModelQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  // Team-scoped shared section (§2.5 Page 2) — skipped entirely for anyone
  // without an elevated role, both to avoid the wasted/rejected call and
  // because `hasElevatedTeamRole` is this frontend's single source of truth
  // for the distinction.
  const teamArgs = { since: timeRange.since, until: timeRange.until, teamId };
  const teamQueryOpts = { skip: !elevated || !teamId, refetchOnMountOrArgChange: true };

  const { data: teamAgentsTotalData, isLoading: teamAgentsTotalIsLoading } = useAgentsTotalQuery(
    teamArgs,
    teamQueryOpts,
  );
  const { data: teamDocumentsTotalData, isLoading: teamDocumentsTotalIsLoading } = useDocumentsTotalQuery(
    teamArgs,
    teamQueryOpts,
  );
  const {
    data: teamTopAgentsData,
    isLoading: teamTopAgentsIsLoading,
    isFetching: teamTopAgentsIsFetching,
    isError: teamTopAgentsIsError,
  } = useTopAgentsByConversationsQuery(teamArgs, teamQueryOpts);
  const {
    data: teamSessionsData,
    isLoading: teamSessionsIsLoading,
    isFetching: teamSessionsIsFetching,
    isError: teamSessionsIsError,
  } = useSessionsOverTimeQuery(teamArgs, teamQueryOpts);
  const {
    data: teamTokenOverTimeData,
    isLoading: teamTokenOverTimeIsLoading,
    isFetching: teamTokenOverTimeIsFetching,
    isError: teamTokenOverTimeIsError,
  } = useTokenUsageOverTimeQuery(teamArgs, teamQueryOpts);
  const {
    data: teamTokenByAgentData,
    isLoading: teamTokenByAgentIsLoading,
    isError: teamTokenByAgentIsError,
  } = useTokenUsageByAgentQuery(teamArgs, teamQueryOpts);
  const {
    data: teamTokenByModelData,
    isLoading: teamTokenByModelIsLoading,
    isError: teamTokenByModelIsError,
  } = useTokenUsageByModelQuery(teamArgs, teamQueryOpts);
  const {
    data: teamStorageData,
    isLoading: teamStorageIsLoading,
    isError: teamStorageIsError,
  } = useStorageByTeamQuery(teamArgs, teamQueryOpts);
  const teamStorageRows = useMemo(
    () =>
      (teamStorageData?.rows ?? [])
        .filter((r) => r.quota_bytes != null && r.quota_bytes > 0)
        .map((r) => ({ label: r.label, value: Math.round((r.used_bytes / r.quota_bytes!) * 100) })),
    [teamStorageData],
  );

  // team_admin's governance summary (§2.5) — team_id is required by this
  // preset, so it only ever fires once both an elevated role and a team are
  // resolved, same gate as every other team-scoped query above.
  const { data: activitySummaryData, isLoading: activitySummaryIsLoading } = useTeamActivitySummaryQuery(teamArgs, {
    skip: !isTeamAdmin || !teamId,
    refetchOnMountOrArgChange: true,
  });

  const handleRangeChange = (range: TimeRange) => {
    setTimeRange(range);
  };

  const handleRefresh = () => {
    if (timeRange.presetKey) {
      const preset = TIME_PRESETS.find((p) => p.key === timeRange.presetKey)!;
      setTimeRange({ ...preset.resolve(), presetKey: timeRange.presetKey });
    }
  };

  const serviceDown = [overTimeIsError, byAgentIsError, byModelIsError].every(Boolean);

  if (serviceDown) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <h1 className={styles.title}>{t("rework.teamUsage.title")}</h1>
        </div>
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.controlPlane.title")}
          description={t("rework.serviceNotice.controlPlane.description")}
          centered
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.teamUsage.title")}</h1>
        <div className={styles.headerControls}>
          <TimeRangeSelector value={timeRange} onChange={handleRangeChange} />
          <IconButton
            color="primary"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh" }}
            onClick={handleRefresh}
            disabled={overTimeIsFetching}
            title={t("common.refresh")}
          />
        </div>
      </div>

      {isTeamAdmin && teamId && (
        <Disclosure title={t("rework.teamUsage.team.adminSectionTitle")} defaultOpen>
          <div className={styles.sectionStack}>
            {activitySummaryData && !activitySummaryIsLoading && (
              <p className={styles.activitySummary}>
                {t(
                  activitySummaryData.trend === "active"
                    ? "rework.teamUsage.team.activitySummary.active"
                    : "rework.teamUsage.team.activitySummary.quiet",
                  { count: activitySummaryData.sessions_in_range },
                )}
              </p>
            )}
            <TaskActivity scope="team" teamId={teamId} />
          </div>
        </Disclosure>
      )}

      {isTeamEditor && teamId && (
        <Disclosure title={t("rework.teamUsage.team.editorSectionTitle")} defaultOpen>
          <TaskActivity scope="team" teamId={teamId} kind="ingestion" />
        </Disclosure>
      )}

      {elevated && teamId && (
        <Disclosure title={t("rework.teamUsage.team.sectionTitle")} defaultOpen>
          <div className={styles.kpiRow}>
            <KpiStatCard
              label={t("rework.teamUsage.team.membersLabel")}
              value={selectedTeam?.member_count ?? undefined}
              isLoading={false}
              isError={false}
            />
            <KpiStatCard
              label={t("rework.teamUsage.team.agentsLabel")}
              value={teamAgentsTotalData?.value}
              delta={teamAgentsTotalData?.delta}
              unavailable={teamAgentsTotalData?.unavailable}
              isLoading={teamAgentsTotalIsLoading}
              isError={false}
            />
            <KpiStatCard
              label={t("rework.teamUsage.team.documentsLabel")}
              value={teamDocumentsTotalData?.value}
              delta={teamDocumentsTotalData?.delta}
              unavailable={teamDocumentsTotalData?.unavailable}
              isLoading={teamDocumentsTotalIsLoading}
              isError={false}
            />
          </div>

          <div className={styles.chartGrid}>
            <div className={styles.cellFull}>
              <TimeSeriesLineChart
                title={t("rework.analytics.tokenUsage.overTime.title")}
                rows={teamTokenOverTimeData?.rows ?? []}
                interval={teamTokenOverTimeData?.interval}
                valueLabel={t("rework.analytics.tokenUsage.overTime.valueLabel")}
                isFetching={teamTokenOverTimeIsFetching}
                isLoading={teamTokenOverTimeIsLoading}
                isError={teamTokenOverTimeIsError}
              />
              <TokenUsageImpact rows={teamTokenOverTimeData?.rows} isLoading={teamTokenOverTimeIsLoading} />
            </div>
            <BarChart
              title={t("rework.analytics.tokenUsage.byAgent.title")}
              rows={teamTokenByAgentData?.rows ?? []}
              valueLabel={t("rework.analytics.tokenUsage.byAgent.valueLabel")}
              emptyMessage={t("rework.analytics.tokenUsage.byAgent.empty")}
              isLoading={teamTokenByAgentIsLoading}
              isError={teamTokenByAgentIsError}
            />
            <BarChart
              title={t("rework.analytics.tokenUsage.byModel.title")}
              rows={teamTokenByModelData?.rows ?? []}
              valueLabel={t("rework.analytics.tokenUsage.byModel.valueLabel")}
              emptyMessage={t("rework.analytics.tokenUsage.byModel.empty")}
              isLoading={teamTokenByModelIsLoading}
              isError={teamTokenByModelIsError}
            />
            <BarChart
              title={t("rework.teamUsage.team.quota.title")}
              rows={teamStorageRows}
              valueLabel={t("rework.teamUsage.team.quota.valueLabel")}
              emptyMessage={t("rework.teamUsage.team.quota.empty")}
              isLoading={teamStorageIsLoading}
              isError={teamStorageIsError}
            />
            <TimeSeriesLineChart
              title={t("rework.teamUsage.team.conversationsOverTime.title")}
              rows={teamSessionsData?.rows ?? []}
              interval={teamSessionsData?.interval}
              valueLabel={t("rework.teamUsage.team.conversationsOverTime.valueLabel")}
              isFetching={teamSessionsIsFetching}
              isLoading={teamSessionsIsLoading}
              isError={teamSessionsIsError}
            />
            <div className={styles.cellFull}>
              <MultiSeriesLineChart
                title={t("rework.teamUsage.team.mostActiveAgents.title")}
                rows={teamTopAgentsData?.rows ?? []}
                series={teamTopAgentsData?.series ?? []}
                interval={teamTopAgentsData?.interval}
                valueLabel={t("rework.teamUsage.team.mostActiveAgents.valueLabel")}
                isFetching={teamTopAgentsIsFetching}
                isLoading={teamTopAgentsIsLoading}
                isError={teamTopAgentsIsError}
              />
            </div>
          </div>
        </Disclosure>
      )}

      <Disclosure title={t("rework.teamUsage.personalSectionTitle")} defaultOpen>
        <div className={styles.chartGrid}>
          <div className={styles.cellFull}>
            <TimeSeriesLineChart
              title={t("rework.teamUsage.tokensOverTime.title")}
              rows={overTimeData?.rows ?? []}
              interval={overTimeData?.interval}
              valueLabel={t("rework.teamUsage.tokensOverTime.valueLabel")}
              isFetching={overTimeIsFetching}
              isLoading={overTimeIsLoading}
              isError={overTimeIsError}
            />
            <TokenUsageImpact rows={overTimeData?.rows} isLoading={overTimeIsLoading} />
          </div>
          <BarChart
            title={t("rework.teamUsage.byAgent.title")}
            rows={byAgentData?.rows ?? []}
            valueLabel={t("rework.teamUsage.byAgent.valueLabel")}
            emptyMessage={t("rework.teamUsage.byAgent.empty")}
            isLoading={byAgentIsLoading}
            isError={byAgentIsError}
          />
          <BarChart
            title={t("rework.teamUsage.byModel.title")}
            rows={byModelData?.rows ?? []}
            valueLabel={t("rework.teamUsage.byModel.valueLabel")}
            emptyMessage={t("rework.teamUsage.byModel.empty")}
            isLoading={byModelIsLoading}
            isError={byModelIsError}
          />
        </div>
      </Disclosure>
    </div>
  );
}
