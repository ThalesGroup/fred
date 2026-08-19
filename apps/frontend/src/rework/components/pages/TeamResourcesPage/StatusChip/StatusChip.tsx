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

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useCopyConfirmation } from "../../../../core/hooks/useCopyConfirmation";
import { writeRichClipboard } from "../../../../utils/clipboardUtils";
import styles from "./StatusChip.module.css";

/**
 * `DocStatus` plus the one state only a FOLDER row can be in (#2384): some
 * documents underneath it failed while the folder itself is neither processing
 * nor broken. Deliberately not added to `DocStatus` — no document is ever
 * "warning", and widening the shared type would push a meaningless case onto
 * every `DocStatusBadge` consumer.
 */
type ChipStatus = DocStatus | "warning";

/** How many failed documents the hover panel names before it summarizes the
 *  rest. The panel is portaled outside the chip, so moving the pointer toward
 *  it closes the tooltip — its scrollbar is unreachable, and an uncapped list
 *  (a 300-file batch that all failed) would be clipped with no way to read
 *  past the fold. */
const MAX_NAMED_FAILURES = 10;

interface StatusChipProps {
  status: ChipStatus;
  /** Per-stage messages from `processing.errors`; shown on hover when failed (#2315). */
  errors?: Record<string, string> | null;
  /** What the ingestion task itself reported when it died — the message the
   *  parent workflow extracted from the Temporal child job. A run that failed
   *  before any stage started stamps nothing in `processing.errors`, so without
   *  this the chip says "Erreur" and the panel has nothing to show. */
  taskError?: string | null;
  /** The ingestion succeeded during this browser session (its SSE task reached
   *  `succeeded`). Marks the otherwise-silent "ready" state with a success
   *  badge so a user who just launched uploads can spot what finished — on a
   *  folder row, that something under it finished and nothing under it is
   *  still running or failed. Session-only by design: the task feed lives in
   *  Redux memory, so a page refresh clears the marker without any timer or
   *  persistence. */
  justCompleted?: boolean;
  /** The failed documents a `warning` folder chip stands for. The chip counts
   *  them and names them on hover — a folder is only ever the sum of what is
   *  under it, so unlike `errors` (one document's pipeline stages) this panel
   *  answers "which files do I have to look at?". */
  failedDocuments?: { uid: string; name: string }[];
}

const ICON_SIZE = 12;

/**
 * Resources dashboard v2's status cell (RFC §13.3): silence for the common
 * "ready" case (no chip, not a green checkmark) — a chip only appears for a
 * state that needs the user's attention. Deliberately a new piece rather than
 * a `DocStatusBadge` prop toggle, so the existing always-visible dot+label
 * rendering used elsewhere is untouched.
 *
 * A failed chip carries its own explanation: hovering it lists each failed
 * pipeline stage with the message the backend persisted in `processing.errors`
 * (`mark_stage_error`, document_structures.py). The data is already in the
 * browse response every row renders from — no click, no menu entry, no modal.
 * Stage keys are shown as-is: they are backend pipeline identifiers
 * (preview/vector/sql/…), useful verbatim in a support ticket.
 */
