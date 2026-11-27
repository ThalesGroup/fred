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

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import Icon, { type IconProps } from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import LocalizedDataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import SearchableCheckboxPicker from "@shared/molecules/SearchableCheckboxPicker/SearchableCheckboxPicker";
import Select from "@shared/molecules/Select/Select";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import { AnalyticsTeamSelector } from "../AnalyticsPage/AnalyticsScopeSelector";
import { ANALYTICS_PRESETS } from "../AnalyticsPage/analyticsQuery";
import {
  type ConversationTraceSummary,
  type TraceCatalogSort,
  type TraceConsentFilter,
  useGetConversationTraceSettingsQuery,
  useListConversationTracesQuery,
  useListConversationTraceTeamsQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  TRACE_LIST_PATH,
  TRACE_TRANSLATION_PREFIX,
  type TraceInspectorOrigin,
  TraceOutcomeBadge,
  TracePageButtons,
} from "./traceControls";
import {
  defaultSort,
  outcomes,
  quickOutcomes,
  quickStatus,
  readCatalogFilters,
  readTraceRefresh,
  traceRefreshIntervals,
  writeCatalogFilters,
} from "./traceCatalogFilters";
import styles from "./ConversationTraces.module.css";
import ConversationTraceSettings from "./ConversationTraceSettings";
import { TraceDeleteButton } from "./TraceDeleteButton";
import { TraceExportButton } from "./TraceExportButton";

type CatalogHistory = {
  pages: readonly string[];
  openedAt: number;
};
const SEARCH_LIMIT = 255;

