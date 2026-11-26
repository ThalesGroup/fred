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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { findReservedPromptTag } from "@rework/utils/promptValidation";
import {
  useGetCommonPromptSettingsQuery,
  usePutCommonPromptSettingsMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformPromptPage.module.css";

// Count Unicode code points, as the Control Plane validation does.
const PLATFORM_PROMPT_MAX_CHARS = 20_000;

export default function PlatformSystemPromptPane({ organizationId }: { organizationId: string }) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const {
    currentData: data,
    isFetching,
    isError,
    error,
    refetch,
  } = useGetCommonPromptSettingsQuery({ organizationId }, { refetchOnMountOrArgChange: true });
  const [setCommonPrompt, { isLoading: isSaving }] = usePutCommonPromptSettingsMutation();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [runtimeId, setRuntimeId] = useState<string>();
  const source = data?.defaults.find((item) => item.runtime_id === runtimeId) ?? data?.defaults[0];
  const sourceUnavailable = !source || source.source_unavailable;
  // An untouched draft follows the selected source only while the organization
  // has no override. Selection never changes the organization's runtime settings.
  const [editedDraft, setDraft] = useState<string>();
  const storedText = data?.text ?? source?.platform_prompt ?? "";
  const draft = editedDraft ?? storedText;
  const [serverError, setServerError] = useState<string>();
  useEffect(() => {
    setDraft(undefined);
    setServerError(undefined);
  }, [data?.text]);

  const reservedTag = findReservedPromptTag(draft);
  const draftLength = [...draft].length;
  const tooLong = draftLength > PLATFORM_PROMPT_MAX_CHARS;
  const clientError = reservedTag
    ? t("rework.promptEditor.reservedTag", { tag: reservedTag })
    : tooLong
      ? t("rework.platformPrompt.field.tooLong", { max: PLATFORM_PROMPT_MAX_CHARS })
      : undefined;
  const isDirty = editedDraft !== undefined && draft !== storedText;
  // An unreachable source is never silently adopted as an empty prompt. An
  // Owner can still author an explicit override, including explicit suppression.
  const canSave =
    data !== undefined &&
    !isError &&
    !isFetching &&
    !clientError &&
    (data.text === null ? !sourceUnavailable || editedDraft !== undefined : isDirty);

  const onDraftChange = (next: string) => {
    setDraft(next);
    setServerError(undefined);
  };

  const onDiscard = () => {
    setDraft(undefined);
    setServerError(undefined);
  };

  const onSave = async () => {
    try {
      await setCommonPrompt({ organizationId, setCommonPrompt: { text: draft } }).unwrap();
      if (!mounted.current) return;
      setServerError(undefined);
      showSuccess({ summary: t("rework.platformPrompt.saved") });
    } catch (error: unknown) {
      if (!mounted.current) return;
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.platformPrompt.saveFailed") });
    }
  };

  if (isError)
    return (
      <div role="alert">
        <p>{t("rework.platformPrompt.loadFailed")}</p>
        <p>{normalizeApiError(error).detail}</p>
        <Button color="primary" variant="outlined" size="medium" onClick={() => void refetch()}>
          {t("rework.provisioning.retryAuthority")}
        </Button>
      </div>
    );
  if (!data) return <p role="status">{t("common.loading")}</p>;

  return (
    <>
      <p className={styles.tabIntro}>{t("rework.platformPrompt.subtitle")}</p>
      <Select
        size="medium"
        compact
        label={t("rework.platformPrompt.source")}
        value={source?.runtime_id}
        options={data.defaults.map((item) => ({
          key: item.runtime_id,
          value: item.runtime_id,
          label: item.runtime_id,
        }))}
        onChange={setRuntimeId}
        disabled={isSaving}
        emptyMessage={t("rework.platformPrompt.noSources")}
      />
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
          {sourceUnavailable ? (
            <p className={styles.warning}>{t("rework.platformPrompt.instructions.unavailable")}</p>
          ) : (
            <pre className={styles.instructionsBody}>
              {source?.platform_instructions ?? t("rework.platformPrompt.instructions.empty")}
            </pre>
          )}
          {data.text !== null && !sourceUnavailable && (
            <>
              <p className={styles.paneTitle}>{t("rework.platformPrompt.defaultPreview")}</p>
              <pre className={`${styles.instructionsBody} ${styles.defaultPreview}`}>
                {source?.platform_prompt ?? ""}
              </pre>
              <Button
                color="primary"
                variant="outlined"
                size="medium"
                disabled={isSaving || isFetching}
                onClick={() => onDraftChange(source?.platform_prompt ?? "")}
              >
                {t("rework.platformPrompt.useDefault")}
              </Button>
            </>
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

          {data.text === null && <p className={styles.notice}>{t("rework.platformPrompt.usingDefault")}</p>}
          {sourceUnavailable && <p className={styles.warning}>{t("rework.platformPrompt.sourceUnavailable")}</p>}
          {data.text === "" && <p className={styles.notice}>{t("rework.platformPrompt.suppressed")}</p>}

          <div className={styles.editorSlot}>
            <PromptEditor
              fillHeight
              label={t("rework.platformPrompt.field.label")}
              value={draft}
              onChange={onDraftChange}
              disabled={isFetching || isSaving}
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
                  who: data.updated_by ? data.updated_by : t("rework.platformPrompt.unknownAuthor"),
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
                disabled={editedDraft === undefined || isSaving}
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
                {isSaving
                  ? t("rework.platformPrompt.saving")
                  : t(
                      data.text === null && editedDraft === undefined
                        ? "rework.platformPrompt.adoptDefault"
                        : "rework.platformPrompt.save",
                    )}
              </Button>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
