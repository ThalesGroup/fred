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

import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
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

/** Rows to list: the search match, applied selection first so rows do not jump while ticking. */
export function orderScopeRows(teams: AnalyticsTeamRow[], applied: string[], search: string) {
  const q = search.trim().toLowerCase();
  const matches = q ? teams.filter((team) => team.name.toLowerCase().includes(q)) : teams;
  const pinned = new Set(applied);
  return {
    selected: matches.filter((team) => pinned.has(team.team_id)),
    others: matches.filter((team) => !pinned.has(team.team_id)),
  };
}

/** Header control choosing the analytics scope: the whole platform or a set of teams. */
export default function AnalyticsScopeSelector({
  value,
  onChange,
}: ScopeProps & { onChange: (ids: string[]) => void }) {
  const { t } = useTranslation();
  const { teams, loaded } = useTeamCatalog();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  const open = () => {
    setDraft(new Set(value));
    setSearch("");
    setIsOpen(true);
  };

  const toggle = (id: string) =>
    setDraft((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const apply = () => {
    // Catalog order: equal selections give equal query args, so cached reads are reused.
    onChange(teams.map((team) => team.team_id).filter((id) => draft.has(id)));
    setIsOpen(false);
  };

  const { selected, others } = useMemo(() => orderScopeRows(teams, value, search), [teams, value, search]);
  const label = scopeLabel(value, teams, t);

  const renderRow = (team: AnalyticsTeamRow) => (
    <label key={team.team_id} className={styles.row}>
      <Checkbox checked={draft.has(team.team_id)} onChange={() => toggle(team.team_id)} />
      <span className={styles.rowLabel}>{team.name}</span>
      <span className={styles.rowMeta}>{t("rework.analytics.scope.members", { count: team.member_count })}</span>
    </label>
  );

  return (
    <div className={styles.container} ref={containerRef} data-open={isOpen}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => (isOpen ? setIsOpen(false) : open())}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title={label}
      >
        <Icon category="outlined" type="groups" />
        <span className={styles.label}>{label}</span>
        <Icon category="outlined" type="arrow_drop_down" />
      </button>

      {isOpen && (
        <div className={styles.panel} role="dialog" aria-label={t("rework.analytics.scope.title")}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={t("rework.analytics.scope.searchPlaceholder")}
            ariaLabel={t("rework.analytics.scope.search")}
            clearAriaLabel={t("rework.analytics.scope.clearSearch")}
            size="xs"
            autoFocus
          />
          <label className={`${styles.row} ${styles.platformRow}`}>
            <Checkbox checked={draft.size === 0} onChange={() => setDraft(new Set())} />
            <span className={styles.rowLabel}>{t("rework.analytics.scope.platform")}</span>
          </label>
          <div className={styles.separator} />
          <div className={styles.list}>
            {selected.length > 0 && <span className={styles.groupLabel}>{t("rework.analytics.scope.selected")}</span>}
            {selected.map(renderRow)}
            {selected.length > 0 && others.length > 0 && (
              <span className={styles.groupLabel}>{t("rework.analytics.scope.otherTeams")}</span>
            )}
            {others.map(renderRow)}
            {selected.length + others.length === 0 && (
              <p className={styles.empty}>{t("rework.analytics.scope.noTeams")}</p>
            )}
          </div>
          <div className={styles.footer}>
            <Button variant="text" color="primary" size="small" onClick={() => setIsOpen(false)}>
              {t("rework.analytics.scope.cancel")}
            </Button>
            {/* Apply filters the draft through the catalog: not before it is there. */}
            <Button variant="filled" color="primary" size="small" onClick={apply} disabled={!loaded}>
              {t("rework.analytics.scope.apply")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Under a team scope: the first teams as chips, how many more, and their distinct members. */
export function AnalyticsScopeSummary({ value, timeRange }: ScopeProps & { timeRange: TimeRange }) {
  const { t } = useTranslation();
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
  const members = adoption.data?.people_with_access;
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

export function scopeLabel(value: string[], teams: AnalyticsTeamRow[], t: TFunction) {
  if (value.length === 0) return t("rework.analytics.scope.platform");
  if (value.length === 1) {
    const team = teams.find((row) => row.team_id === value[0]);
    if (team) return team.name;
  }
  return t("rework.analytics.scope.teamsSelected", { count: value.length });
}
