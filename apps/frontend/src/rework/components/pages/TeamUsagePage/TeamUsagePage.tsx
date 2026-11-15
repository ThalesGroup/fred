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
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import { refreshTimeRange, resolvePreset, type TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Button from "@shared/atoms/Button/Button";
import { teamAnalyticsWorkbook } from "./exportTeamAnalytics";
import { downloadFile } from "../../../../utils/downloadUtils";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import PersonalUsage from "./PersonalUsage";
import ConsumptionUsage from "./ConsumptionUsage";
import TeamAnalytics from "./TeamAnalytics";
import { personalQueries } from "./personalUsage";
import { analyticsErrorKey, collectiveConsumptionQueries, collectiveHistoryQueries } from "./teamAnalytics";
import {
  useQueryAnalyticsQuery,
  useLazyQueryAnalyticsQuery,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import styles from "./TeamUsagePage.module.css";

/** All collective reads use Weaver authority; aggregate access never opens conversation content. */
export default function TeamUsagePage() {
  const working = useWorkingOrganization();
  const organizationId = working.loading || working.error ? undefined : working.organizationId;
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(() => resolvePreset("last30d"));
  const [tab, setTab] = useState(0);
  const { teamId } = useParams<{ teamId: string }>();
  const space = working.memberships.isError
    ? undefined
    : working.memberships.currentData?.find((item) => item.id === teamId && item.organization_id === organizationId);
  const isPersonalTeam = space?.kind === "personal";
  const canReadConsumption = canReadSpaceUsage(space, organizationId);
  const collectiveSpaceId = canReadConsumption ? space.id : undefined;
  const identity = KeyCloakService.GetSessionIdentity();
  const args = useMemo(
    () =>
      ({
        usage: organizationId
          ? sessionQueryArgs({ analyticsRequest: { queries: personalQueries(timeRange, organizationId, false) } })
          : skipToken,
        collective: collectiveSpaceId
          ? sessionQueryArgs({
              analyticsRequest: { queries: collectiveConsumptionQueries(timeRange, collectiveSpaceId) },
            })
          : skipToken,
        history: collectiveSpaceId
          ? sessionQueryArgs({ analyticsRequest: { queries: collectiveHistoryQueries(timeRange, collectiveSpaceId) } })
          : skipToken,
        skills: organizationId
          ? sessionQueryArgs({ analyticsRequest: { queries: personalQueries(timeRange, organizationId, true) } })
          : skipToken,
      }) as const,
    [timeRange, identity, organizationId, collectiveSpaceId],
  );
  const usage = useQueryAnalyticsQuery(args.usage, { refetchOnMountOrArgChange: 300 });
  const personalSkills = useQueryAnalyticsQuery(args.skills, { skip: !isPersonalTeam, refetchOnMountOrArgChange: 300 });
  const collectiveUsage = useQueryAnalyticsQuery(args.collective, { refetchOnMountOrArgChange: true });
  const history = useQueryAnalyticsQuery(args.history, { skip: tab === 0, refetchOnMountOrArgChange: true });
  const [exportQuery] = useLazyQueryAnalyticsQuery();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string>();
  const exportContext = `${identity}/${organizationId}/${collectiveSpaceId}/${timeRange.since}/${timeRange.until}/${tab}`;
  const currentContext = useRef(exportContext);
  useEffect(() => {
    currentContext.current = exportContext;
    setExportError(undefined);
    return () => {
      currentContext.current = "";
    };
  }, [exportContext]);
  const handleExport = async () => {
    if (args.collective === skipToken || args.history === skipToken) return;
    const context = exportContext;
    const stillCurrent = () => currentContext.current === context && KeyCloakService.GetSessionIdentity() === identity;
    if (!stillCurrent()) return;
    setExporting(true);
    setExportError(undefined);
    try {
      // Refresh authorization and data at the same fixed period; never export an old cache on denial.
      const sql = await exportQuery(args.collective, false).unwrap();
      if (!stillCurrent()) return;
      const datasets = [sql];
      if (tab !== 0) datasets.push(await exportQuery(args.history, false).unwrap());
      if (!stillCurrent()) return;
      const keys =
        tab === 0
          ? ["total", "series", "agents", "models", "impact", "previous_total", "previous_impact"]
          : tab === 1
            ? ["conversations", "turns", "previous_turns", "turn_series"]
            : ["turns", "previous_turns", "turn_agents", "skills"];
      const selected = datasets.map((data) => ({
        ...data,
        results: Object.fromEntries(Object.entries(data.results).filter(([key]) => keys.includes(key))),
      }));
      const blob = await teamAnalyticsWorkbook(collectiveSpaceId!, selected, t);
      if (stillCurrent()) downloadFile(blob, `analytics-${collectiveSpaceId}.xlsx`);
    } catch (error) {
      if (currentContext.current === context) setExportError(analyticsErrorKey(error));
    } finally {
      setExporting(false);
    }
  };
  const handleRefresh = () => {
    if (!organizationId) return;
    const next = refreshTimeRange(timeRange);
    if (next.since !== timeRange.since || next.until !== timeRange.until) {
      setTimeRange(next);
      return;
    }
    void usage.refetch();
    if (canReadConsumption) {
      void collectiveUsage.refetch();
      if (tab !== 0) void history.refetch();
    }
    if (isPersonalTeam) void personalSkills.refetch();
  };
  const tabs = ["consumption", "usage", "agents"];
  return (
    <div className={styles.page}>
      <PageHeader
        title={t(
          canReadConsumption
            ? space.kind === "project"
              ? "rework.teamUsage.projectPageTitle"
              : "rework.teamUsage.team.pageTitle"
            : "rework.teamUsage.title",
        )}
        sticky
        actions={
          <>
            <TimeRangeSelector
              value={timeRange}
              onChange={setTimeRange}
              presetKeys={
                canReadConsumption
                  ? ["last7d", "last30d", "last3Months", "last12Months", "today", "thisWeek", "thisMonth"]
                  : undefined
              }
            />
            {canReadConsumption && (
              <Button
                variant="filled"
                color="primary"
                size="small"
                icon={{ category: "outlined", type: "download" }}
                disabled={exporting || collectiveUsage.isFetching || (tab !== 0 && history.isFetching)}
                aria-busy={exporting}
                onClick={handleExport}
              >
                {t("rework.teamAnalytics.export")}
              </Button>
            )}
            <IconButton
              color="primary"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "refresh" }}
              onClick={handleRefresh}
              disabled={
                !organizationId ||
                usage.isFetching ||
                (canReadConsumption && (collectiveUsage.isFetching || (tab !== 0 && history.isFetching))) ||
                (isPersonalTeam && personalSkills.isFetching)
              }
              title={t("common.refresh")}
              aria-label={t("common.refresh")}
            />
          </>
        }
        tabs={
          canReadConsumption ? (
            <ButtonGroup
              variant="tabs"
              size="small"
              color="on-surface"
              aria-label={t("rework.teamAnalytics.tabs")}
              items={tabs.map((key) => ({ label: t(`rework.teamAnalytics.${key}`) }))}
              selectedIndex={tab}
              onSelectedIndexChange={setTab}
            />
          ) : undefined
        }
      />
      {exportError && <p role="alert">{t(exportError)}</p>}
      {canReadConsumption ? (
        <>
          <p>{t(space.kind === "team" ? "rework.teamAnalytics.teamScope" : "rework.teamAnalytics.projectScope")}</p>
          <p>{t("rework.teamAnalytics.period", { since: timeRange.since, until: timeRange.until })}</p>
          {collectiveUsage.isError && <p role="alert">{t(analyticsErrorKey(collectiveUsage.error))}</p>}
          <div role="tabpanel" aria-label={t(`rework.teamAnalytics.${tabs[tab]}`)}>
            {tab === 0 ? (
              <ConsumptionUsage
                title={t(space.kind === "project" ? "rework.consumption.projectTitle" : "rework.consumption.teamTitle")}
                usage={collectiveUsage}
                detailed
              />
            ) : (
              <TeamAnalytics history={history} consumption={collectiveUsage} agents={tab === 2} />
            )}
          </div>
        </>
      ) : (
        !isPersonalTeam && (
          <p role="status">
            {t(
              working.loading
                ? "common.loading"
                : working.error || working.memberships.isError
                  ? "rework.teamAnalytics.unavailable"
                  : "rework.teamAnalytics.denied",
            )}
          </p>
        )
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
