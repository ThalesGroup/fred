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

// Admin Corpus Audit page (#2112). Surfaces the platform-admin-only document
// store audit (knowledge-flow-backend `MetadataService.audit_stores`), which
// compares each document's Postgres processing-stage claims against what is
// actually present in the content store and the vector store, and lets an
// admin fix the anomalies found (`fix_store_anomalies` — deletes orphan
// vector/content data, so it is gated behind a confirmation). Consumes only
// the generated knowledge-flow hooks — no hand-written fetch or response
// types (there is no knowledge-flow "enhancements" file to alias through,
// unlike control-plane, so the generated hook names are used directly).

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAuditDocumentsKnowledgeFlowV1DocumentsAuditGetQuery,
  useFixDocumentsKnowledgeFlowV1DocumentsAuditFixPostMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { StoreAuditFinding } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./CorpusAuditPage.module.css";

function PresenceIcon({ present }: { present: boolean }) {
  return (
    <div className={styles.centered}>
      <span className={present ? styles.present : styles.absent}>
        <Icon category="outlined" type={present ? "check_circle" : "close"} />
      </span>
    </div>
  );
}

export default function CorpusAuditPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();

  const { data, isLoading, isFetching, isError, refetch } = useAuditDocumentsKnowledgeFlowV1DocumentsAuditGetQuery();
  const [fixAnomalies, { isLoading: isFixing }] = useFixDocumentsKnowledgeFlowV1DocumentsAuditFixPostMutation();

  const [showFixConfirm, setShowFixConfirm] = useState(false);

  const anomalies = data?.anomalies ?? [];
  const hasAnomalies = data?.has_anomalies ?? false;
  // "Fix" only ever repairs missing_content/missing_vectors (resets a lying
  // stage flag) — it never touches orphan_vectors/orphan_content, which stay
  // reported for a human to delete by hand or investigate. Disable the
  // button when there's nothing it would actually do, so it's never a no-op
  // click on an orphan-only anomaly set.
  const hasRepairableAnomalies = anomalies.some((finding) =>
    (finding.issues ?? []).some((issue) => issue === "missing_content" || issue === "missing_vectors"),
  );

  const handleFixConfirmed = async () => {
    setShowFixConfirm(false);
    try {
      const result = await fixAnomalies().unwrap();
      const resetCount = result.reset_metadata?.length ?? 0;
      showSuccess({
        summary: t("rework.admin.corpusAudit.fixSuccess", { count: resetCount }),
      });
      // The fix mutation isn't tagged against the audit query (no shared RTK
      // Query tag between the two endpoints), so the table won't refresh on
      // its own — refetch explicitly, same pattern as MigrationPage's
      // post-task stats refresh.
      void refetch();
    } catch {
      showError({ summary: t("rework.admin.corpusAudit.fixError") });
    }
  };

  const columns: DataTableColumn<StoreAuditFinding>[] = [
    {
      label: t("rework.admin.corpusAudit.col.document"),
      size: "2fr",
      cellRenderer: (finding) => (
        <div className={styles.docCell}>
          <span className={styles.docName} title={finding.document_name ?? finding.document_uid}>
            {finding.document_name ?? finding.document_uid}
          </span>
          <span className={styles.docUid}>{finding.document_uid}</span>
        </div>
      ),
    },
    {
      label: t("rework.admin.corpusAudit.col.sourceTag"),
      size: "1fr",
      cellRenderer: (finding) => finding.source_tag ?? "—",
    },
    {
      label: t("rework.admin.corpusAudit.col.metadata"),
      cellRenderer: (finding) => <PresenceIcon present={finding.present_in_metadata} />,
    },
    {
      label: t("rework.admin.corpusAudit.col.vectorStore"),
      cellRenderer: (finding) => <PresenceIcon present={finding.present_in_vector_store} />,
    },
    {
      label: t("rework.admin.corpusAudit.col.contentStore"),
      cellRenderer: (finding) => <PresenceIcon present={finding.present_in_content_store} />,
    },
    {
      label: t("rework.admin.corpusAudit.col.vectorChunks"),
      cellRenderer: (finding) => finding.vector_chunks ?? "—",
    },
    {
      label: t("rework.admin.corpusAudit.col.issues"),
      size: "2fr",
      cellRenderer: (finding) => <span className={styles.issues}>{(finding.issues ?? []).join(", ") || "—"}</span>,
    },
  ];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.admin.corpusAudit.title")}</h1>
          <p className={styles.subtitle}>{t("rework.admin.corpusAudit.subtitle")}</p>
        </div>
        <div className={styles.headerActions}>
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh", filled: false }}
            onClick={() => void refetch()}
            disabled={isLoading || isFetching}
            title={t("rework.admin.corpusAudit.refresh")}
          />
          <Button
            color="error"
            variant="outlined"
            size="medium"
            icon={{ category: "outlined", type: "build" }}
            onClick={() => setShowFixConfirm(true)}
            disabled={isLoading || isFetching || isFixing || !hasRepairableAnomalies}
          >
            {isFixing ? t("rework.admin.corpusAudit.fixing") : t("rework.admin.corpusAudit.fix")}
          </Button>
        </div>
      </header>

      {isLoading && <p className={styles.status}>{t("rework.admin.corpusAudit.loading")}</p>}
      {isError && <p className={styles.statusError}>{t("rework.admin.corpusAudit.loadError")}</p>}

      {!isLoading && !isError && data && (
        <>
          <div className={styles.kpiGrid}>
            <KpiStatCard
              label={t("rework.admin.corpusAudit.stats.metadata")}
              value={data.metadata_count}
              isLoading={false}
              isError={false}
            />
            <KpiStatCard
              label={t("rework.admin.corpusAudit.stats.vectors")}
              value={data.vector_count}
              isLoading={false}
              isError={false}
            />
            <KpiStatCard
              label={t("rework.admin.corpusAudit.stats.content")}
              value={data.content_count}
              isLoading={false}
              isError={false}
            />
          </div>

          <div className={styles.banner} data-severity={hasAnomalies ? "warning" : "success"} role="status">
            <span className={styles.bannerIcon} aria-hidden>
              <Icon category="outlined" type={hasAnomalies ? "warning" : "check_circle"} />
            </span>
            <span>
              {hasAnomalies
                ? t("rework.admin.corpusAudit.anomaliesFound", { count: anomalies.length })
                : t("rework.admin.corpusAudit.noAnomalies")}
            </span>
          </div>

          {anomalies.length === 0 ? (
            <PageEmptyState icon="check_circle" message={t("rework.admin.corpusAudit.empty")} />
          ) : (
            <DataTable columns={columns} data={anomalies} />
          )}
        </>
      )}

      <ConfirmationDialog
        open={showFixConfirm}
        title={t("rework.admin.corpusAudit.fixConfirm.title")}
        message={t("rework.admin.corpusAudit.fixConfirm.message")}
        confirmLabel={t("rework.admin.corpusAudit.fixConfirm.confirm")}
        cancelLabel={t("rework.admin.corpusAudit.fixConfirm.cancel")}
        criticalAction
        onConfirm={() => void handleFixConfirmed()}
        onCancel={() => setShowFixConfirm(false)}
      />
    </div>
  );
}
