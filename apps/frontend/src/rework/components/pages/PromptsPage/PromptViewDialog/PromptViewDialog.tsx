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

/** Minimal prompt shape the read-only view can render without a team fetch. */
export interface PromptViewDetail {
  id: string;
  name: string;
  description?: string | null;
  text: string;
  category_id?: string | null;
}

interface PromptViewDialogProps {
  open: boolean;
  onClose: () => void;
  /** team variant: fetches the prompt detail for this team. */
  teamId?: string;
  promptId?: string | null;
  categories?: PromptCategorySummary[];
  /**
   * Marketplace variant: the prompt is already loaded (the caller may not be a
   * member of the author team, so the team fetch would 403). When set, the
   * dialog renders this directly and skips the query.
   */
  preloadedDetail?: PromptViewDetail | null;
  /** Overrides the chip label (e.g. the author team name on the marketplace). */
  chipLabel?: string | null;
  /** Fired after a successful clipboard copy, so the caller can record a use. */
  onCopied?: () => void;
}

/** Read-only view of one prompt, reached by clicking a `PromptCard`. Editing
 * stays reachable only through the card's more-menu (team library); on the
 * marketplace the only action is copy-to-clipboard. */
export default function PromptViewDialog({
  open,
  teamId,
  promptId,
  categories = [],
  preloadedDetail,
  chipLabel,
  onCopied,
  onClose,
}: PromptViewDialogProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();
  const [copied, setCopied] = useState(false);

  const { data: rawDetail } = useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
    { teamId: teamId || "", promptId: promptId || "" },
    { skip: !open || !promptId || !teamId || !!preloadedDetail },
  );
  // RTK Query's `data` keeps returning the *previous* successful result (same
  // object reference) for a moment after `promptId` changes, before the new
  // fetch resolves — same root cause as issue #1996 in the edit form. Without
  // this guard, opening prompt B right after prompt A briefly (or, on a slow
  // network, not-so-briefly) renders A's name/category/text under B's dialog.
  const fetched = rawDetail && rawDetail.id === promptId ? rawDetail : undefined;
  const detail: PromptViewDetail | undefined = preloadedDetail ?? fetched;

  useEffect(() => {
    setCopied(false);
  }, [open, promptId, preloadedDetail?.id]);

  const category = categories.find((c) => c.id === detail?.category_id);
  const resolvedChipLabel =
    chipLabel !== undefined ? chipLabel : (category?.name ?? t("rework.promptCategories.noCategory"));

  const handleCopy = () => {
    if (!detail) return;
    writeRichClipboard("", detail.text).then((ok) => {
      if (ok) {
        setCopied(true);
        showSuccess({ summary: t("rework.teams.prompts.view.copiedToast"), duration: 2000 });
        setTimeout(() => setCopied(false), 2000);
        onCopied?.();
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
