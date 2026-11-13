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
import DataTable, { type DataTableColumn } from "../DataTable/LocalizedDataTable";
import styles from "./SkillUsageTable.module.css";

interface SkillUsageRow {
  skill_name: string;
  user_count: number | bigint;
  model_count: number | bigint;
  total: number | bigint;
}

interface Props {
  data?: { rows: SkillUsageRow[]; truncated?: boolean };
  agentLabel?: string;
  isLoading: boolean;
  isError: boolean;
}

export default function SkillUsageTable({ data, agentLabel, isLoading, isError }: Props) {
  const { t, i18n } = useTranslation();
  const columns: DataTableColumn<SkillUsageRow>[] = [
    {
      label: t("rework.analytics.skillUsage.skill"),
      size: "2fr",
      sortable: true,
      sortValue: (row) => row.skill_name,
      cellRenderer: (row) => row.skill_name,
    },
    ...(["user_count", "model_count", "total"] as const).map((key) => ({
      label: key === "model_count" && agentLabel ? agentLabel : t(`rework.analytics.skillUsage.${key}`),
      size: "1fr",
      sortable: true,
      sortValue: (row: SkillUsageRow) => String(row[key]).padStart(20, "0"),
      cellRenderer: (row: SkillUsageRow) => row[key].toLocaleString(i18n.language),
    })),
  ];
  return (
    <section className={styles.section} aria-label={t("rework.analytics.skillUsage.title")}>
      <h2 className={styles.title}>{t("rework.analytics.skillUsage.title")}</h2>
      <p className={styles.description}>{t("rework.analytics.skillUsage.description")}</p>
      {isError ? (
        <p role="alert">{t("common.loadingError")}</p>
      ) : isLoading ? (
        <p role="status">{t("common.loading")}</p>
      ) : !data?.rows.length ? (
        <p role="status">{t("rework.analytics.skillUsage.empty")}</p>
      ) : (
        <>
          <DataTable columns={columns} data={data.rows} rowKey={(row) => row.skill_name} size="small" pageSize={20} />
          {data.truncated && <p role="status">{t("rework.analytics.skillUsage.truncated")}</p>}
        </>
      )}
    </section>
  );
}
