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

// The pane's "Rédaction" tab: the session's document as its parts,
// edited in place. Each
// action is one batch `{base_seq: view.seq, operations}`; the returned view
// replaces the shown one and the PDF preview is refreshed. A stale batch
// (409) reloads the view; a refused one (422) lists its problems on top.

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import type { ContentOperation } from "./api/wordTemplateCapabilityOpenApi";
import { wordTemplateErrorKind } from "./sessionDocument";
import { useWordTemplateContent } from "./useWordTemplateContent";
import { WordTemplateParts } from "./WordTemplateBlocks";
import styles from "./WordTemplateEditor.module.css";

interface WordTemplateEditorProps {
  sessionId: string;
  /** The session poll's version key (null = no document yet). */
  versionKey: string | null;
  /** Re-read the session state (refreshes the preview). */
  refreshSession: () => void;
}

export function WordTemplateEditor({ sessionId, versionKey, refreshSession }: WordTemplateEditorProps) {
  const { t } = useTranslation();
  const { showInfo, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const onStale = useCallback(() => showInfo({ summary: t("capability.word_template.editor.stale") }), [showInfo, t]);
  const onFailure = useCallback(
    (message: string) => showError({ summary: t("capability.word_template.editor.saveError"), detail: message }),
    [showError, t],
  );

  const { view, isLoading, loadError, isSaving, apply, undo, rejection, dismissRejection } = useWordTemplateContent({
    sessionId,
    versionKey,
    onChanged: refreshSession,
    onStale,
    onFailure,
  });

  const confirmRemove = useCallback(
    (operation: ContentOperation, message: string) =>
      showConfirmationDialog({
        title: t("capability.word_template.editor.confirmRemoveTitle"),
        message,
        confirmButtonLabel: t("capability.word_template.editor.remove"),
        cancelButtonLabel: t("capability.word_template.editor.cancel"),
        criticalAction: true,
        onConfirm: () => void apply([operation]),
      }),
    [showConfirmationDialog, apply, t],
  );

  if (versionKey === null) {
    return <div className={styles.empty}>{t("capability.word_template.preview.empty")}</div>;
  }
  if (!view) {
    if (loadError) {
      const { status, data } = loadError as { status?: number; data?: { detail?: unknown } };
      const detail = typeof data?.detail === "string" ? data.detail : undefined;
      return (
        <div className={styles.error}>
          {t(`capability.word_template.preview.error.${wordTemplateErrorKind({ status, detail })}`)}
        </div>
      );
    }
    return <div className={styles.empty}>{t("capability.word_template.editor.loading")}</div>;
  }

  const parts = view.parts ?? [];
  return (
    <div className={styles.editor}>
      <div className={styles.toolbar}>
        <Button
          color="on-surface"
          variant="text"
          size="small"
          icon={{ category: "outlined", type: "history" }}
          disabled={isSaving || view.seq === 0}
          onClick={() => void undo()}
        >
          {t("capability.word_template.editor.undo")}
        </Button>
        <span className={styles.status} aria-live="polite">
          {isSaving
            ? t("capability.word_template.editor.saving")
            : isLoading
              ? t("capability.word_template.preview.refreshing")
              : null}
        </span>
      </div>

      {rejection && (
        <div className={styles.rejection} role="alert">
          <div className={styles.rejectionHead}>
            <span>{t("capability.word_template.editor.rejected")}</span>
            <IconButton
              color="on-surface"
              variant="icon"
              size="2xs"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("capability.word_template.editor.dismiss")}
              onClick={dismissRejection}
            />
          </div>
          {rejection.problems.length > 0 && (
            <ul className={styles.problems}>
              {rejection.problems.map((problem, i) => (
                <li key={i}>{problem}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className={styles.scroll}>
        {parts.length === 0 ? (
          <div className={styles.empty}>{t("capability.word_template.editor.nothingToEdit")}</div>
        ) : (
          <WordTemplateParts parts={parts} apply={apply} confirmRemove={confirmRemove} busy={isSaving} />
        )}
      </div>
    </div>
  );
}
