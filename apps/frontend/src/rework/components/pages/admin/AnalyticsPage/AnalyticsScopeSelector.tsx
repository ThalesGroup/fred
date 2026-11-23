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

import type { TFunction } from "i18next";
import { useAnalyticsTranslation } from "./useAnalyticsTranslation";
import Chip from "@shared/atoms/Chip/Chip";
import SearchableCheckboxPicker, {
  groupCheckboxOptions,
  type CheckboxOption,
} from "@shared/molecules/SearchableCheckboxPicker/SearchableCheckboxPicker";
import type { TimeRange } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import {
  useAnalyticsAdoptionQuery,
  useAnalyticsTeamsCatalogQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AnalyticsTeamRow } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { KPI_CACHE, zonedKpiArgs } from "./analyticsQuery";
import styles from "./AnalyticsScopeSelector.module.scss";

const SUMMARY_CHIPS = 4;

interface ScopeProps {
  /** Selected team ids; empty means the whole platform. */
  value: string[];
}

function useTeamCatalog() {
  const { data } = useAnalyticsTeamsCatalogQuery({}, KPI_CACHE);
  return { teams: data?.rows ?? [], loaded: data !== undefined };
}

export function orderScopeRows(teams: AnalyticsTeamRow[], applied: string[], search: string) {
  const options = teams.map((team) => ({ value: team.team_id, label: team.name, team }));
  const { selected, others } = groupCheckboxOptions(options, applied, search);
  return { selected: selected.map(({ team }) => team), others: others.map(({ team }) => team) };
}

/** Header control choosing the analytics scope: the whole platform or a set of teams. */
export default function AnalyticsScopeSelector(props: ScopeProps & { onChange: (ids: string[]) => void }) {
  const { teams, loaded } = useTeamCatalog();
  return <AnalyticsTeamSelector {...props} teams={teams} loaded={loaded} />;
}

type TeamOption = Pick<AnalyticsTeamRow, "team_id" | "name"> & Partial<Pick<AnalyticsTeamRow, "member_count">>;

export function AnalyticsTeamSelector({
  value,
  onChange,
  teams,
  loaded,
}: ScopeProps & { onChange: (ids: string[]) => void; teams: TeamOption[]; loaded: boolean }) {
  const { t } = useAnalyticsTranslation();
  const options: CheckboxOption<string>[] = teams.map((team) => ({
    value: team.team_id,
    label: team.name,
    detail: team.member_count == null ? undefined : t("rework.analytics.scope.members", { count: team.member_count }),
  }));
  return (
    <SearchableCheckboxPicker
      icon="groups"
      value={value}
      onChange={onChange}
      options={options}
      loading={!loaded}
      triggerLabel={scopeLabel(value, teams, t)}
      labels={{
        title: t("rework.analytics.scope.title"),
        reset: t("rework.analytics.scope.platform"),
        search: t("rework.analytics.scope.search"),
        searchPlaceholder: t("rework.analytics.scope.searchPlaceholder"),
        clearSearch: t("rework.analytics.scope.clearSearch"),
        selected: t("rework.analytics.scope.selected"),
        others: t("rework.analytics.scope.otherTeams"),
        empty: t("rework.analytics.scope.noTeams"),
        cancel: t("rework.analytics.scope.cancel"),
        apply: t("rework.analytics.scope.apply"),
      }}
    />
  );
}

/** Under a team scope: the first teams as chips, how many more, and their distinct members. */
export function AnalyticsScopeSummary({ value, timeRange }: ScopeProps & { timeRange: TimeRange }) {
  const { t } = useAnalyticsTranslation();
  const { teams } = useTeamCatalog();
  // People in several teams count once: the adoption read's people with access (same cached read).
  const adoption = useAnalyticsAdoptionQuery(zonedKpiArgs(timeRange, value), {
    ...KPI_CACHE,
    skip: value.length === 0,
  });
  if (value.length === 0) return null;
  const picked = new Set(value);
  const selected = teams.filter((team) => picked.has(team.team_id));
  if (selected.length === 0) return null;
  const members = adoption.currentData?.people_with_access;
  const more = selected.length - SUMMARY_CHIPS;
  return (
    <div className={styles.summary}>
      {selected.slice(0, SUMMARY_CHIPS).map((team) => (
        <Chip key={team.team_id} label={team.name} />
      ))}
      {more > 0 && <span className={styles.summaryText}>{t("rework.analytics.scope.more", { count: more })}</span>}
      {members != null && (
        <span className={styles.summaryText}>{t("rework.analytics.scope.membersTotal", { count: members })}</span>
      )}
    </div>
  );
}

export function scopeLabel(value: string[], teams: TeamOption[], t: TFunction) {
  if (value.length === 0) return t("rework.analytics.scope.platform");
  if (value.length === 1) {
    const team = teams.find((row) => row.team_id === value[0]);
    if (team) return team.name;
  }
  return t("rework.analytics.scope.teamsSelected", { count: value.length });
}
