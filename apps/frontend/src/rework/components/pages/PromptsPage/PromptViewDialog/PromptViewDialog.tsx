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
import { useTranslation } from "react-i18next";
import {
  type PromptCategorySummary,
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptViewDialog.module.scss";

interface PromptViewDialogProps {
  open: boolean;
  teamId: string;
  promptId: string | null;
  categories: PromptCategorySummary[];
  onClose: () => void;
}

/** Read-only view of one prompt, reached by clicking a `PromptCard` — editing
 * stays reachable only through the card's hover-edit icon (PROMPT-09 follow-up). */
export default function PromptViewDialog({ open, teamId, promptId, categories, onClose }: PromptViewDialogProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const [copied, setCopied] = useState(false);

  const { data: rawDetail } = useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
    { teamId, promptId: promptId || "" },
    { skip: !open || !promptId },
  );
  // RTK Query's `data` keeps returning the *previous* successful result (same
  // object reference) for a moment after `promptId` changes, before the new
  // fetch resolves — same root cause as issue #1996 in the edit form. Without
  // this guard, opening prompt B right after prompt A briefly (or, on a slow
  // network, not-so-briefly) renders A's name/category/text under B's dialog.
  const detail = rawDetail && rawDetail.id === promptId ? rawDetail : undefined;

  useEffect(() => {
    setCopied(false);
  }, [open, promptId]);

  const category = categories.find((c) => c.id === detail?.category_id);

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
        {!detail ? (
          <div className={styles.loading}>
            <Spinner size={20} />
          </div>
        ) : (
          <>
            <div className={styles.header}>
              <span className={styles.title}>{detail.name}</span>
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

            {detail.description && <p className={styles.description}>{detail.description}</p>}

            <span className={styles.categoryChip}>
              {category ? category.name : t("rework.promptCategories.noCategory")}
            </span>

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
