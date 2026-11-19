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

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import LocalizedDataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import SearchableCheckboxPicker from "@shared/molecules/SearchableCheckboxPicker/SearchableCheckboxPicker";
import TimeRangeSelector from "@shared/molecules/TimeRangeSelector/TimeRangeSelector";
import { resolvePreset } from "@shared/molecules/TimeRangeSelector/timeRange.types";
import { AnalyticsTeamSelector } from "../AnalyticsPage/AnalyticsScopeSelector";
import { ANALYTICS_PRESETS } from "../AnalyticsPage/analyticsQuery";
import {
  type ConversationTraceSummary,
  type TraceCatalogSort,
  type TraceConsentFilter,
  type TraceOutcome,
  type TraceFailureCategory,
  useListConversationTracesQuery,
  useListConversationTraceTeamsQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  TRACE_LIST_PATH,
  TRACE_TRANSLATION_PREFIX,
  TraceIdentifier,
  TraceOutcomeBadge,
  TracePageButtons,
  useTracePagination,
} from "./traceControls";
import styles from "./ConversationTraces.module.css";
import ConversationTraceSettings from "./ConversationTraceSettings";
import { TraceDeleteButton } from "./TraceDeleteButton";
import { TraceExportButton } from "./TraceExportButton";

type OutcomeFilter = TraceOutcome | TraceFailureCategory;
type QuickStatus = "all" | "completed" | "failed";

const failureCategories: TraceFailureCategory[] = [
  "http_5xx",
  "http_429",
  "http_400",
  "http_other_4xx",
  "stream_interrupted",
  "timeout_or_connection",
  "context_limit",
  "tool_or_capability",
  "internal_or_unknown",
];
const quickOutcomes: Record<QuickStatus, OutcomeFilter[]> = {
  all: [],
  completed: ["completed"],
  failed: [...failureCategories, "failed"],
};
const quickStatuses = Object.keys(quickOutcomes) as QuickStatus[];
const outcomes: OutcomeFilter[] = ["completed", ...quickOutcomes.failed, "paused", "unknown"];
const consentFilters: TraceConsentFilter[] = ["all", "shared", "masked"];

