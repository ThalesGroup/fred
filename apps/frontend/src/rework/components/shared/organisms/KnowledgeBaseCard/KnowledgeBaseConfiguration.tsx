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
import { useKnowledgeBaseFieldsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { FieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./KnowledgeBaseConfiguration.module.css";

interface KnowledgeBaseConfigurationProps {
  definitionId: string;
  teamId: string;
  configuration: { [key: string]: unknown };
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** What a team filled in when it created this base, read only.
 *
 * Titles come from the definition's own declaration; several bases of the same
 * kind share one request for them. A secret-declared field is skipped outright:
 * the API strips its value, so the row could only ever be an empty promise.
 */
export default function KnowledgeBaseConfiguration({
  definitionId,
  teamId,
  configuration,
}: KnowledgeBaseConfigurationProps) {
  const { t } = useTranslation();
  const { data: fields } = useKnowledgeBaseFieldsQuery({ definitionId, teamId });

  const declared: FieldSpec[] = (fields?.configuration_fields ?? []).filter((field) => field.type !== "secret");
  const rows = declared.length
    ? declared.map((field) => ({ key: field.key, label: field.title, value: configuration[field.key] }))
    : Object.keys(configuration).map((key) => ({ key, label: key, value: configuration[key] }));

  if (!rows.length) return <>{t("rework.knowledgeBases.card.noConfiguration")}</>;

  return (
    <dl className={styles.configuration}>
      {rows.map((row) => (
        <div key={row.key} className={styles.row}>
          <dt className={styles.label}>{row.label}</dt>
          <dd className={styles.value} title={displayValue(row.value)}>
            {displayValue(row.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
