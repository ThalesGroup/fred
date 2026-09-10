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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { findReservedPromptTag } from "@rework/utils/promptValidation";
import {
  usePlatformInstructionsQuery,
  usePlatformPromptQuery,
  useSetPlatformPromptMutation,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformPromptPage.module.css";

// Mirrors `PLATFORM_PROMPT_MAX_CHARS` in the backend's
// `platform_prompt/schemas.py`. Kept visible next to the editor rather than only
// enforced on submit: this text is re-sent on every model call of every agent,
// so the cost of a long one should be apparent while typing.
const PLATFORM_PROMPT_MAX_CHARS = 20_000;

/**
 * The two platform-wide blocks every agent receives ahead of the tool rules
 * and its own instructions, shown side by side in the order the model reads
 * them: the read-only instructions the platform ships on the left, the global
 * prompt an admin owns on the right. An admin writing the right pane needs
 * the left one in view to know what is already covered and what outranks them.
 */
export default function PlatformPromptPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading } = usePlatformPromptQuery();
  const { data: instructions } = usePlatformInstructionsQuery();
  const [setPlatformPrompt, { isLoading: isSaving }] = useSetPlatformPromptMutation();

  // The row stores the acting user's Keycloak uid, not their name — a uid is
  // stable across renames and is the right thing to persist for audit. Resolve
  // it for display only; `userDisplayName` falls back to the raw uid.
  const auditUids = data?.updated_by ? [data.updated_by] : [];
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const [draft, setDraft] = useState("");
  const [serverError, setServerError] = useState<string | undefined>();
  // `data` arrives after the first render, and again after every save. Seeding
  // the draft from it on each arrival keeps the editor showing what is actually
  // stored, including the `updated_by`/`updated_at` the save echoes back.
  useEffect(() => {
    if (data) setDraft(data.text);
  }, [data]);

  // Both refusals mirror the backend's 422s so the admin sees them while
  // typing; the server's own wording is kept for anything that slips past.
  // Code points, not UTF-16 units: that is what the backend's cap counts.
  const reservedTag = findReservedPromptTag(draft);
  const draftLength = [...draft].length;
  const tooLong = draftLength > PLATFORM_PROMPT_MAX_CHARS;
  const clientError = reservedTag
    ? t("rework.promptEditor.reservedTag", { tag: reservedTag })
    : tooLong
      ? t("rework.platformPrompt.field.tooLong", { max: PLATFORM_PROMPT_MAX_CHARS })
      : undefined;

  // `is_default` (no row ever saved) must stay saveable even when the draft
  // still equals the empty `text` the API reports for it: saving "" from that
  // state is how an admin suppresses the block platform-wide, and it is a real
  // state change (`is_default` flips to false).
  const isDirty = data !== undefined && draft !== data.text;
  // Blocked while `source_unavailable`: the editor is showing "" only because
  // no pod answered, and saving that would persist a suppressed platform prompt
  // as though an admin had chosen it.
  const canSave = data !== undefined && !data.source_unavailable && (isDirty || data.is_default) && !clientError;

  const onDraftChange = (next: string) => {
    setDraft(next);
    setServerError(undefined);
  };

  const onDiscard = () => {
    if (data) onDraftChange(data.text);
  };

  const onSave = async () => {
    try {
      await setPlatformPrompt({ setPlatformPromptRequest: { text: draft } }).unwrap();
      setServerError(undefined);
      showSuccess({ summary: t("rework.platformPrompt.saved") });
    } catch (error: unknown) {
      // A 403 (not a platform admin) or 5xx must not look like a successful
      // save. A 422 names what was refused: that goes under the editor, where
      // the fix is, and the toast only says the save did not happen.
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.platformPrompt.saveFailed") });
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.platformPrompt.title")} subtitle={t("rework.platformPrompt.subtitle")} />

      <div className={styles.split}>
        {/* Read-only, shipped with the platform, and the first block the model
            reads: it carries the precedence rule the editable prompt is
            subject to, which is why it sits first here too. */}
        <section className={styles.pane}>
          <div className={styles.paneHead}>
            <div className={styles.paneTitleRow}>
              <h2 className={styles.paneTitle}>{t("rework.platformPrompt.instructions.title")}</h2>
              <span className={styles.badge}>{t("rework.platformPrompt.instructions.badge")}</span>
            </div>
            <p className={styles.paneSubtitle}>{t("rework.platformPrompt.instructions.subtitle")}</p>
          </div>

          {/* An unreachable pod must not render as "the platform has no
              instructions" — they still apply to every agent, it is only this
              display that failed. */}
          {instructions?.source_unavailable ? (
            <p className={styles.warning}>{t("rework.platformPrompt.instructions.unavailable")}</p>
          ) : (
            <pre className={styles.instructionsBody}>{instructions?.text ?? ""}</pre>
          )}
          <p className={styles.instructionsNote}>{t("rework.platformPrompt.instructions.note")}</p>
        </section>

        <section className={styles.pane}>
          <div className={styles.paneHead}>
            <div className={styles.paneTitleRow}>
              <h2 className={styles.paneTitle}>{t("rework.platformPrompt.editor.title")}</h2>
              <span className={styles.badge}>{t("rework.platformPrompt.editor.badge")}</span>
            </div>
            <p className={styles.paneSubtitle}>{t("rework.platformPrompt.editor.subtitle")}</p>
          </div>

          {/* Only the two states a reader cannot see for themselves get a line
              here; "no admin has saved one yet" is already told by the Editable
              badge and the default text sitting in the editor. */}
          {data?.source_unavailable && <p className={styles.warning}>{t("rework.platformPrompt.sourceUnavailable")}</p>}
          {data && !data.is_default && data.text.length === 0 && (
            <p className={styles.notice}>{t("rework.platformPrompt.suppressed")}</p>
          )}

          <div className={styles.editorSlot}>
            <PromptEditor
              label={t("rework.platformPrompt.field.label")}
              value={draft}
              onChange={onDraftChange}
              disabled={isLoading || isSaving}
              error={clientError ?? serverError}
            />
          </div>
          <div className={styles.editorFooter}>
            <p className={styles.hint}>{t("rework.platformPrompt.field.explanation")}</p>
            <p className={`${styles.counter} ${tooLong ? styles.counterOver : ""}`}>
              {draftLength} / {PLATFORM_PROMPT_MAX_CHARS}
            </p>
          </div>

          {/* Save belongs to this pane, not to the page header: only one of the
              two blocks is editable. */}
          <div className={styles.paneFooter}>
            {data?.updated_at && (
              <p className={styles.meta}>
                {t("rework.platformPrompt.lastUpdated", {
                  who: data.updated_by
                    ? userDisplayName(data.updated_by, auditUserById.get(data.updated_by))
                    : t("rework.platformPrompt.unknownAuthor"),
                  when: new Date(data.updated_at).toLocaleString(),
                })}
              </p>
            )}
            <div className={styles.actions}>
              <Button
                color="primary"
                variant="outlined"
                size="medium"
                onClick={onDiscard}
                disabled={!isDirty || isSaving}
              >
                {t("rework.platformPrompt.reset")}
              </Button>
              <Button
                color="primary"
                variant="filled"
                size="medium"
                icon={{ category: "outlined", type: "check", filled: false }}
                onClick={onSave}
                disabled={!canSave || isSaving}
              >
                {isSaving ? t("rework.platformPrompt.saving") : t("rework.platformPrompt.save")}
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
