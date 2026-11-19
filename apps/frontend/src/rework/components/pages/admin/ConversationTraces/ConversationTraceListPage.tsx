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
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import LocalizedDataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  type ConversationTraceSummary,
  useListConversationTracesQuery,
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

export default function ConversationTraceListPage() {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [failedOnly, setFailedOnly] = useState(true);
  const [selected, setSelected] = useState<ReadonlySet<string | number>>(new Set());
  const pager = useTracePagination();
  const catalog = useListConversationTracesQuery(
    { failedOnly, cursor: pager.cursor },
    { refetchOnMountOrArgChange: true },
  );
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });
  const rows = catalog.currentData?.conversations ?? [];
  const picked = rows.map(({ session_id }) => session_id).filter((id) => selected.has(id));

  function refreshAfterDelete() {
    setSelected(new Set());
    pager.reset();
  }

  const columns: DataTableColumn<ConversationTraceSummary>[] = [
    {
      label: t("conversation"),
      size: "minmax(12rem, 2fr)",
      cellRenderer: (row) => (
        <div className={styles.conversationCell}>
          <Link className={styles.link} to={`${TRACE_LIST_PATH}/${encodeURIComponent(row.session_id)}`}>
            {t("maskedConversation")}
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
      label: t("status"),
      size: "minmax(6rem, 1fr)",
      cellRenderer: ({ outcome }) => <TraceOutcomeBadge outcome={outcome} />,
    },
    {
      label: t("availability"),
      size: "minmax(7rem, 1fr)",
      cellRenderer: ({ availability }) => t(`evidence.${availability}`),
    },
    {
      label: t("latestTurn"),
      size: "minmax(10rem, 1fr)",
      cellRenderer: (row) => (
        <time dateTime={row.latest_started_at}>{date.format(new Date(row.latest_started_at))}</time>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={t("title")} subtitle={t("catalogDescription")} />
      <ConversationTraceSettings onFlushed={refreshAfterDelete} />
      <div className={styles.toolbar}>
        <div className={styles.filters} role="group" aria-label={t("status")}>
          {[true, false].map((filter) => (
            <Button
              type="button"
              key={String(filter)}
              color="secondary"
              size="small"
              aria-pressed={filter === failedOnly}
              variant={filter === failedOnly ? "tonal" : "text"}
              onClick={() => {
                setFailedOnly(filter);
                pager.reset();
                setSelected(new Set());
              }}
            >
              {filter ? t("outcome.failed") : t("all")}
            </Button>
          ))}
        </div>
        {picked.length > 0 && <span aria-live="polite">{t("selectedCount", { count: picked.length })}</span>}
        <TraceDeleteButton
          mode="selected"
          sessionIds={picked}
          disabled={catalog.isFetching}
          onDeleted={refreshAfterDelete}
        />
        <Button
          type="button"
          color="secondary"
          size="small"
          variant="text"
          disabled={catalog.isFetching}
          onClick={() => {
            void catalog.refetch();
          }}
        >
          {t("refresh")}
        </Button>
      </div>
      {catalog.isError ? (
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
          />
        </div>
      ) : (
        <p className={styles.empty} role="status">
          {catalog.isFetching ? t("loading") : failedOnly ? t("noFailures") : t("noCaptures")}
        </p>
      )}
      <TracePageButtons
        pager={pager}
        nextCursor={catalog.currentData?.next_cursor ?? null}
        disabled={catalog.isFetching}
      />
    </div>
  );
}
