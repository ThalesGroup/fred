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

import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Switch from "@shared/atoms/Switch/Switch";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import LocalizedDataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import {
  type ConversationTraceSummary,
  useGetConversationTraceSettingsQuery,
  useListConversationTracesQuery,
  useSetConversationTraceSettingsMutation,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  TRACE_LIST_PATH,
  TRACE_TRANSLATION_PREFIX,
  TraceOutcomeBadge,
  TracePageButtons,
  useTracePagination,
} from "./traceControls";
import styles from "./ConversationTraces.module.css";

export default function ConversationTraceListPage() {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [failedOnly, setFailedOnly] = useState(true);
  const [settingsError, setSettingsError] = useState(false);
  const switchHelp = useId();
  const pager = useTracePagination();
  const settings = useGetConversationTraceSettingsQuery(undefined, { refetchOnMountOrArgChange: true });
  const [setCapture, update] = useSetConversationTraceSettingsMutation();
  const catalog = useListConversationTracesQuery(
    { failedOnly, cursor: pager.cursor },
    { refetchOnMountOrArgChange: true },
  );
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });
  const rows = catalog.currentData?.conversations ?? [];

  async function changeCapture(enabled: boolean) {
    setSettingsError(false);
    try {
      await setCapture({ conversationTraceSettings: { enabled } }).unwrap();
      await settings.refetch().unwrap();
    } catch {
      setSettingsError(true);
    }
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
      <section className={styles.captureSettings} aria-label={t("captureSettings")}>
        <div>
          <h2>{t("captureSettings")}</h2>
          <p id={switchHelp}>{t("captureHelp")}</p>
          {settings.isError && (
            <p role="alert" className={styles.error}>
              {t("settingsLoadError")}
            </p>
          )}
          {settingsError && (
            <p role="alert" className={styles.error}>
              {t("settingsSaveError")}
            </p>
          )}
        </div>
        <Switch
          role="switch"
          aria-label={t("captureSettings")}
          aria-describedby={switchHelp}
          checked={settings.data?.enabled ?? false}
          disabled={!settings.data || settings.isFetching || update.isLoading}
          onChange={(event) => void changeCapture(event.currentTarget.checked)}
        />
      </section>
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
              }}
            >
              {filter ? t("outcome.failed") : t("all")}
            </Button>
          ))}
        </div>
        <Button
          type="button"
          color="secondary"
          size="small"
          variant="text"
          disabled={catalog.isFetching}
          onClick={() => {
            void catalog.refetch();
            void settings.refetch();
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
          <LocalizedDataTable data={rows} columns={columns} rowKey={(row) => row.session_id} />
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
