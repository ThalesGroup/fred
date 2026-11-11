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

import { useTranslation } from "react-i18next";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable";
import { InfoHint } from "./AnalyticsSection";
import styles from "./AnalyticsPage.module.css";

interface AnalyticsTableProps<T> {
  /** Names the table's keys under `rework.analytics.tables`: title, def, how, empty. */
  id: string;
  columns: DataTableColumn<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  isLoading: boolean;
  isError: boolean;
  /** Replaces the empty message, e.g. when the data is not attached to teams. */
  emptyMessage?: string;
  /** Leaves the title to the section heading; it still names the table for assistive tech. */
  hideTitle?: boolean;
}

/** The info icon of an untitled table, for its section heading (`aside`). */
export function TableHint({ id }: { id: string }) {
  const { t } = useTranslation();
  const key = `rework.analytics.tables.${id}`;
  return <InfoHint label={t(`${key}.title`)} def={t(`${key}.def`)} how={t(`${key}.how`)} />;
}

/** A titled table block of the analytics page, with its loading and empty states. */
export default function AnalyticsTable<T>({
  id,
  columns,
  rows,
  rowKey,
  isLoading,
  isError,
  emptyMessage,
  hideTitle = false,
}: AnalyticsTableProps<T>) {
  const { t } = useTranslation();
  const key = `rework.analytics.tables.${id}`;
  const title = t(`${key}.title`);
  const def = t(`${key}.def`, { defaultValue: "" });
  return (
    <section className={styles.tableBlock} aria-label={title}>
      {!hideTitle && (
        <div className={styles.blockHeader}>
          <h3 className={styles.blockTitle}>{title}</h3>
          {def && <InfoHint label={title} def={def} how={t(`${key}.how`, { defaultValue: "" }) || undefined} />}
        </div>
      )}
      {isError ? (
        <p role="alert" className={styles.note}>
          {t("common.loadingError")}
        </p>
      ) : isLoading ? (
        <p role="status" className={styles.note}>
          {t("common.loading")}
        </p>
      ) : !rows?.length ? (
        <p role="status" className={styles.note}>
          {emptyMessage ?? t(`${key}.empty`)}
        </p>
      ) : (
        <DataTable columns={columns} data={rows} rowKey={rowKey} size="small" />
      )}
    </section>
  );
}
