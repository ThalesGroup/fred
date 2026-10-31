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
} from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { useGetPromptQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import styles from "./PromptViewDialog.module.scss";

/** Minimal prompt shape the read-only view can render without a team fetch. */
export interface PromptViewDetail {
  id: string;
  name: string;
  description?: string | null;
  text: string;
  category_id?: string | null;
  /** Shown ahead of the description when set — in the team library and on the
   *  marketplace alike. On the marketplace it is the author team's command: an
   *  import into a team already holding it gets the first free `-N` suffix. */
  command?: string | null;
}

interface PromptViewDialogProps {
  open: boolean;
  onClose: () => void;
  /** team variant: fetches the prompt detail for this team. */
  teamId?: string;
  spaceId?: string;
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
  spaceId,
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

  const { currentData: rawDetail, isError: legacyError } =
    useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
      { teamId: teamId || "", promptId: promptId || "" },
      { skip: !!spaceId || !open || !promptId || !teamId || !!preloadedDetail },
    );
  // Keep the marketplace/home consumers on their own contract. Weaver never
  // converts its definition to a legacy DTO or starts the legacy query.
  const fetched = rawDetail && rawDetail.id === promptId ? rawDetail : undefined;
  const weaver = useGetPromptQuery(
    { spaceId: spaceId ?? "", promptId: promptId ?? "" },
    {
      skip: !open || !spaceId || !promptId,
      refetchOnMountOrArgChange: true,
    },
  );
  const detail = spaceId
    ? !weaver.isError && !weaver.isFetching
      ? weaver.currentData
      : undefined
    : (preloadedDetail ?? fetched);
  const failed = spaceId ? weaver.isError : legacyError;
  const name = detail && ("display_name" in detail ? detail.display_name : detail.name);
  const command = detail && ("logical_name" in detail ? detail.logical_name : detail.command);

  useEffect(() => {
    setCopied(false);
  }, [open, promptId, preloadedDetail?.id]);

  const category = categories.find(
    (c) => c.id === (detail && "category_id" in detail ? detail.category_id : undefined),
  );
  const resolvedChipLabel = spaceId
    ? null
    : chipLabel !== undefined
      ? chipLabel
      : (category?.name ?? t("rework.promptCategories.noCategory"));

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