export function StatusChip({ status, errors, justCompleted, failedDocuments, taskError }: StatusChipProps) {
  const { t } = useTranslation();
  // Folder rollup: the count is the label ("2 errors"), because restating
  // "Error" on a folder says nothing the row's own subtree doesn't already
  // imply — how many, and which ones, is the actionable part.
  if (status === "warning") {
    const failed = failedDocuments ?? [];
    if (failed.length === 0) return null;
    const named = failed.slice(0, MAX_NAMED_FAILURES);
    return (
      <DetailPanel
        title={t("rework.resources.status.folderFailedTooltip", { count: failed.length })}
        // Every name, not just the rendered ten: the point of copying is to get
        // the whole list out.
        copyText={failed.map((doc) => doc.name).join("\n")}
        chip={
          <span className={styles.chip} data-variant="warning">
            <Icon category="outlined" type="warning" />
            {t("rework.resources.status.folderFailed", { count: failed.length })}
          </span>
        }
      >
        <ul className={styles.failedList}>
          {named.map((doc) => (
            <li key={doc.uid}>{doc.name}</li>
          ))}
        </ul>
        {failed.length > named.length && (
          <span className={styles.failedTooltipMore}>
            {t("rework.resources.status.folderFailedMore", { count: failed.length - named.length })}
          </span>
        )}
      </DetailPanel>
    );
  }
  if (status === "ready") {
    if (!justCompleted) return null;
    return (
      <span className={styles.justDone}>
        <span className={styles.chip} data-variant="done">
          <Icon category="outlined" type="check_circle" />
          {t("rework.resources.status.justDone")}
        </span>
      </span>
    );
  }

  const variant = status === "raw" ? "pending" : status;
  const chip = (
    <span className={styles.chip} data-variant={variant}>
      {variant === "processing" ? (
        <Spinner size={ICON_SIZE} />
      ) : variant === "pending" ? (
        <span className={styles.breathingIcon}>
          <Icon category="outlined" type="sync" />
        </span>
      ) : (
        <Icon category="outlined" type="error_outline" />
      )}
      {t(`rework.resources.status.${status}`)}
    </span>
  );

  const errorEntries = status === "failed" ? Object.entries(errors ?? {}) : [];
  const reportedError = status === "failed" ? taskError?.trim() : undefined;
  // A stage message is more precise than the task's, so it is not repeated when
  // it already says the same thing.
  const showReportedError = reportedError && !errorEntries.some(([, message]) => message.trim() === reportedError);
  if (errorEntries.length === 0 && !showReportedError) return chip;

  const copyText = [
    ...errorEntries.map(([stage, message]) => `${stage}: ${message}`),
    ...(showReportedError ? [reportedError] : []),
  ].join("\n");

  return (
    <DetailPanel title={t("rework.resources.status.failed")} copyText={copyText} chip={chip}>
      {errorEntries.length > 0 && (
        <dl className={styles.errorTooltip}>
          {errorEntries.map(([stage, message]) => (
            <div key={stage} className={styles.errorEntry}>
              {/* The raw key alone ("preview", "vector") reads as jargon —
                  labelling it as a pipeline stage tells the user what failed. */}
              <dt className={styles.errorStage}>{t("rework.resources.errorTooltip.stage", { stage })}</dt>
              <dd className={styles.errorMessage}>{message}</dd>
            </div>
          ))}
        </dl>
      )}
      {showReportedError && (
        <div className={styles.errorEntry}>
          <span className={styles.errorStage}>{t("rework.resources.errorTooltip.reported")}</span>
          <span className={styles.errorMessage}>{reportedError}</span>
        </div>
      )}
    </DetailPanel>
  );
}

interface DetailPanelProps {
  chip: ReactNode;
  title: string;
  /** Plain text the copy button writes — the FULL detail, even where the panel
   *  truncates the rendered list: copying is exactly when the whole thing is
   *  wanted (a support ticket, a message to whoever uploaded the file). */
  copyText: string;
  children: ReactNode;
}

/**
 * A failure panel that opens on hover and can then be USED: the pointer can
 * travel into it, select the message, and hit copy.
 *
 * That is `Tooltip`'s `interactive` mode rather than a bespoke popover — the
 * atom already owns portalling, viewport clamping and the keyboard-focus path,
 * and every other hover panel in the app benefits from the same affordance
 * instead of this one growing its own. The clipboard write goes through
 * `writeRichClipboard`, which every copy site routes through (#2366), and the
 * receipt through `useCopyConfirmation`, the flip the chat turns share (#2359).
 */
function DetailPanel({ chip, title, copyText, children }: DetailPanelProps) {
  const { t } = useTranslation();
  const { copied, confirmCopied } = useCopyConfirmation();

  return (
    <Tooltip
      interactive
      content={
        <div className={styles.detailPanel}>
          <div className={styles.detailHeader}>
            <span className={styles.detailTitle}>{title}</span>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
              aria-label={copied ? t("rework.resources.status.detailCopied") : t("rework.resources.status.copyDetail")}
              onClick={() => {
                void writeRichClipboard("", copyText).then((ok) => {
                  if (ok) confirmCopied();
                });
              }}
            />
          </div>
          <div className={styles.detailBody}>{children}</div>
        </div>
      }
    >
      {chip}
    </Tooltip>
  );
}
