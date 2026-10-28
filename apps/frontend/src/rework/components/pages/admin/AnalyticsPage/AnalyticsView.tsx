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

import { useState, type ComponentType, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Button from "@shared/atoms/Button/Button";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import { resolvePreset, type TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { InfoIcon } from "./AnalyticsSection";
import AnalyticsScopeSelector, { AnalyticsScopeSummary } from "./AnalyticsScopeSelector";
import AnalyticsUserFilter, { AnalyticsUserFilterSummary } from "./AnalyticsUserFilter";
import {
  ANALYTICS_PRESETS,
  type AnalyticsMode,
  type AnalyticsTabProps,
  type AnalyticsUserFilterValue,
  userFilterParam,
  zonedKpiArgs,
} from "./analyticsQuery";
import { exportAnalytics } from "./exportAnalytics";
import AdoptionTab from "./tabs/AdoptionTab";
import AgentsTab from "./tabs/AgentsTab";
import OverviewTab from "./tabs/OverviewTab";
import QualityCostTab from "./tabs/QualityCostTab";
import TeamsTab from "./tabs/TeamsTab";
import TechnicalTab from "./tabs/TechnicalTab";
import UsageTab from "./tabs/UsageTab";
import styles from "./AnalyticsPage.module.css";

const ANALYTICS_TABS = ["overview", "adoption", "usage", "teams", "agents", "cost", "tech"] as const;
type AnalyticsTab = (typeof ANALYTICS_TABS)[number];
// The Technical tab is platform operations: not shown on a team's page.
const TEAM_TABS = ANALYTICS_TABS.filter((id) => id !== "tech");
const EXTRA_TAB = "extra";

const TAB_CONTENT: Record<AnalyticsTab, ComponentType<AnalyticsTabProps>> = {
  overview: OverviewTab,
  adoption: AdoptionTab,
  usage: UsageTab,
  teams: TeamsTab,
  agents: AgentsTab,
  cost: QualityCostTab,
  tech: TechnicalTab,
};

interface AnalyticsViewProps {
  title: string;
  mode: AnalyticsMode;
  /** Fixed scope in team mode; the platform page lets the viewer choose it. */
  teamIds?: string[];
  /** A last tab outside the analytics catalog, such as the viewer's own usage. */
  extraTab?: { label: string; render: (timeRange: TimeRange) => ReactNode };
}

/** Analytics, one tab per question family. Only the selected tab mounts, so only its reads run. */
export default function AnalyticsView({ title, mode, teamIds: fixedTeamIds, extraTab }: AnalyticsViewProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  const [exporting, setExporting] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>(() => resolvePreset("last30d"));
  const [selectedTeamIds, setTeamIds] = useState<string[]>([]);
  const teamIds = fixedTeamIds ?? selectedTeamIds;
  // Account attributes are platform data: never filtered on a team's page.
  const [selectedUserFilter, setUserFilter] = useState<AnalyticsUserFilterValue | null>(null);
  const userFilter = mode === "platform" ? userFilterParam(selectedUserFilter) : undefined;
  const tabIds: string[] = [...(mode === "team" ? TEAM_TABS : ANALYTICS_TABS), ...(extraTab ? [EXTRA_TAB] : [])];
  const [tab, setTab] = useState<string>("overview");
  const tabLabel = (id: string) => (id === EXTRA_TAB ? extraTab!.label : t(`rework.analytics.tabs.${id}`));
  const Content = TAB_CONTENT[tab as AnalyticsTab];

  const handleExport = async () => {
    setExporting(true);
    try {
      const lang = i18n.language.startsWith("fr") ? "fr" : "en";
      await exportAnalytics({ ...zonedKpiArgs(timeRange, teamIds, userFilter), lang });
    } catch {
      showError({ summary: t("rework.analytics.exportError") });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <PageHeader
          title={title}
          titleAction={
            <InfoIcon
              label={t("rework.analytics.aboutLabel")}
              content={t(mode === "team" ? "rework.analytics.aboutTeam" : "rework.analytics.about")}
            />
          }
          filters={
            <>
              {mode === "platform" && (
                <>
                  <AnalyticsScopeSelector value={teamIds} onChange={setTeamIds} />
                  <AnalyticsUserFilter value={selectedUserFilter} onChange={setUserFilter} />
                </>
              )}
              <TimeRangeSelector value={timeRange} onChange={setTimeRange} presetKeys={ANALYTICS_PRESETS} />
              <Button
                variant="filled"
                color="primary"
                size="medium"
                icon={{ category: "outlined", type: "download" }}
                disabled={exporting}
                aria-busy={exporting}
                onClick={handleExport}
              >
                {t(exporting ? "rework.analytics.exporting" : "rework.analytics.export")}
              </Button>
            </>
          }
          tabs={
            <ButtonGroup
              variant="tabs"
              size="small"
              color="on-surface"
              surface="surface-container-high"
              aria-label={t("rework.analytics.tabsLabel")}
              items={tabIds.map((id) => ({ label: tabLabel(id) }))}
              selectedIndex={tabIds.indexOf(tab)}
              onSelectedIndexChange={(index) => setTab(tabIds[index])}
            />
          }
        />
        {mode === "platform" && (
          <>
            <AnalyticsScopeSummary value={teamIds} timeRange={timeRange} />
            <AnalyticsUserFilterSummary value={selectedUserFilter} onClear={() => setUserFilter(null)} />
          </>
        )}
      </div>
      <div role="tabpanel" aria-label={tabLabel(tab)} className={styles.body}>
        {tab === EXTRA_TAB ? (
          extraTab!.render(timeRange)
        ) : (
          <Content timeRange={timeRange} teamIds={teamIds} mode={mode} userFilter={userFilter} />
        )}
      </div>
    </div>
  );
}
