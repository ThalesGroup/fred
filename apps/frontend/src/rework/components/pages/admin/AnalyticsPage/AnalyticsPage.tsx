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
import { Link } from "react-router-dom";
import styles from "./AnalyticsPage.module.css";
import {
  useActiveUsersOverTimeQuery,
  useAgentPromptLengthDistributionQuery,
  useAgentsTotalQuery,
  useDocumentsTotalQuery,
  useMessagesOverTimeQuery,
  useSessionsByScopeQuery,
  useSessionsOverTimeQuery,
  useStorageByTeamQuery,
  useTokenUsageByAgentQuery,
  useTokenUsageByModelQuery,
  useTokenUsageOverTimeQuery,
  useTopAgentsByConversationsQuery,
  useTopTeamsBySessionsQuery,
  useUniqueUsersTotalQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { TIME_PRESETS } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard";
import PieChart from "@shared/molecules/PieChart/PieChart";
import BarChart from "@shared/molecules/BarChart/BarChart";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
import TaskActivity from "@shared/organisms/TaskActivity/TaskActivity.tsx";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";

const defaultPreset = TIME_PRESETS.find((p) => p.key === "last30d")!;
const defaultRange: TimeRange = { ...defaultPreset.resolve(), presetKey: "last30d" };

function sumRows(rows: { value: number }[] | undefined): number | undefined {
  if (rows === undefined) return undefined;
  return Math.round(rows.reduce((acc, r) => acc + r.value, 0));
}

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);

  // #2148: `refetchOnMountOrArgChange: 300` implements the "5 minute
  // client-side TTL, does not re-fetch on every render" policy
  // KPI-ANALYTICS-RFC.md §2.6 already documents — every preset below used
  // `true` instead, which ignored cache age and refetched on every mount.
  const { data, isLoading, isFetching, isError } = useActiveUsersOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: totalData,
    isLoading: totalIsLoading,
    isError: totalIsError,
  } = useUniqueUsersTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: sessionsData,
    isLoading: sessionsIsLoading,
    isError: sessionsIsError,
  } = useSessionsOverTimeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: messagesData,
    isLoading: messagesIsLoading,
    isFetching: messagesIsFetching,
    isError: messagesIsError,
  } = useMessagesOverTimeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: scopeData,
    isLoading: scopeIsLoading,
    isError: scopeIsError,
  } = useSessionsByScopeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  // Add translated labels
  const scopeRows = useMemo(
    () =>
      (scopeData?.rows ?? []).map((r) => ({
        ...r,
        label:
          r.label === "personal"
            ? t("rework.analytics.conversationsByScope.personal")
            : t("rework.analytics.conversationsByScope.team"),
      })),
    [scopeData, t],
  );

  const {
    data: topTeamsData,
    isLoading: topTeamsIsLoading,
    isError: topTeamsIsError,
  } = useTopTeamsBySessionsQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: agentsTotalData,
    isLoading: agentsTotalIsLoading,
    isError: agentsTotalIsError,
  } = useAgentsTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: documentsTotalData,
    isLoading: documentsTotalIsLoading,
    isError: documentsTotalIsError,
  } = useDocumentsTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: topAgentsData,
    isLoading: topAgentsIsLoading,
    isFetching: topAgentsIsFetching,
    isError: topAgentsIsError,
  } = useTopAgentsByConversationsQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: promptLengthData,
    isLoading: promptLengthIsLoading,
    isError: promptLengthIsError,
  } = useAgentPromptLengthDistributionQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  // Token usage + green/cost (§2.7, F1) — platform-wide (no teamId), same
  // presets the personal dashboard (Page 3) and the team dashboard (Page 2,
  // F2) parameterize by scope.
  const {
    data: tokenUsageOverTimeData,
    isLoading: tokenUsageOverTimeIsLoading,
    isFetching: tokenUsageOverTimeIsFetching,
    isError: tokenUsageOverTimeIsError,
  } = useTokenUsageOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: tokenUsageByAgentData,
    isLoading: tokenUsageByAgentIsLoading,
    isError: tokenUsageByAgentIsError,
  } = useTokenUsageByAgentQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: tokenUsageByModelData,
    isLoading: tokenUsageByModelIsLoading,
    isError: tokenUsageByModelIsError,
  } = useTokenUsageByModelQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  // Admin-only section (§2.4/§2.5) — can_manage_platform, not the weaker
  // can_observe_platform every query above requires. Skipped entirely for a
  // plain platform_observer, both to avoid the wasted call and because
  // useUserCapabilities() is this frontend's single source of truth for the
  // distinction (never re-derived from Keycloak roles).
  const { canAdmin } = useUserCapabilities();
  const {
    data: storageByTeamData,
    isLoading: storageByTeamIsLoading,
    isError: storageByTeamIsError,
  } = useStorageByTeamQuery(
    { since: timeRange.since, until: timeRange.until },
    { skip: !canAdmin, refetchOnMountOrArgChange: 300 },
  );
  const storageByTeamRows = useMemo(
    () =>
      (storageByTeamData?.rows ?? [])
        .filter((r) => r.quota_bytes != null && r.quota_bytes > 0)
        .map((r) => ({
          label: r.label,
          value: Math.round((r.used_bytes / r.quota_bytes!) * 100),
        })),
    [storageByTeamData],
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

  // When every metric query fails, the control plane is unreachable — show the
  // shared "service not running" notice instead of a grid of error cards.
  const serviceDown = [
    isError,
    totalIsError,
    sessionsIsError,
    messagesIsError,
    scopeIsError,
    topTeamsIsError,
    agentsTotalIsError,
    documentsTotalIsError,
    topAgentsIsError,
    promptLengthIsError,
  ].every(Boolean);

  if (serviceDown) {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <h1 className={styles.title}>{t("rework.analytics.title")}</h1>
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
        <h1 className={styles.title}>{t("rework.analytics.title")}</h1>
        <div className={styles.headerControls}>
          <TimeRangeSelector value={timeRange} onChange={handleRangeChange} />
          <IconButton
            color="primary"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh" }}
            onClick={handleRefresh}
            disabled={isFetching}
            title={t("common.refresh")}
          />
        </div>
      </div>

      {/* Grouped into collapsible sections (closes #1777's density critique)
          rather than one flat scroll. */}
      <Disclosure title={t("rework.analytics.sections.overview")} defaultOpen>
        {/* At-a-glance key figures — compact number tiles. */}
        <div className={styles.kpiRow}>
          <KpiStatCard
            label={t("rework.analytics.activeUsers.uniqueTotal")}
            value={totalData?.value}
            isLoading={totalIsLoading}
            isError={totalIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.conversations.total")}
            value={sumRows(sessionsData?.rows)}
            isLoading={sessionsIsLoading}
            isError={sessionsIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.messages.total")}
            value={sumRows(messagesData?.rows)}
            isLoading={messagesIsLoading}
            isError={messagesIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.agents.total")}
            value={agentsTotalData?.value}
            delta={agentsTotalData?.delta}
            unavailable={agentsTotalData?.unavailable}
            isLoading={agentsTotalIsLoading}
            isError={agentsTotalIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.documents.total")}
            value={documentsTotalData?.value}
            delta={documentsTotalData?.delta}
            unavailable={documentsTotalData?.unavailable}
            isLoading={documentsTotalIsLoading}
            isError={documentsTotalIsError}
          />
        </div>

        {/* Bento grid: trends + pie share the top row; the busy multi-series gets
            a wide cell; the prompt-length distribution spans the full width. */}
        <div className={styles.chartGrid}>
          <TimeSeriesLineChart
            title={t("rework.analytics.activeUsers.title")}
            rows={data?.rows ?? []}
            interval={data?.interval}
            valueLabel={t("rework.analytics.activeUsers.valueLabel")}
            isFetching={isFetching}
            isLoading={isLoading}
            isError={isError}
          />
          <TimeSeriesLineChart
            title={t("rework.analytics.messages.title")}
            rows={messagesData?.rows ?? []}
            interval={messagesData?.interval}
            valueLabel={t("rework.analytics.messages.valueLabel")}
            isFetching={messagesIsFetching}
            isLoading={messagesIsLoading}
            isError={messagesIsError}
          />
          <PieChart
            title={t("rework.analytics.conversationsByScope.title")}
            rows={scopeRows}
            emptyMessage={t("rework.analytics.conversationsByScope.empty")}
            isLoading={scopeIsLoading}
            isError={scopeIsError}
          />
          <BarChart
            title={t("rework.analytics.topTeams.title")}
            rows={topTeamsData?.rows ?? []}
            valueLabel={t("rework.analytics.topTeams.valueLabel")}
            emptyMessage={t("rework.analytics.topTeams.empty")}
            isLoading={topTeamsIsLoading}
            isError={topTeamsIsError}
          />
          <div className={styles.cellWide}>
            <MultiSeriesLineChart
              title={t("rework.analytics.agents.topByConversations.title")}
              rows={topAgentsData?.rows ?? []}
              series={topAgentsData?.series ?? []}
              interval={topAgentsData?.interval}
              valueLabel={t("rework.analytics.agents.topByConversations.valueLabel")}
              isFetching={topAgentsIsFetching}
              isLoading={topAgentsIsLoading}
              isError={topAgentsIsError}
            />
          </div>
          <div className={styles.cellFull}>
            <BarChart
              title={t("rework.analytics.agents.promptLengthDistribution.title")}
              rows={promptLengthData?.rows ?? []}
              valueLabel={t("rework.analytics.agents.promptLengthDistribution.valueLabel")}
              emptyMessage={t("rework.analytics.agents.promptLengthDistribution.empty")}
              isLoading={promptLengthIsLoading}
              isError={promptLengthIsError}
              sortOrder="none"
              orientation="vertical"
            />
          </div>
        </div>
      </Disclosure>

      {/* New (v3, §2.7): platform-wide token usage + green/cost, inline with
          the same charts — not a separate panel. */}
      <Disclosure title={t("rework.analytics.sections.tokenUsage")} defaultOpen>
        <div className={styles.chartGrid}>
          <div className={styles.cellWide}>
            <TimeSeriesLineChart
              title={t("rework.analytics.tokenUsage.overTime.title")}
              rows={tokenUsageOverTimeData?.rows ?? []}
              interval={tokenUsageOverTimeData?.interval}
              valueLabel={t("rework.analytics.tokenUsage.overTime.valueLabel")}
              isFetching={tokenUsageOverTimeIsFetching}
              isLoading={tokenUsageOverTimeIsLoading}
              isError={tokenUsageOverTimeIsError}
            />
            <TokenUsageImpact rows={tokenUsageOverTimeData?.rows} isLoading={tokenUsageOverTimeIsLoading} />
          </div>
          <BarChart
            title={t("rework.analytics.tokenUsage.byAgent.title")}
            rows={tokenUsageByAgentData?.rows ?? []}
            valueLabel={t("rework.analytics.tokenUsage.byAgent.valueLabel")}
            emptyMessage={t("rework.analytics.tokenUsage.byAgent.empty")}
            isLoading={tokenUsageByAgentIsLoading}
            isError={tokenUsageByAgentIsError}
          />
          <BarChart
            title={t("rework.analytics.tokenUsage.byModel.title")}
            rows={tokenUsageByModelData?.rows ?? []}
            valueLabel={t("rework.analytics.tokenUsage.byModel.valueLabel")}
            emptyMessage={t("rework.analytics.tokenUsage.byModel.empty")}
            isLoading={tokenUsageByModelIsLoading}
            isError={tokenUsageByModelIsError}
          />
        </div>
      </Disclosure>

      {/* Admin-only (§2.4/§2.5) — can_manage_platform, checked server-side by
          storage_by_team itself; hidden here too so a plain observer never
          sees an empty section they can't use. */}
      {canAdmin && (
        <Disclosure title={t("rework.analytics.sections.administration")} defaultOpen>
          <div className={styles.sectionStack}>
            <BarChart
              title={t("rework.analytics.administration.storageByTeam.title")}
              rows={storageByTeamRows}
              valueLabel={t("rework.analytics.administration.storageByTeam.valueLabel")}
              emptyMessage={t("rework.analytics.administration.storageByTeam.empty")}
              isLoading={storageByTeamIsLoading}
              isError={storageByTeamIsError}
            />
            <section>
              <h2 className={styles.subheading}>{t("rework.analytics.administration.activitiesTitle")}</h2>
              <TaskActivity scope="platform" />
            </section>
            <Link to="/admin/capabilities?kind=model" className={styles.governanceLink}>
              {t("rework.analytics.administration.modelsGovernanceLink")}
            </Link>
          </div>
        </Disclosure>
      )}
    </div>
  );
}