function TraceFilterButtons<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | undefined;
  options: { value: T; label: string; icon?: IconProps["type"] }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className={styles.filterGroup}>
      <span>{label}</span>
      <div className={styles.segments} role="group" aria-label={label}>
        {options.map(({ value: key, label: text, icon }) => (
          <button key={key} type="button" aria-pressed={key === value} onClick={() => onChange(key)}>
            {icon && <Icon category="outlined" type={icon} />}
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ConversationTraceListPage() {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settings = useGetConversationTraceSettingsQuery(undefined, {
    refetchOnMountOrArgChange: true,
    pollingInterval: 5000,
    skipPollingIfUnfocused: true,
  });
  const capture = settings.isError ? undefined : settings.currentData;
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const history = location.state as CatalogHistory | null;
  const [openedAt] = useState(Date.now);
  const [relativeRefresh, setRelativeRefresh] = useState<{ locationKey: string; at: number }>();
  const refreshedView = relativeRefresh?.locationKey === location.key ? relativeRefresh : undefined;
  const asOf = refreshedView?.at ?? history?.openedAt ?? openedAt;
  const refreshInterval = readTraceRefresh(params);
  const filters = readCatalogFilters(params, asOf);
  const { statusOutcomes, teamIds, consent, period, sort } = filters;
  const [selected, setSelected] = useState<ReadonlySet<string | number>>(new Set());
  const appliedQuery = params.get("q")?.slice(0, SEARCH_LIMIT) ?? "";
  const search = appliedQuery.trim();
  const [draft, setDraft] = useState<{ locationKey: string; value: string }>();
  const queryInput = draft?.locationKey === location.key ? draft.value : appliedQuery;
  const queryInputRef = useRef<HTMLInputElement>(null);
  const [catalogRestarted, setCatalogRestarted] = useState(false);
  const pages = history?.pages ?? [];
  const cursor = pages[pages.length - 1];
  const replaceView = useCallback(
    (next: URLSearchParams, query: string, pages: readonly string[], openedAt = asOf) => {
      const nextParams = new URLSearchParams(next);
      if (query.trim()) nextParams.set("q", query);
      else nextParams.delete("q");
      const state: CatalogHistory = { pages, openedAt };
      setParams(nextParams, { state, replace: true, preventScrollReset: true });
    },
    [asOf, setParams],
  );
  const queryUpdating = queryInput.trim() !== search;

  useEffect(() => {
    if (!queryUpdating) return;
    const timer = window.setTimeout(() => {
      replaceView(params, queryInput, []);
      setCatalogRestarted(false);
      setSelected(new Set());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [params, queryInput, queryUpdating, replaceView]);

  const searchOutcomes = search
    ? outcomes.filter((outcome) => t(`outcome.${outcome}`).toLocaleLowerCase().includes(search.toLocaleLowerCase()))
    : [];
  const teams = useListConversationTraceTeamsQuery(undefined, { refetchOnMountOrArgChange: true });
  const catalog = useListConversationTracesQuery(
    {
      failedOnly: false,
      outcomes: statusOutcomes.length ? statusOutcomes : undefined,
      teamIds: teamIds.length ? teamIds : undefined,
      consent,
      query: search || undefined,
      queryOutcomes: searchOutcomes.length ? searchOutcomes : undefined,
      since: period.since,
      until: period.presetKey && !period.offset ? undefined : period.until,
      sort: sort.field,
      direction: sort.direction,
      cursor,
      limit: 20,
    },
    { refetchOnMountOrArgChange: true },
  );
  const staleCursor = Boolean(cursor) && catalog.error && "status" in catalog.error && catalog.error.status === 409;
  useEffect(() => {
    if (!staleCursor) return;
    replaceView(params, queryInput, []);
    setCatalogRestarted(true);
  }, [staleCursor, params, queryInput, replaceView]);
  const relative = Boolean(period.presetKey && !period.offset);
  const { refetch } = catalog;
  const refreshCatalog = useCallback(() => {
    if (queryUpdating) return;
    if (relative) {
      const now = Date.now();
      setRelativeRefresh({ locationKey: location.key, at: now });
      if (readCatalogFilters(params, now).period.since !== period.since) return;
    }
    void refetch();
  }, [location.key, params, period.since, queryUpdating, refetch, relative]);
  useEffect(() => {
    if (!refreshInterval) return;
    const timer = window.setInterval(refreshCatalog, refreshInterval * 1000);
    return () => window.clearInterval(timer);
  }, [refreshCatalog, refreshInterval]);
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "medium" });
  const minutes = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "minute", unitDisplay: "short" });
  const seconds = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "second", unitDisplay: "short" });
  const visibleData = catalog.currentData ?? (refreshedView && catalog.isFetching ? catalog.data : undefined);
  const rows = visibleData?.conversations ?? [];
  const picked = rows.map(({ session_id }) => session_id).filter((id) => selected.has(id));
  const status = quickStatus(statusOutcomes);
  const inspectorOrigin: TraceInspectorOrigin = { listSearch: location.search, listSteps: 1 };
  const sortLabels: Record<TraceCatalogSort, string> = {
    title: t("conversation"),
    user: t("user"),
    team: t("team"),
    outcome: t("outcomeLabel"),
    consent: t("consentFilter"),
    latest: t("latestTurn"),
  };

  function clearSelection() {
    setSelected(new Set());
    setCatalogRestarted(false);
  }

  function resetPage() {
    if (cursor) replaceView(params, queryInput, []);
    clearSelection();
  }

  function changeFilters(patch: Partial<typeof filters>) {
    const currentPreset = patch.period?.presetKey && !patch.period.offset;
    replaceView(
      writeCatalogFilters(params, { ...filters, ...patch }),
      queryInput,
      [],
      currentPreset ? Date.parse(patch.period.until) : asOf,
    );
    clearSelection();
  }

  const columns: DataTableColumn<ConversationTraceSummary>[] = [
    {
      label: sortLabels.title,
      size: "minmax(13rem, 2fr)",
      sortable: true,
      cellRenderer: (row) => (
        <Link
          className={styles.conversationLink}
          to={`${TRACE_LIST_PATH}/${encodeURIComponent(row.session_id)}`}
          state={inspectorOrigin}
        >
          <strong>{row.title || t("maskedConversation")}</strong>
          <span>{row.agent_display_name}</span>
        </Link>
      ),
    },
    {
      label: sortLabels.user,
      size: "minmax(6.5rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => row.user_display_name || row.username || row.user_id || t("unavailable"),
    },
    {
      label: sortLabels.team,
      size: "minmax(6.5rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => row.team_name,
    },
    {
      label: sortLabels.outcome,
      size: "minmax(10rem, 1.2fr)",
      sortable: true,
      cellRenderer: (row) => (
        <div className={styles.chips}>
          {(row.outcomes?.length ? row.outcomes : [row.failure_category ?? row.outcome]).map((outcome) => (
            <TraceOutcomeBadge key={outcome} outcome={outcome} />
          ))}
        </div>
      ),
    },
    {
      label: sortLabels.consent,
      size: "minmax(9rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => (
        <div className={styles.catalogMetadata}>
          <Chip label={t(`catalogAccess.${row.access}`)} tone={row.access === "masked" ? "default" : "tertiary"} />
          {row.availability !== "captured" && <small>{t(`evidence.${row.availability}`)}</small>}
        </div>
      ),
    },
    {
      label: sortLabels.latest,
      size: "minmax(11rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => (
        <time dateTime={row.latest_started_at}>{date.format(new Date(row.latest_started_at))}</time>
      ),
    },
  ];

  return (
    <div className={`${styles.page} ${styles.catalogPage}`}>
      <PageHeader
        title={t("title")}
        subtitle={t("catalogDescription")}
        actions={
          <>
            {capture?.degradation_reason && (
              <Chip label={t(`degradation.${capture.degradation_reason}`)} tone="error" />
            )}
            <div className={styles.captureControls}>
              {capture &&
                (capture.enabled ? (
                  <StatusBadge label={t("captureOn")} tone="success" />
                ) : (
                  <Chip label={t("captureOff")} />
                ))}
              <Button
                variant="outlined"
                color="on-surface"
                size="small"
                icon={{ category: "outlined", type: "settings" }}
                onClick={() => setSettingsOpen(true)}
              >
                {t("settings")}
              </Button>
            </div>
          </>
        }
      />
      {settingsOpen && (
        <ConversationTraceSettings settings={settings} onClose={() => setSettingsOpen(false)} onFlushed={resetPage} />
      )}
      <div className={styles.filters} role="group" aria-label={t("filtersLabel")}>
        <div className={styles.primaryFilters}>
          <TextInput
            ref={queryInputRef}
            label={t("searchLabel")}
            size="medium"
            type="search"
            compact
            maxLength={SEARCH_LIMIT}
            showCharacterCount={false}
            placeholder={t("searchPlaceholder")}
            icon={{ category: "outlined", type: "search" }}
            value={queryInput}
            onChange={(event) => setDraft({ locationKey: location.key, value: event.currentTarget.value })}
          />
          <div className={styles.filterGroup}>
            <span>{t("team")}</span>
            <AnalyticsTeamSelector
              teams={teams.currentData ?? []}
              loaded={teams.isSuccess}
              value={teamIds}
              onChange={(teamIds) => changeFilters({ teamIds })}
            />
            {teams.isError && <span role="alert">{t("teamsError")}</span>}
          </div>
          <div className={styles.filterGroup}>
            <span>{t("latestTurn")}</span>
            <TimeRangeSelector
              value={period}
              onChange={(period) => changeFilters({ period })}
              presetKeys={ANALYTICS_PRESETS}
            />
          </div>
        </div>
        <div className={styles.secondaryFilters}>
          <TraceFilterButtons
            label={t("status")}
            value={status}
            options={[
              { value: "all", label: t("quickStatus.all") },
              { value: "completed", label: t("quickStatus.completed"), icon: "check" },
              { value: "failed", label: t("quickStatus.failed"), icon: "error" },
            ]}
            onChange={(key) => changeFilters({ statusOutcomes: quickOutcomes[key] })}
          />
          <TraceFilterButtons<TraceConsentFilter>
            label={t("consentFilter")}
            value={consent}
            options={[
              { value: "all", label: t("consentOptions.all") },
              { value: "shared", label: t("consentOptions.shared"), icon: "check_circle" },
              { value: "masked", label: t("consentOptions.masked"), icon: "lock" },
            ]}
            onChange={(consent) => changeFilters({ consent })}
          />
          <div className={styles.filterGroup}>
            <span>{t("outcomeLabel")}</span>
            <SearchableCheckboxPicker
              icon="tune"
              value={statusOutcomes}
              onChange={(next) => changeFilters({ statusOutcomes: next.length === outcomes.length ? [] : next })}
              triggerLabel={
                statusOutcomes.length
                  ? t("outcomePicker.count", { count: statusOutcomes.length })
                  : t("outcomePicker.all")
              }
              options={outcomes.map((outcome) => ({
                value: outcome,
                label: t(`outcome.${outcome}`),
                content: <TraceOutcomeBadge outcome={outcome} />,
              }))}
              labels={{
                title: t("outcomeLabel"),
                reset: t("outcomePicker.all"),
                search: t("outcomePicker.search"),
                searchPlaceholder: t("outcomePicker.search"),
                clearSearch: t("clearSearch"),
                selected: t("outcomePicker.selected"),
                others: t("outcomePicker.others"),
                empty: t("outcomePicker.empty"),
                cancel: t("manual.cancel"),
                apply: t("outcomePicker.apply"),
              }}
            />
          </div>
        </div>
      </div>
      <div className={styles.tableSection}>
        <div className={styles.bulkActions}>
          <span aria-live="polite">
            {t(picked.length ? "selectedCount" : "pageCount", { count: picked.length || rows.length })}
          </span>
          <div className={styles.catalogActions}>
            <div className={styles.chips}>
              <TraceExportButton sessionIds={picked} disabled={catalog.isFetching || queryUpdating} />
              <TraceDeleteButton
                mode="selected"
                sessionIds={picked}
                disabled={catalog.isFetching || queryUpdating}
                onDeleted={resetPage}
              />
            </div>
            <div className={styles.chips}>
              <IconButton
                icon={{ category: "outlined", type: "refresh" }}
                variant="icon"
                size="small"
                aria-label={t("refresh")}
                title={t("refresh")}
                disabled={catalog.isFetching || queryUpdating}
                onClick={refreshCatalog}
              />
              <div title={t("autoRefresh")}>
                <Select
                  size="small"
                  compact
                  ariaLabel={t("autoRefresh")}
                  value={refreshInterval}
                  options={traceRefreshIntervals.map((interval) => ({
                    key: String(interval),
                    value: interval,
                    label:
                      interval === 0
                        ? t("refreshOff")
                        : interval < 60
                          ? seconds.format(interval)
                          : minutes.format(interval / 60),
                  }))}
                  onChange={(interval) => {
                    const next = new URLSearchParams(params);
                    next.set("refresh", String(interval));
                    replaceView(next, queryInput, pages);
                  }}
                />
              </div>
            </div>
          </div>
        </div>
        {catalogRestarted && !cursor && <p role="status">{t("catalogRestarted")}</p>}
        {catalog.isError && !staleCursor ? (
          <p role="alert" className={styles.error}>
            {t("listError")}
          </p>
        ) : rows.length > 0 ? (
          <div className={styles.listTable}>
            <LocalizedDataTable
              size="medium"
              data={rows}
              columns={columns}
              rowKey={(row) => row.session_id}
              selectable
              selectedKeys={selected}
              onSelectionChange={setSelected}
              sortState={{ columnLabel: sortLabels[sort.field], direction: sort.direction }}
              onSortChange={(next) => {
                const field = (Object.keys(sortLabels) as TraceCatalogSort[]).find(
                  (key) => sortLabels[key] === next?.columnLabel,
                );
                changeFilters({ sort: field && next ? { field, direction: next.direction } : defaultSort });
              }}
            />
          </div>
        ) : catalog.isFetching || queryUpdating ? (
          <p className={styles.empty} role="status">
            {t("loading")}
          </p>
        ) : (
          <div className={styles.catalogEmpty}>
            <PageEmptyState message={t("noMatches")} icon="search" />
            {search && statusOutcomes.length > 0 && (
              <Button
                color="on-surface"
                variant="outlined"
                size="small"
                onClick={() => {
                  changeFilters({ statusOutcomes: quickOutcomes.all });
                  queryInputRef.current?.focus();
                }}
              >
                {t("showAllSearchOutcomes")}
              </Button>
            )}
          </div>
        )}
        <TracePageButtons
          pager={{
            cursor,
            next: (next) => replaceView(params, queryInput, [...pages, next]),
            previous: () => replaceView(params, queryInput, pages.slice(0, -1)),
          }}
          nextCursor={catalog.currentData?.next_cursor ?? null}
          disabled={catalog.isFetching || queryUpdating || Boolean(staleCursor)}
        />
      </div>
    </div>
  );
}
