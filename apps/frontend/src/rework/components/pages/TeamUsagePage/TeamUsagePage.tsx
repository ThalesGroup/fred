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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./TeamUsagePage.module.css";
import {
  useUserTokenUsageOverTimeQuery,
  useUserTokenUsageByAgentQuery,
  useUserTokenUsageByModelQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { TIME_PRESETS } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import TimeSeriesLineChart from "@shared/molecules/TimeSeriesLineChart/TimeSeriesLineChart";
import BarChart from "@shared/molecules/BarChart/BarChart";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import IconButton from "@shared/atoms/IconButton/IconButton";

const defaultPreset = TIME_PRESETS.find((p) => p.key === "last30d")!;
const defaultRange: TimeRange = { ...defaultPreset.resolve(), presetKey: "last30d" };

/**
 * Personal token-usage dashboard — OBSERV-02 / BACKLOG.md §7b.
 * Reuses the same chart primitives and layout as the platform AnalyticsPage,
 * self-scoped to the requesting user by the backend presets (no team/agent
 * picker: this is "my own consumption", not an admin view).
 */
export default function TeamUsagePage() {
  const { t } = useTranslation();
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultRange);

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
    </div>
  );
}
