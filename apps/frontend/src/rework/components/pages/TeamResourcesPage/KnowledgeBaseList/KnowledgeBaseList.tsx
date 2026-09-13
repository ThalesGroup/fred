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
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import type { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { FOLDER_ICON } from "../../../../utils/fileIconSpec.ts";
import type { KnowledgeBaseInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./KnowledgeBaseList.module.css";

/** Which knowledge base a row opens. */
export type KnowledgeBaseChoice = { kind: "native" } | { kind: "contributed"; libraryId: string };

interface KnowledgeBaseListProps {
  /** The knowledge bases a contributor fills for this team. */
  instances: readonly KnowledgeBaseInstanceSummary[];
  onOpen: (choice: KnowledgeBaseChoice) => void;
}

type Row = { kind: "native" } | { kind: "contributed"; instance: KnowledgeBaseInstanceSummary };

/**
 * The team's knowledge bases, one level above the folders. Fred's own is the
 * team corpus minus every contributed library; each contributed library is a
 * base of its own, badged with the name its contributor declared.
 *
 * No mapping from a contributor's identifier to anything this file knows: the
 * badge renders `definition_name` straight from the data, and every row gets
 * the same icon. The next contributor publishes something nobody here has
 * heard of, and it still reads correctly.
 */
export default function KnowledgeBaseList({ instances, onOpen }: KnowledgeBaseListProps) {
  const { t } = useTranslation();

  const rows: Row[] = [
    { kind: "native" },
    ...[...instances]
      .sort((a, b) => a.library_name.localeCompare(b.library_name))
      .map((instance): Row => ({ kind: "contributed", instance })),
  ];

  const rowName = (row: Row) =>
    row.kind === "native" ? t("rework.resources.knowledgeBases.nativeName") : row.instance.library_name;

  const columns: DataTableColumn<Row>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "2fr",
      cellRenderer: (row) => {
        const name = rowName(row);
        return (
          <button
            type="button"
            className={styles.nameButton}
            aria-label={t("rework.resources.knowledgeBases.open", { name })}
            onClick={() =>
              onOpen(
                row.kind === "native"
                  ? { kind: "native" }
                  : { kind: "contributed", libraryId: row.instance.library_id },
              )
            }
          >
            <span className={styles.rowIcon} aria-hidden>
              <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
            </span>
            <span className={styles.name}>{name}</span>
          </button>
        );
      },
    },
    {
      // Both badges answer one question — where do these documents come from.
      // "Dépôt manuel" is Fred's own answer to it, so it is a translated
      // constant; a contributed base answers with the name it declared.
      label: t("rework.resources.knowledgeBases.origin"),
      size: "12rem",
      cellRenderer: (row) => (
        <Chip
          label={
            row.kind === "native" ? t("rework.resources.knowledgeBases.manualDeposit") : row.instance.definition_name
          }
        />
      ),
    },
    {
      label: t("rework.resources.knowledgeBases.access"),
      size: "9rem",
      cellRenderer: (row) =>
        row.kind === "contributed" ? (
          <span className={styles.access}>{t("rework.resources.knowledgeBases.readOnly")}</span>
        ) : null,
    },
  ];

  return (
    <ResourceExplorer<Row>
      breadcrumb={{
        segments: [{ label: t("rework.resources.knowledgeBases.title") }],
        onBack: () => {},
        canGoBack: false,
        backLabel: t("rework.resources.action.back"),
      }}
      columns={columns}
      rows={rows}
      rowKey={(row) => (row.kind === "native" ? "native" : row.instance.id)}
      selectable={false}
    />
  );
}
