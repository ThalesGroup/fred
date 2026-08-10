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

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
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
  const open = doc !== null;

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!doc) return null;

  const errors = Object.entries(doc.processing?.errors ?? {});

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="ingestion-error-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <p id="ingestion-error-title" className={styles.title}>
                {t("rework.resources.errorModal.title")}
              </p>
              <IconButton
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={onClose}
              />
            </div>

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
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("common.close")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
