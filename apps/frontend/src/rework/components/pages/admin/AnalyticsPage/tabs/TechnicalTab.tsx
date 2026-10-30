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
  useAgentPromptLengthDistributionQuery,
  useCreationAssistantUsageQuery,
  useStorageByTeamQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { TeamStorageRow } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import { formatBytes } from "@shared/utils/formatBytes";
import HistogramChart from "@shared/molecules/HistogramChart/HistogramChart";
import { AnalyticsSection, AnalyticsServiceDown } from "../AnalyticsSection";
import AnalyticsTable from "../AnalyticsTable";
import InfoTile from "../InfoTile";
import { BarCell } from "../RankedBars";
import { formatValue, NO_VALUE } from "../analyticsFormat";
import WebResearchSection from "../WebResearchSection";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, kpiArgs, platformOnly } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

/** Platform operations: web research, storage quotas, how agents are built, model governance. */
export default function TechnicalTab({ timeRange, teamIds, userFilter }: AnalyticsTabProps) {
  const { t, i18n } = useTranslation();
  const args = kpiArgs(timeRange, teamIds);
  const storage = useStorageByTeamQuery(args, KPI_CACHE);
  const promptLength = useAgentPromptLengthDistributionQuery(args, platformOnly(teamIds));
  const creationAssistant = useCreationAssistantUsageQuery(
    kpiArgs(timeRange, teamIds, userFilter),
    platformOnly(teamIds),
  );
  const teamScoped = teamIds.length > 0;

  // From this share of its quota a team should be warned before imports get blocked.
  const NEAR_QUOTA = 0.8;
  const usedShare = (r: TeamStorageRow) => (r.quota_bytes ? r.used_bytes / r.quota_bytes : null);
  const storageRows = useMemo(
    () => [...(storage.data?.rows ?? [])].sort((a, b) => (usedShare(b) ?? -1) - (usedShare(a) ?? -1)),
    [storage.data],
  );
  const storageKey = "rework.analytics.tables.storage";
  const bytes = (value: number) => <span className={styles.numeric}>{formatBytes(value, i18n.language)}</span>;
  const storageColumns: DataTableColumn<TeamStorageRow>[] = [
    {
      label: t(`${storageKey}.team`),
      size: "2fr",
      sortable: true,
      sortValue: (r) => r.label,
      cellRenderer: (r) => r.label,
    },
    {
      label: t(`${storageKey}.used`),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.used_bytes,
      cellRenderer: (r) => bytes(r.used_bytes),
    },
    {
      label: t(`${storageKey}.quota`),
      size: "1fr",
      sortable: true,
      sortValue: (r) => r.quota_bytes ?? -1,
      cellRenderer: (r) => (r.quota_bytes ? bytes(r.quota_bytes) : <span className={styles.numeric}>{NO_VALUE}</span>),
    },
    {
      label: t(`${storageKey}.share`),
      size: "2fr",
      sortable: true,
      sortValue: (r) => usedShare(r) ?? -1,
      cellRenderer: (r) => {
        const share = usedShare(r);
        const near = share != null && share >= NEAR_QUOTA;
        return <BarCell share={share} theme={near ? "warning" : "tertiary"} emphasize={near} />;
      },
    },
  ];

  const promptAgents = (promptLength.data?.rows ?? []).reduce((sum, r) => sum + r.value, 0);

  if (allFailed([storage, promptLength, creationAssistant])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <WebResearchSection timeRange={timeRange} teamIds={teamIds} userFilter={userFilter} />

      <AnalyticsSection id="storage">
        <AnalyticsTable
          id="storage"
          hideTitle
          columns={storageColumns}
          rows={storageRows}
          rowKey={(r) => r.team_id}
          isLoading={storage.isLoading}
          isError={storage.isError}
        />
      </AnalyticsSection>

      <AnalyticsSection id="agentBuild">
        <div className={styles.chartGrid}>
          <div className={styles.block}>
            <HistogramChart
              title={t("rework.analytics.agents.promptLengthDistribution.title")}
              rows={promptLength.data?.rows ?? []}
              valueLabel={t("rework.analytics.agents.promptLengthDistribution.valueLabel")}
              emptyMessage={t(
                teamScoped
                  ? "rework.analytics.scope.notForTeams"
                  : "rework.analytics.agents.promptLengthDistribution.empty",
              )}
              isLoading={promptLength.isLoading}
              isError={promptLength.isError}
              flat
              labelled
            />
            {promptAgents > 0 && (
              <p className={styles.note}>
                {t("rework.analytics.agents.promptLengthDistribution.agentCount", {
                  count: promptAgents,
                  value: formatValue(promptAgents, "count", i18n.language),
                })}
              </p>
            )}
          </div>
          <InfoTile
            id="creationAssistant"
            value={creationAssistant.data?.drafts}
            caption={t("rework.analytics.tiles.creationAssistant.caption", {
              tokens: creationAssistant.data?.total_tokens ?? 0,
            })}
            {...(teamScoped && { unavailable: true, noDataLabel: t("rework.analytics.scope.notForTeamsShort") })}
            isLoading={creationAssistant.isLoading}
            isError={creationAssistant.isError}
          />
        </div>
      </AnalyticsSection>
    </div>
  );
}
