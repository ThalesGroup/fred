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

import Button from "@shared/atoms/Button/Button.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import DocumentNameCell from "@shared/molecules/DocumentNameCell/DocumentNameCell.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useKnowledgeBaseQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import {
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  type DocumentMetadata,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { formatDateTime } from "../../../utils/formatDateTime.ts";
import styles from "./KnowledgeBaseDocumentsPage.module.css";

const PAGE_SIZE = 25;

/** What one Knowledge Base has put in its library, and nothing else.
 *
 * Read only by design, not by omission: these documents belong to a source the
 * base mirrors, so removing one here would only last until the next run. The
 * way to stop taking them is to delete the base, from the list this page came
 * from.
 */
export default function KnowledgeBaseDocumentsPage() {
  const { teamId, instanceId } = useParams<{ teamId: string; instanceId: string }>();
  const { t } = useTranslation();

  const {
    data: instance,
    isLoading: isLoadingInstance,
    isError: instanceError,
  } = useKnowledgeBaseQuery({ instanceId: instanceId ?? "" }, { skip: !instanceId });

  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [documentsError, setDocumentsError] = useState(false);

  const libraryId = instance?.library_id;

  const loadPage = useCallback(
    async (tagId: string, from: number) => {
      setIsLoadingDocuments(true);
      setDocumentsError(false);
      try {
        const page = await browseDocumentsByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset: from, limit: PAGE_SIZE },
        }).unwrap();
        setDocuments(page.documents ?? []);
        setTotal(page.total ?? 0);
      } catch {
        setDocumentsError(true);
        setDocuments([]);
        setTotal(0);
      } finally {
        setIsLoadingDocuments(false);
      }
    },
    [browseDocumentsByTag],
  );

  useEffect(() => {
    if (libraryId) void loadPage(libraryId, offset);
  }, [libraryId, offset, loadPage]);

  // The same columns a team's resources show, minus the ones that act: this is
  // the same object, so it is read the same way.
  const columns: DataTableColumn<DocumentMetadata>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "2fr",
      cellRenderer: (doc) => <DocumentNameCell doc={doc} />,
    },
    {
      label: t("rework.resources.columns.size"),
      size: "6.5rem",
      cellRenderer: (doc) => <span className={styles.nowrapCell}>{formatBytes(doc.file?.file_size_bytes ?? 0)}</span>,
    },
    {
      label: t("rework.resources.columns.created"),
      size: "9rem",
      cellRenderer: (doc) => <span className={styles.nowrapCell}>{formatDateTime(doc.source.date_added_to_kb)}</span>,
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Link to={`/team/${teamId}/knowledge-bases`} className={styles.back}>
          <Button
            color="on-surface-retreat"
            variant="text"
            size="medium"
            icon={{ category: "outlined", type: "arrow_back" }}
          >
            {t("rework.knowledgeBases.documents.back")}
          </Button>
        </Link>
        <span className={styles.title}>{instance?.library_name ?? ""}</span>
        {instance && <span className={styles.kind}>{instance.definition_name}</span>}
      </div>

      {isLoadingInstance ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
        </div>
      ) : instanceError || !instance ? (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.knowledgeBases.documents.unavailable.title")}
          description={t("rework.knowledgeBases.documents.unavailable.description")}
          centered
        />
      ) : documentsError ? (
        <ServiceNotice icon="cloud_off" title={t("rework.knowledgeBases.documents.loadFailed")} centered />
      ) : isLoadingDocuments && !documents.length ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
        </div>
      ) : !total ? (
        <ServiceNotice icon="database" title={t("rework.knowledgeBases.documents.empty")} centered />
      ) : (
        <div className={styles.table}>
          <DataTable<DocumentMetadata>
            columns={columns}
            data={documents}
            rowKey={(doc) => doc.identity.document_uid}
            serverPagination={{ totalCount: total, offset, limit: PAGE_SIZE, onOffsetChange: setOffset }}
          />
        </div>
      )}
    </div>
  );
}
