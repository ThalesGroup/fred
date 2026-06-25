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
import styles from "./AnalyticsPage.module.css";
import {
  useActiveUsersOverTimeQuery,
  useAgentPromptLengthDistributionQuery,
  useAgentsTotalQuery,
  useDocumentsTotalQuery,
  useMessagesOverTimeQuery,
  useSessionsByScopeQuery,
  useSessionsOverTimeQuery,
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

const defaultPreset = TIME_PRESETS.find((p) => p.key === "last30d")!;
const defaultRange: TimeRange = { ...defaultPreset.resolve(), presetKey: "last30d" };

function sumRows(rows: { value: number }[] | undefined): number | undefined {
  if (rows === undefined) return undefined;
  return Math.round(rows.reduce((acc, r) => acc + r.value, 0));
}

export default function AnalyticsPage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);

  const { data, isLoading, isFetching, isError } = useActiveUsersOverTimeQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  const {
    data: totalData,
    isLoading: totalIsLoading,
    isError: totalIsError,
  } = useUniqueUsersTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

  const {
    data: sessionsData,
    isLoading: sessionsIsLoading,
    isError: sessionsIsError,
  } = useSessionsOverTimeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

  const {
    data: messagesData,
    isLoading: messagesIsLoading,
    isFetching: messagesIsFetching,
    isError: messagesIsError,
  } = useMessagesOverTimeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

  const {
    data: scopeData,
    isLoading: scopeIsLoading,
    isError: scopeIsError,
  } = useSessionsByScopeQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

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
    { refetchOnMountOrArgChange: true },
  );

  const {
    data: agentsTotalData,
    isLoading: agentsTotalIsLoading,
    isError: agentsTotalIsError,
  } = useAgentsTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

  const {
    data: documentsTotalData,
    isLoading: documentsTotalIsLoading,
    isError: documentsTotalIsError,
  } = useDocumentsTotalQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: true });

  const {
    data: topAgentsData,
    isLoading: topAgentsIsLoading,
    isFetching: topAgentsIsFetching,
    isError: topAgentsIsError,
  } = useTopAgentsByConversationsQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
  );

  const {
    data: promptLengthData,
    isLoading: promptLengthIsLoading,
    isError: promptLengthIsError,
  } = useAgentPromptLengthDistributionQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: true },
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
    </div>
  );
}
