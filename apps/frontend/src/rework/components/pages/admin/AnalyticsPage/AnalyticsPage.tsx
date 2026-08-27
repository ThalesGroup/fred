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
  useAgentsPerUserQuery,
  useAgentsPerUserTrendQuery,
  useAgentsTotalQuery,
  useConversationDepthQuery,
  useConversationDepthTrendQuery,
  useConversationsPerUserQuery,
  useConversationsPerUserTrendQuery,
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
import HistogramChart from "@shared/molecules/HistogramChart/HistogramChart";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import IconButton from "@shared/atoms/IconButton/IconButton";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import TokenUsageImpact from "@shared/molecules/TokenUsageImpact/TokenUsageImpact.tsx";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { formatTrendWindow } from "./trendWindow";

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

  // Engagement distributions (#2426) — how many conversations a user starts,
  // how deep a conversation goes, and how many distinct agents a user reaches
  // for. All three return histogram rows plus a median.
  const {
    data: conversationsPerUserData,
    isLoading: conversationsPerUserIsLoading,
    isError: conversationsPerUserIsError,
  } = useConversationsPerUserQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: conversationDepthData,
    isLoading: conversationDepthIsLoading,
    isError: conversationDepthIsError,
  } = useConversationDepthQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  const {
    data: agentsPerUserData,
    isLoading: agentsPerUserIsLoading,
    isError: agentsPerUserIsError,
  } = useAgentsPerUserQuery({ since: timeRange.since, until: timeRange.until }, { refetchOnMountOrArgChange: 300 });

  // Engagement trends (#2428) — the same three medians recomputed per bucket
  // over a trailing window, so the section shows how usage is moving and not
  // only where it stands over the whole range.
  const {
    data: conversationsPerUserTrendData,
    isLoading: conversationsPerUserTrendIsLoading,
    isFetching: conversationsPerUserTrendIsFetching,
    isError: conversationsPerUserTrendIsError,
  } = useConversationsPerUserTrendQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: conversationDepthTrendData,
    isLoading: conversationDepthTrendIsLoading,
    isFetching: conversationDepthTrendIsFetching,
    isError: conversationDepthTrendIsError,
  } = useConversationDepthTrendQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  const {
    data: agentsPerUserTrendData,
    isLoading: agentsPerUserTrendIsLoading,
    isFetching: agentsPerUserTrendIsFetching,
    isError: agentsPerUserTrendIsError,
  } = useAgentsPerUserTrendQuery(
    { since: timeRange.since, until: timeRange.until },
    { refetchOnMountOrArgChange: 300 },
  );

  // The window is the backend's to decide (it follows the bucket interval), so
  // it can only be named once the response is in — until then the tooltip goes
  // without a label rather than announcing a window nobody resolved yet.
  const trendValueLabel = (key: string, window: string | null | undefined) => {
    const formatted = formatTrendWindow(window, t);
    return formatted ? t(key, { window: formatted }) : undefined;
  };

  // The window belongs in the title too, not only in the tooltip: without it an
  // admin who never hovers cannot tell this median line from the range-wide
  // median tile above. Falls back to the bare title until the response names
  // the window.
  const trendTitle = (key: string, window: string | null | undefined) => {
    const formatted = formatTrendWindow(window, t);
    const title = t(key);
    return formatted ? t("rework.analytics.engagement.trendTitleWithWindow", { title, window: formatted }) : title;
  };

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
    conversationsPerUserIsError,
    conversationDepthIsError,
    agentsPerUserIsError,
    conversationsPerUserTrendIsError,
    conversationDepthTrendIsError,
    agentsPerUserTrendIsError,
  ].every(Boolean);

  if (serviceDown) {
    return (
      <div className={styles.page}>
        <PageHeader title={t("rework.analytics.title")} />
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
        title={t("rework.analytics.title")}
        actions={
          <>
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
          </>
        }
      />

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
            <HistogramChart
              title={t("rework.analytics.agents.promptLengthDistribution.title")}
              rows={promptLengthData?.rows ?? []}
              valueLabel={t("rework.analytics.agents.promptLengthDistribution.valueLabel")}
              emptyMessage={t("rework.analytics.agents.promptLengthDistribution.empty")}
              isLoading={promptLengthIsLoading}
              isError={promptLengthIsError}
            />
          </div>
        </div>
      </Disclosure>

      {/* Engagement (#2426): the shape-of-usage questions the totals above
          can't answer — is usage spread across users or concentrated in a few,
          do conversations go anywhere past the first message, and how many
          distinct agents a user actually reaches for. The trend row below the
          histograms (#2428) adds the direction each of those three is moving:
          the same median, recomputed over a trailing window per bucket. */}
      <Disclosure title={t("rework.analytics.sections.engagement")} defaultOpen>
        {/* Every figure in this section covers only users active in the range
            (≥1 conversation started) — there is deliberately no "0" bar, and
            the note below says so rather than leaving readers to infer it. */}
        <p className={styles.sectionDescription}>{t("rework.analytics.engagement.description")}</p>
        {/* `median` is null when the range holds nothing to take a median of.
            Flagging that as `unavailable` makes the card say "no data" — left
            unset it would render as a label with nothing under it. The value is
            a median of integers, so it is always whole or .5: KpiStatCard's
            toLocaleString formats it fine, no call-site rounding needed. */}
        <div className={styles.kpiRow}>
          <KpiStatCard
            label={t("rework.analytics.engagement.conversationsPerUser.medianLabel")}
            value={conversationsPerUserData?.median}
            unavailable={conversationsPerUserData != null && conversationsPerUserData.median == null}
            isLoading={conversationsPerUserIsLoading}
            isError={conversationsPerUserIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.engagement.conversationDepth.medianLabel")}
            value={conversationDepthData?.median}
            unavailable={conversationDepthData != null && conversationDepthData.median == null}
            isLoading={conversationDepthIsLoading}
            isError={conversationDepthIsError}
          />
          <KpiStatCard
            label={t("rework.analytics.engagement.agentsPerUser.medianLabel")}
            value={agentsPerUserData?.median}
            unavailable={agentsPerUserData != null && agentsPerUserData.median == null}
            isLoading={agentsPerUserIsLoading}
            isError={agentsPerUserIsError}
          />
        </div>

        {/* Three histograms, one per bento column. */}
        <div className={styles.chartGrid}>
          <HistogramChart
            title={t("rework.analytics.engagement.conversationsPerUser.title")}
            rows={conversationsPerUserData?.rows ?? []}
            valueLabel={t("rework.analytics.engagement.conversationsPerUser.valueLabel")}
            emptyMessage={t("rework.analytics.engagement.conversationsPerUser.empty")}
            isLoading={conversationsPerUserIsLoading}
            isError={conversationsPerUserIsError}
          />
          <HistogramChart
            title={t("rework.analytics.engagement.conversationDepth.title")}
            rows={conversationDepthData?.rows ?? []}
            valueLabel={t("rework.analytics.engagement.conversationDepth.valueLabel")}
            emptyMessage={t("rework.analytics.engagement.conversationDepth.empty")}
            isLoading={conversationDepthIsLoading}
            isError={conversationDepthIsError}
          />
          <HistogramChart
            title={t("rework.analytics.engagement.agentsPerUser.title")}
            rows={agentsPerUserData?.rows ?? []}
            valueLabel={t("rework.analytics.engagement.agentsPerUser.valueLabel")}
            emptyMessage={t("rework.analytics.engagement.agentsPerUser.empty")}
            isLoading={agentsPerUserIsLoading}
            isError={agentsPerUserIsError}
          />
        </div>

        {/* Same three metrics, same column order as the histograms above, so a
            reader tracks one column down instead of hunting for the pair.

            Each carries its own `emptyMessage`: a trend can be empty while the
            histogram beside it is not. The series drops the current, partial
            bucket, so a range whose only activity is today has no bucket left
            to plot even though the histogram counts it. Left to the generic
            "no data" that pairing reads as a bug in the chart. */}
        <div className={styles.chartGrid}>
          <TimeSeriesLineChart
            title={trendTitle(
              "rework.analytics.engagement.conversationsPerUserTrend.title",
              conversationsPerUserTrendData?.window,
            )}
            rows={conversationsPerUserTrendData?.rows ?? []}
            interval={conversationsPerUserTrendData?.interval}
            valueLabel={trendValueLabel(
              "rework.analytics.engagement.conversationsPerUserTrend.valueLabel",
              conversationsPerUserTrendData?.window,
            )}
            emptyMessage={t("rework.analytics.engagement.conversationsPerUserTrend.empty")}
            isFetching={conversationsPerUserTrendIsFetching}
            isLoading={conversationsPerUserTrendIsLoading}
            isError={conversationsPerUserTrendIsError}
          />
          <TimeSeriesLineChart
            title={trendTitle(
              "rework.analytics.engagement.conversationDepthTrend.title",
              conversationDepthTrendData?.window,
            )}
            rows={conversationDepthTrendData?.rows ?? []}
            interval={conversationDepthTrendData?.interval}
            valueLabel={trendValueLabel(
              "rework.analytics.engagement.conversationDepthTrend.valueLabel",
              conversationDepthTrendData?.window,
            )}
            emptyMessage={t("rework.analytics.engagement.conversationDepthTrend.empty")}
            isFetching={conversationDepthTrendIsFetching}
            isLoading={conversationDepthTrendIsLoading}
            isError={conversationDepthTrendIsError}
          />
          <TimeSeriesLineChart
            title={trendTitle("rework.analytics.engagement.agentsPerUserTrend.title", agentsPerUserTrendData?.window)}
            rows={agentsPerUserTrendData?.rows ?? []}
            interval={agentsPerUserTrendData?.interval}
            valueLabel={trendValueLabel(
              "rework.analytics.engagement.agentsPerUserTrend.valueLabel",
              agentsPerUserTrendData?.window,
            )}
            emptyMessage={t("rework.analytics.engagement.agentsPerUserTrend.empty")}
            isFetching={agentsPerUserTrendIsFetching}
            isLoading={agentsPerUserTrendIsLoading}
            isError={agentsPerUserTrendIsError}
          />
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
            <Link to="/admin/capabilities?kind=model" className={styles.governanceLink}>
              {t("rework.analytics.administration.modelsGovernanceLink")}
            </Link>
          </div>
        </Disclosure>
      )}
    </div>
  );
}
