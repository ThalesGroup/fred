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
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import {
  usePlatformInstructionsQuery,
  usePlatformPromptQuery,
  useSetPlatformPromptMutation,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformPromptPage.module.css";

// Mirrors `PLATFORM_PROMPT_MAX_CHARS` in the backend's
// `platform_prompt/schemas.py`. Kept visible in the editor rather than only
// enforced on submit: this text is re-sent on every model call of every agent,
// so the cost of a long one should be apparent while typing.
const PLATFORM_PROMPT_MAX_CHARS = 20_000;

/**
 * The two prompt blocks every agent receives ahead of its own instructions,
 * shown side by side in the order the model sees them: the platform prompt an
 * admin owns on the left, the instructions the platform ships on the right.
 *
 * The split is the point — an admin writing the left pane needs to read the
 * right one to know what is already covered, and a stacked layout put the
 * read-only block a scroll away from the editor it exists to inform.
 */
export default function PlatformPromptPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading } = usePlatformPromptQuery();
  const { data: instructions } = usePlatformInstructionsQuery();
  const [setPlatformPrompt, { isLoading: isSaving }] = useSetPlatformPromptMutation();

  // The row stores the acting user's Keycloak uid, not their name — a uid is
  // stable across renames and is the right thing to persist for audit. Resolve
  // it for display only, the same way agent cards resolve their own audit uids
  // (#1952); `userDisplayName` falls back to the raw uid when the lookup finds
  // nothing, so an unresolvable or M2M-disabled deployment still shows who.
  const auditUids = data?.updated_by ? [data.updated_by] : [];
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const [draft, setDraft] = useState("");
  // `data` arrives after the first render, and again after every save. Seeding
  // the draft from it on each arrival keeps the editor showing what is actually
  // stored, including the `updated_by`/`updated_at` the save echoes back.
  useEffect(() => {
    if (data) setDraft(data.text);
  }, [data]);

  // `is_default` (no row ever saved) must stay saveable even when the draft
  // still equals the empty `text` the API reports for it: saving "" from that
  // state is how an admin suppresses the block platform-wide, and it is a real
  // state change (`is_default` flips to false). Comparing text alone would
  // leave that transition unreachable from the UI — the one distinction the
  // backend goes out of its way to preserve.
  const isDirty = data !== undefined && draft !== data.text;
  // Blocked while `source_unavailable`: the editor is showing "" only because
  // no pod answered, and saving that would persist a suppressed platform prompt
  // as though an admin had chosen it.
  const canSave = data !== undefined && !data.source_unavailable && (isDirty || data.is_default);

  const onSave = async () => {
    try {
      await setPlatformPrompt({ setPlatformPromptRequest: { text: draft } }).unwrap();
      showSuccess({ summary: t("rework.platformPrompt.saved") });
    } catch {
      // A 403 (not a platform admin) or 5xx must not look like a successful
      // save — without this the page silently kept showing the draft.
      showError({ summary: t("rework.platformPrompt.saveFailed") });
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.platformPrompt.title")} subtitle={t("rework.platformPrompt.subtitle")} />

      <div className={styles.split}>
        <section className={styles.pane}>
          <div className={styles.paneHead}>
            <div className={styles.paneTitleRow}>
              <h2 className={styles.paneTitle}>{t("rework.platformPrompt.editor.title")}</h2>
              <span className={styles.badge}>{t("rework.platformPrompt.editor.badge")}</span>
            </div>
            <p className={styles.paneSubtitle}>{t("rework.platformPrompt.editor.subtitle")}</p>
          </div>

          {/* Only the two states a reader cannot see for themselves get a line
              here. "No admin has saved one yet" is not one of them: the Editable
              badge and the default text sitting in the editor already say it, so
              a notice repeating it was noise on the state the page is in most of
              the time. */}
          {data?.source_unavailable && <p className={styles.warning}>{t("rework.platformPrompt.sourceUnavailable")}</p>}
          {data && !data.is_default && data.text.length === 0 && (
            <p className={styles.notice}>{t("rework.platformPrompt.suppressed")}</p>
          )}

          <div className={styles.editorSlot}>
            <TextArea
              label={t("rework.platformPrompt.field.label")}
              explanation={t("rework.platformPrompt.field.explanation")}
              value={draft}
              maxLength={PLATFORM_PROMPT_MAX_CHARS}
              disabled={isLoading || isSaving}
              onChange={(event) => setDraft(event.target.value)}
            />
          </div>

          {/* Save belongs to this pane, not to the page header: only one of the
              two blocks is editable, and a page-level button read as if it
              might be saving both. */}
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
                onClick={() => data && setDraft(data.text)}
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

        {/* Read-only, shipped with the platform. Shown so an admin can see
            exactly what every agent is told after the prompt on the left — the
            two are rendered back to back in the real system prompt, in the
            same order as these panes. */}
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
      </div>
    </div>
  );
}