function TraceFilterButtons<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | undefined;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className={styles.filterGroup}>
      <span>{label}</span>
      <div className={styles.filters} role="group" aria-label={label}>
        {options.map((option) => (
          <Button
            key={option.value}
            type="button"
            color="secondary"
            size="small"
            aria-pressed={option.value === value}
            variant={option.value === value ? "tonal" : "text"}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

export default function ConversationTraceListPage() {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [statusOutcomes, setStatusOutcomes] = useState(quickOutcomes.failed);
  const [selected, setSelected] = useState<ReadonlySet<string | number>>(new Set());
  const [teamIds, setTeamIds] = useState<string[]>([]);
  const [consent, setConsent] = useState<TraceConsentFilter>("all");
  const [period, setPeriod] = useState(() => resolvePreset("last30d"));
  const [queryInput, setQueryInput] = useState("");
  const [userInput, setUserInput] = useState("");
  const [search, setSearch] = useState({ query: "", userId: "" });
  const [catalogRestarted, setCatalogRestarted] = useState(false);
  const [sort, setSort] = useState<{ field: TraceCatalogSort; direction: "asc" | "desc" }>({
    field: "latest",
    direction: "desc",
  });
  const pager = useTracePagination();
  const resetPage = pager.reset;
  const queryUpdating = queryInput.trim() !== search.query || userInput.trim() !== search.userId;

  useEffect(() => {
    if (!queryUpdating) return;
    const timer = window.setTimeout(() => {
      setSearch({ query: queryInput.trim(), userId: userInput.trim() });
      resetPage();
      setCatalogRestarted(false);
      setSelected(new Set());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [queryInput, userInput, queryUpdating, resetPage]);

  const teams = useListConversationTraceTeamsQuery(undefined, { refetchOnMountOrArgChange: true });
  const catalog = useListConversationTracesQuery(
    {
      failedOnly: false,
      outcomes: statusOutcomes.length ? statusOutcomes : undefined,
      teamIds: teamIds.length ? teamIds : undefined,
      consent,
      query: search.query || undefined,
      userId: search.userId || undefined,
      since: period.since,
      until: period.presetKey && !period.offset ? undefined : period.until,
      sort: sort.field,
      direction: sort.direction,
      cursor: pager.cursor,
      limit: 20,
    },
    { refetchOnMountOrArgChange: true },
  );
  const staleCursor =
    Boolean(pager.cursor) && catalog.error && "status" in catalog.error && catalog.error.status === 409;
  useEffect(() => {
    if (!staleCursor) return;
    resetPage();
    setCatalogRestarted(true);
  }, [staleCursor, resetPage]);
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });
  const rows = catalog.currentData?.conversations ?? [];
  const picked = rows.map(({ session_id }) => session_id).filter((id) => selected.has(id));
  const status = quickStatuses.find((key) => {
    const preset = quickOutcomes[key];
    return preset.length === statusOutcomes.length && preset.every((outcome) => statusOutcomes.includes(outcome));
  });
  const sortLabels: Record<TraceCatalogSort, string> = {
    title: t("conversation"),
    user: t("user"),
    team: t("team"),
    outcome: t("outcomeLabel"),
    consent: t("consentFilter"),
    latest: t("latestTurn"),
  };

  function clearPick() {
    setSelected(new Set());
    setCatalogRestarted(false);
    resetPage();
  }

  const changeFilter =
    <T,>(change: (value: T) => void) =>
    (value: T) => {
      change(value);
      clearPick();
    };

  const columns: DataTableColumn<ConversationTraceSummary>[] = [
    {
      label: sortLabels.title,
      size: "minmax(13rem, 2fr)",
      sortable: true,
      cellRenderer: (row) => (
        <div className={styles.conversationCell}>
          <Link className={styles.link} to={`${TRACE_LIST_PATH}/${encodeURIComponent(row.session_id)}`}>
            {row.title || t("maskedConversation")}
          </Link>
          <span>{row.agent_display_name}</span>
          {row.support_error_ref && (
            <div>
              <span>{t("supportErrorRef")}</span>
              <TraceIdentifier label={t("supportErrorRef")} value={row.support_error_ref} />
            </div>
          )}
        </div>
      ),
    },
    {
      label: sortLabels.user,
      size: "minmax(7rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => row.username || row.user_id || t("unavailable"),
    },
    {
      label: sortLabels.team,
      size: "minmax(8rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => row.team_name,
    },
    {
      label: sortLabels.outcome,
      size: "minmax(9rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => <TraceOutcomeBadge outcome={row.failure_category ?? row.outcome} />,
    },
    {
      label: sortLabels.consent,
      size: "minmax(7rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => t(`catalogAccess.${row.access}`),
    },
    {
      label: t("availability"),
      size: "minmax(7rem, 1fr)",
      cellRenderer: ({ availability }) => t(`evidence.${availability}`),
    },
    {
      label: sortLabels.latest,
      size: "minmax(10rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => (
        <time dateTime={row.latest_started_at}>{date.format(new Date(row.latest_started_at))}</time>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={t("title")} />
      <ConversationTraceSettings onFlushed={clearPick} />
      <div className={styles.filterBar} role="group" aria-label={t("filtersLabel")}>
        <div className={styles.filterGroup}>
          <span>{t("searchLabel")}</span>
          <SearchInput
            value={queryInput}
            maxLength={255}
            onChange={setQueryInput}
            ariaLabel={t("searchLabel")}
            placeholder={t("searchPlaceholder")}
            clearAriaLabel={t("clearSearch")}
          />
        </div>
        <div className={styles.filterGroup}>
          <span>{t("user")}</span>
          <SearchInput
            value={userInput}
            maxLength={255}
            onChange={setUserInput}
            ariaLabel={t("user")}
            placeholder={t("userPlaceholder")}
            clearAriaLabel={t("clearUser")}
          />
        </div>
        <div className={styles.filterGroup}>
          <span>{t("team")}</span>
          <AnalyticsTeamSelector
            teams={teams.currentData ?? []}
            loaded={teams.isSuccess}
            value={teamIds}
            onChange={changeFilter(setTeamIds)}
          />
          {teams.isError && <span role="alert">{t("teamsError")}</span>}
        </div>
        <div className={styles.filterGroup}>
          <span>{t("latestTurn")}</span>
          <TimeRangeSelector value={period} onChange={changeFilter(setPeriod)} presetKeys={ANALYTICS_PRESETS} />
        </div>
      </div>
      <div className={styles.filterBar}>
        <TraceFilterButtons<QuickStatus>
          label={t("status")}
          value={status}
          options={quickStatuses.map((key) => ({ value: key, label: t(`quickStatus.${key}`) }))}
          onChange={(key) => changeFilter(setStatusOutcomes)(quickOutcomes[key])}
        />
        <TraceFilterButtons<TraceConsentFilter>
          label={t("consentFilter")}
          value={consent}
          options={consentFilters.map((key) => ({ value: key, label: t(`consentOptions.${key}`) }))}
          onChange={changeFilter(setConsent)}
        />
        <div className={styles.filterGroup}>
          <span>{t("outcomeLabel")}</span>
          <SearchableCheckboxPicker
            icon="tune"
            value={statusOutcomes}
            onChange={(next) => changeFilter(setStatusOutcomes)(next.length === outcomes.length ? [] : next)}
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
      <div className={styles.toolbar}>
        {picked.length > 0 && <span aria-live="polite">{t("selectedCount", { count: picked.length })}</span>}
        <TraceDeleteButton
          mode="selected"
          sessionIds={picked}
          disabled={catalog.isFetching || queryUpdating}
          onDeleted={clearPick}
        />
        <TraceExportButton sessionIds={picked} disabled={catalog.isFetching || queryUpdating} />
        <Button
          type="button"
          color="secondary"
          size="small"
          variant="text"
          disabled={catalog.isFetching || queryUpdating}
          onClick={() => void catalog.refetch()}
        >
          {t("refresh")}
        </Button>
      </div>
      {catalogRestarted && !pager.cursor && <p role="status">{t("catalogRestarted")}</p>}
      {catalog.isError && !staleCursor ? (
        <p role="alert" className={styles.error}>
          {t("listError")}
        </p>
      ) : rows.length > 0 ? (
        <div className={styles.table}>
          <LocalizedDataTable
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
              setSort(field && next ? { field, direction: next.direction } : { field: "latest", direction: "desc" });
              clearPick();
            }}
          />
        </div>
      ) : catalog.isFetching || queryUpdating ? (
        <p className={styles.empty} role="status">
          {t("loading")}
        </p>
      ) : (
        <PageEmptyState message={t("noMatches")} icon="search" />
      )}
      <TracePageButtons
        pager={pager}
        nextCursor={catalog.currentData?.next_cursor ?? null}
        disabled={catalog.isFetching || queryUpdating || Boolean(staleCursor)}
      />
    </div>
  );
}
