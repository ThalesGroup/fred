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

import {
  useAnalyticsAdoptionQuery,
  useAnalyticsUsageQuery,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import AdoptionFunnel from "../AdoptionFunnel";
import CohortTable from "../CohortTable";
import { AnalyticsSection, AnalyticsServiceDown } from "../AnalyticsSection";
import InfoTile from "../InfoTile";
import { allFailed, type AnalyticsTabProps, KPI_CACHE, zonedKpiArgs } from "../analyticsQuery";
import styles from "../AnalyticsPage.module.css";

export default function AdoptionTab({ timeRange, teamIds, userFilter, days }: AnalyticsTabProps) {
  const adoption = useAnalyticsAdoptionQuery(zonedKpiArgs(timeRange, teamIds, userFilter, days), KPI_CACHE);
  const data = adoption.data;
  const tile = { isLoading: adoption.isLoading, isError: adoption.isError };
  const usage = useAnalyticsUsageQuery(zonedKpiArgs(timeRange, teamIds, userFilter, days), KPI_CACHE);

  if (allFailed([adoption, usage])) return <AnalyticsServiceDown />;

  return (
    <div className={styles.tabContent}>
      <AnalyticsSection id="reach">
        <div className={styles.mainAside}>
          <AdoptionFunnel data={data} {...tile} />
          <div className={styles.stack}>
            <InfoTile
              id="activeUsersPerWorkday"
              period={usage.data?.active_users_per_workday}
              format="decimal"
              isLoading={usage.isLoading}
              isError={usage.isError}
            />
          </div>
        </div>
      </AnalyticsSection>

      <AnalyticsSection id="activation">
        <div className={styles.asideMain}>
          <div className={styles.stack}>
            <InfoTile
              id="firstMessageWithin7Days"
              period={data?.first_message_within_7_days_rate}
              format="percent"
              deltaKind="points"
              {...tile}
            />
            <InfoTile
              id="daysToFirstMessage"
              period={data?.median_days_to_first_message}
              format="days"
              lowerIsBetter
              {...tile}
            />
          </div>
          <CohortTable rows={data?.cohorts} {...tile} />
        </div>
      </AnalyticsSection>
    </div>
  );
}
