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
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./IngestionErrorModal.module.css";

interface IngestionErrorModalProps {
  /** Document whose ingestion errors are shown; null keeps the modal closed. */
  doc: DocumentMetadata | null;
  onClose: () => void;
}

/**
 * Read-only detail of a failed ingestion (#2315): lists each failed pipeline
 * stage with the error message the backend persisted in `processing.errors`
 * (`mark_stage_error`, document_structures.py). The data is already in the
 * browse response every row renders from — this modal only surfaces it.
 * Stage keys are shown as-is: they are backend pipeline identifiers
 * (preview/vector/sql/…), useful verbatim in a support ticket.
 */
export default function IngestionErrorModal({ doc, onClose }: IngestionErrorModalProps) {
  const { t } = useTranslation();
  if (!doc) return null;

  const errors = Object.entries(doc.processing?.errors ?? {});

  return (
    <Dialog
      open
      title={t("rework.resources.errorModal.title")}
      confirmLabel={t("common.close")}
      onConfirm={onClose}
      onCancel={onClose}
      hideCancel
    >
      <p className={styles.documentName}>{doc.identity.document_name}</p>
      {errors.length === 0 ? (
        <p className={styles.empty}>{t("rework.resources.errorModal.empty")}</p>
      ) : (
        <dl className={styles.errorList}>
          {errors.map(([stage, message]) => (
            <div key={stage} className={styles.errorEntry}>
              <dt className={styles.stage}>{stage}</dt>
              <dd className={styles.message}>{message}</dd>
            </div>
          ))}
        </dl>
      )}
    </Dialog>
  );
}
