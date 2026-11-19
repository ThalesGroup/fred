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
import Chip from "@shared/atoms/Chip/Chip";
import Icon, { type IconProps } from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import LocalizedDataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
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
  useGetConversationTraceSettingsQuery,
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
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "medium" });
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
        <Link className={styles.conversationLink} to={`${TRACE_LIST_PATH}/${encodeURIComponent(row.session_id)}`}>
          <strong>{row.title || t("maskedConversation")}</strong>
          <span>{row.agent_display_name}</span>
        </Link>
      ),
    },
    {
      label: sortLabels.user,
      size: "minmax(6.5rem, 1fr)",
      sortable: true,
      cellRenderer: (row) => row.username || row.user_id || t("unavailable"),
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
        <div className={styles.catalogMetadata}>
          <TraceOutcomeBadge outcome={row.failure_category ?? row.outcome} />
          {row.availability === "history_only" && row.support_error_ref && (
            <TraceIdentifier label={t("supportErrorRef")} value={row.support_error_ref} />
          )}
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
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        subtitle={t("catalogDescription")}
        actions={
          <div className={styles.chips}>
            {capture && (
              <Chip
                label={t(capture.enabled ? "captureOn" : "captureOff")}
                tone={capture.enabled ? "success" : "default"}
              />
            )}
            {capture?.degradation_reason && (
              <Chip label={t(`degradation.${capture.degradation_reason}`)} tone="error" />
            )}
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
        }
      />
      {settingsOpen && (
        <ConversationTraceSettings settings={settings} onClose={() => setSettingsOpen(false)} onFlushed={clearPick} />
      )}
      <div className={styles.filters} role="group" aria-label={t("filtersLabel")}>
        <div className={styles.primaryFilters}>
          <TextInput
            label={t("searchLabel")}
            size="medium"
            type="search"
            compact
            maxLength={255}
            showCharacterCount={false}
            placeholder={t("searchPlaceholder")}
            icon={{ category: "outlined", type: "search" }}
            value={queryInput}
            onChange={(event) => setQueryInput(event.currentTarget.value)}
          />
          <TextInput
            label={t("user")}
            size="medium"
            type="search"
            compact
            maxLength={255}
            showCharacterCount={false}
            placeholder={t("userPlaceholder")}
            value={userInput}
            onChange={(event) => setUserInput(event.currentTarget.value)}
          />
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
        <div className={styles.secondaryFilters}>
          <TraceFilterButtons<QuickStatus>
            label={t("status")}
            value={status}
            options={[
              { value: "all", label: t("quickStatus.all") },
              { value: "completed", label: t("quickStatus.completed"), icon: "check" },
              { value: "failed", label: t("quickStatus.failed"), icon: "error" },
            ]}
            onChange={(key) => changeFilter(setStatusOutcomes)(quickOutcomes[key])}
          />
          <TraceFilterButtons<TraceConsentFilter>
            label={t("consentFilter")}
            value={consent}
            options={[
              { value: "all", label: t("consentOptions.all") },
              { value: "shared", label: t("consentOptions.shared"), icon: "check_circle" },
              { value: "masked", label: t("consentOptions.masked"), icon: "lock" },
            ]}
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
      </div>
      <div className={styles.tableSection}>
        <div className={styles.bulkActions}>
          <span aria-live="polite">
            {t(picked.length ? "selectedCount" : "pageCount", { count: picked.length || rows.length })}
          </span>
          <div className={styles.chips}>
            <TraceExportButton sessionIds={picked} disabled={catalog.isFetching || queryUpdating} />
            <TraceDeleteButton
              mode="selected"
              sessionIds={picked}
              disabled={catalog.isFetching || queryUpdating}
              onDeleted={clearPick}
            />
            <IconButton
              icon={{ category: "outlined", type: "refresh" }}
              variant="icon"
              size="small"
              aria-label={t("refresh")}
              title={t("refresh")}
              disabled={catalog.isFetching || queryUpdating}
              onClick={() => void catalog.refetch()}
            />
          </div>
        </div>
        {catalogRestarted && !pager.cursor && <p role="status">{t("catalogRestarted")}</p>}
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
    </div>
  );
}
