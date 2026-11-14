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

import { canReadSpaceUsage } from "@core/utils/spaceUsage";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import { skipToken } from "@reduxjs/toolkit/query";
import { useParams } from "react-router-dom";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./TeamUsagePage.module.css";
import {
  useAgentsTotalQuery,
  useSkillUsageQuery,
  useDocumentsTotalQuery,
  useSessionsOverTimeQuery,
  useStorageByTeamQuery,
  useTopAgentsByConversationsQuery,
} from "../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { refreshTimeRange, resolvePreset } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import MultiSeriesLineChart from "@shared/molecules/MultiSeriesLineChart/MultiSeriesLineChart";
import BarChart from "@shared/molecules/BarChart/BarChart";
import KpiStatCard from "@shared/molecules/KpiStatCard/LocalizedKpiStatCard";
import PersonalUsage from "./PersonalUsage";
import ConsumptionUsage from "./ConsumptionUsage";
import { consumptionQueries, personalQueries } from "./personalUsage";
import { useQueryAnalyticsQuery } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Disclosure from "@shared/atoms/Disclosure/Disclosure.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { hasElevatedTeamRole } from "@hooks/teamCapabilities.ts";

/** Weaver consumption and personal usage; other collective indicators retain their legacy gates. */
export default function TeamUsagePage() {
  const workingOrganization = useWorkingOrganization();
  const organizationId =
    workingOrganization.loading || workingOrganization.error ? undefined : workingOrganization.organizationId;
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(() => resolvePreset("last30d"));

  const { teamId } = useParams<{ teamId: string }>();
  const space = workingOrganization.memberships.isError
    ? undefined
    : workingOrganization.memberships.currentData?.find(
        (item) => item.id === teamId && item.organization_id === organizationId,
      );
  const isPersonalTeam = space?.kind === "personal";
  // Personal UUIDs and their placement come from Weaver, never Swift's ID convention/bootstrap.
  const { selectedTeam } = useSelectedTeam(!space || isPersonalTeam);
  const capabilities = useTeamCapabilities(selectedTeam);
  const collective = space?.kind === "team" || space?.kind === "project";
  const canReadConsumption = canReadSpaceUsage(space, organizationId);
  const collectiveSpaceId = canReadConsumption ? space.id : undefined;
  // Legacy sections keep their own permissions; Weaver ReadUsage never opens them.
  const elevated = collective && selectedTeam?.id === teamId && hasElevatedTeamRole(capabilities);
  const pageTitle =
    elevated || canReadConsumption
      ? t(space.kind === "project" ? "rework.teamUsage.projectPageTitle" : "rework.teamUsage.team.pageTitle")
      : t("rework.teamUsage.title");

  const identity = KeyCloakService.GetSessionIdentity();
  const args = useMemo(
    () =>
      ({
        usage: organizationId
          ? sessionQueryArgs({ analyticsRequest: { queries: personalQueries(timeRange, organizationId, false) } })
          : skipToken,
        collective: collectiveSpaceId
          ? sessionQueryArgs({
              analyticsRequest: { queries: consumptionQueries(timeRange, { kind: "space", id: collectiveSpaceId }) },
            })
          : skipToken,
        skills: organizationId
          ? sessionQueryArgs({ analyticsRequest: { queries: personalQueries(timeRange, organizationId, true) } })
          : skipToken,
        // Identity changes must bind fresh arguments even for an unchanged period.
      }) as const,
    [timeRange, identity, organizationId, collectiveSpaceId],
  );
  const usage = useQueryAnalyticsQuery(args.usage, { refetchOnMountOrArgChange: 300 });
  const personalSkills = useQueryAnalyticsQuery(args.skills, { skip: !isPersonalTeam, refetchOnMountOrArgChange: 300 });

  const collectiveUsage = useQueryAnalyticsQuery(args.collective, { refetchOnMountOrArgChange: true });
  const teamArgs = { since: timeRange.since, until: timeRange.until, teamId };
  const teamQueryOpts = { skip: !elevated || !teamId, refetchOnMountOrArgChange: 300 };

  const {
    currentData: skillUsageData,
    isFetching: skillUsageIsFetching,
    isLoading: skillUsageIsLoading,
    isError: skillUsageIsError,
  } = useSkillUsageQuery(teamArgs, teamQueryOpts);

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
    if (!organizationId) return;
    const next = refreshTimeRange(timeRange);
    if (next.since === timeRange.since && next.until === timeRange.until) {
      void usage.refetch();
      if (canReadConsumption) void collectiveUsage.refetch();
      if (isPersonalTeam) void personalSkills.refetch();
    } else setTimeRange(next);
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title={pageTitle}
        sticky
        actions={
          <>
            <TimeRangeSelector value={timeRange} onChange={handleRangeChange} />
            <IconButton
              color="primary"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "refresh" }}
              onClick={handleRefresh}
              disabled={
                !organizationId ||
                usage.isFetching ||
                (canReadConsumption && collectiveUsage.isFetching) ||
                (isPersonalTeam && personalSkills.isFetching)
              }
              title={t("common.refresh")}
              aria-label={t("common.refresh")}
            />
          </>
        }
      />

      {canReadConsumption && (
        <ConsumptionUsage
          title={t(space.kind === "project" ? "rework.consumption.projectTitle" : "rework.consumption.teamTitle")}
          usage={collectiveUsage}
        />
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

      {elevated && teamId && (
        <Disclosure title={t("rework.teamUsage.team.skillsSectionTitle")} defaultOpen>
          <SkillUsageTable
            data={skillUsageData}
            isLoading={skillUsageIsLoading || (skillUsageIsFetching && !skillUsageData)}
            isError={skillUsageIsError}
          />
        </Disclosure>
      )}

      <PersonalUsage
        organizationId={organizationId}
        usage={usage}
        skills={personalSkills}
        withSkills={isPersonalTeam}
      />
    </div>
  );
}
