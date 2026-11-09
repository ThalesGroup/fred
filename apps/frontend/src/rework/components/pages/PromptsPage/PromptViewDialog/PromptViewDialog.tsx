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

import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { useEffect, useState } from "react";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useTranslation } from "react-i18next";
import { useGetPromptQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import Chip from "@shared/atoms/Chip/Chip";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import styles from "./PromptViewDialog.module.scss";

interface PromptViewDialogProps {
  open: boolean;
  onClose: () => void;
  spaceId?: string;
  promptId?: string | null;
  categories?: { id: string; name: string }[];
  chipLabel?: string | null;
}

/** Read-only view of one prompt, reached by clicking a `PromptCard`. Editing
 * stays reachable through the library card menu. */
export default function PromptViewDialog({
  open,
  spaceId,
  promptId,
  categories = [],
  chipLabel,
  onClose,
}: PromptViewDialogProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const [copied, setCopied] = useState(false);

  const weaver = useGetPromptQuery(
    { spaceId: spaceId ?? "", promptId: promptId ?? "" },
    {
      ...crossSessionRefreshOptions(!open || !spaceId || !promptId),
      refetchOnMountOrArgChange: true,
    },
  );
  useRefetchOnWindowFocus(weaver.refetch, !open || !spaceId || !promptId);
  const detail = spaceId && !weaver.isError && !weaver.isFetching ? weaver.currentData : undefined;
  const failed = weaver.isError;
  const name = detail?.display_name;
  const command = detail?.logical_name;

  useEffect(() => {
    setCopied(false);
  }, [open, promptId, spaceId]);

  const category = categories.find((category) => category.id === detail?.category_id);
  const resolvedChipLabel = chipLabel ?? category?.name ?? t("rework.promptCategories.noCategory");

  const handleCopy = () => {
    if (!detail) return;
    writeRichClipboard("", detail.text).then((ok) => {
      if (ok) {
        setCopied(true);
        showSuccess({ summary: t("rework.teams.prompts.view.copiedToast"), duration: 2000 });
        setTimeout(() => setCopied(false), 2000);
      }
    });
  };

  return (
    <FullPageModal isOpen={open} onClose={onClose} id="prompt-view-modal" background="scrim">
      <div className={styles.card}>
        <div className={styles.header}>
          <span id="prompt-view-modal-title" className={styles.title}>
            {name ?? t("chatbot.promptSelectionPanel.title")}
          </span>
        </div>
        <div className={styles.closeButton}>
          <IconButton
            size="medium"
            color="on-surface-retreat"
            variant="icon"
            icon={{ category: "outlined", type: "close" }}
            aria-label={t("rework.teams.prompts.view.closeAria")}
            onClick={onClose}
          />
        </div>
        {failed ? (
          <ServiceNotice icon="info" title={t("chatbot.commandTurn.previewError")} />
        ) : !detail ? (
          <div className={styles.loading}>
            <Spinner size={20} />
          </div>
        ) : (
          <>
            {(command || detail.description) && (
              <div className={styles.summary}>
                {command && <span className={styles.commandSlug}>/{command}</span>}
                {detail.description && <p className={styles.description}>{detail.description}</p>}
              </div>
            )}

            {"tags" in detail && detail.tags.length > 0 && (
              <div className={styles.tags} aria-label={t("rework.weaverPrompts.tags")}>
                {detail.tags.map((tag) => (
                  <Chip key={tag} label={tag} />
                ))}
              </div>
            )}
            {resolvedChipLabel && <span className={styles.categoryChip}>{resolvedChipLabel}</span>}

            <div className={styles.textSection}>
              <div className={styles.textHeader}>
                <span className={styles.textLabel}>{t("rework.teams.prompts.form.text")}</span>
                <IconButton
                  size="medium"
                  color="on-surface-retreat"
                  variant="icon"
                  icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
                  aria-label={t("rework.teams.prompts.view.copyAria")}
                  onClick={handleCopy}
                />
              </div>
              {/* A plain scrollable div, not a `textarea` — readOnly textareas
               *  can still be focused, clicked into, and have their text
               *  selected/dragged. This is meant to be pure display: scroll only,
               *  no focus ring, no cursor, no selection (the copy button above
               *  is the only way out). */}
              <div className={styles.textarea} tabIndex={-1}>
                {detail.text}
              </div>
            </div>
          </>
        )}
      </div>
    </FullPageModal>
  );
}
