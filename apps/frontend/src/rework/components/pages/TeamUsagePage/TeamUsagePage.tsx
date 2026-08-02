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
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
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

  const { teamId, selectedTeam, isPersonalTeam } = useSelectedTeam();
  const capabilities = useTeamCapabilities(selectedTeam);
  // The personal team is granted `can_update_resources`/`can_update_agents`
  // unconditionally (`teams/system.py::build_personal_team`) so its owner can
  // manage their own docs/agents — that's a real permission, not an elevated
  // *team* role. Without excluding it here, every user would see the
  // collaborative-team sections below while sitting in personal space, since
  // those flags would read exactly as they do for a real team_editor/admin.
  const elevated = hasElevatedTeamRole(capabilities) && !isPersonalTeam;
  // This page is majority team-scoped content for an elevated viewer (KPIs,
  // charts, storage quota below) with only a "My usage" subsection at the
  // bottom — calling it "My token usage" for that viewer was misleading (a
  // team_admin reported it read as a personal-usage page while looking at
  // team-wide data). Plain members/personal-team viewers only ever see the
  // personal section, so the original title stays correct for them.
  const pageTitle = elevated ? t("rework.teamUsage.team.pageTitle") : t("rework.teamUsage.title");

  // #2148: `refetchOnMountOrArgChange: 300` implements the "5 minute
  // client-side TTL, does not re-fetch on every render" policy
  // KPI-ANALYTICS-RFC.md §2.6 already documents — every preset below used
  // `true` instead, which ignored cache age and refetched on every mount.
  const {
    data: overTimeData,
    isLoading: overTimeIsLoading,
    isFetching: overTimeIsFetching,
    isError: overTimeIsError,
  } = useUserTokenUsageOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: byAgentData,
    isLoading: byAgentIsLoading,
    isError: byAgentIsError,
  } = useUserTokenUsageByAgentQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: byModelData,
    isLoading: byModelIsLoading,
    isError: byModelIsError,
  } = useUserTokenUsageByModelQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  // Team-scoped shared section (§2.5 Page 2) — skipped entirely for anyone
  // without an elevated role, both to avoid the wasted/rejected call and
  // because `hasElevatedTeamRole` is this frontend's single source of truth
  // for the distinction.
  const teamArgs = { since: timeRange.since, until: timeRange.until, teamId };
  const teamQueryOpts = { skip: !elevated || !teamId, refetchOnMountOrArgChange: 300 };

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
        <PageHeader title={pageTitle} />
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
      <PageHeader
        title={pageTitle}
        actions={
          <>
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
          </>
        }
      />

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
