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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor.tsx";
import Select, { type SelectOption } from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { findReservedPromptTag } from "@rework/utils/promptValidation";
import {
  useCreationAssistantSettingsQuery,
  useResetCreationAssistantPromptMutation,
  useSetCreationAssistantSettingsMutation,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./PlatformPromptPage.module.css";
import {
  normalizeReasoningEffort,
  REASONING_ON,
  reasoningControl,
  type ReasoningEffort,
} from "./creationAssistantReasoning";

// Mirrors `MAX_CREATION_ASSISTANT_PROMPT_CHARS` in fred-sdk's agent_draft.py.
const CREATION_ASSISTANT_PROMPT_MAX_CHARS = 20_000;
const LANGUAGE_PLACEHOLDER = "{language}";

/** Admin settings of the agent form's creation assistant: meta-prompt and model. */
export default function CreationAssistantPane() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data, isLoading } = useCreationAssistantSettingsQuery();
  const [savePrompt, { isLoading: isSaving }] = useSetCreationAssistantSettingsMutation();
  const [resetPrompt, { isLoading: isResetting }] = useResetCreationAssistantPromptMutation();
  const busy = isLoading || isSaving || isResetting;

  const auditUids = data?.updated_by ? [data.updated_by] : [];
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });
  const auditUserById = new Map(auditUsers.map((summary) => [summary.id, summary]));

  const [draft, setDraft] = useState("");
  // "" stands for the platform's default chat model.
  const [modelDraft, setModelDraft] = useState("");
  const [reasoningDraft, setReasoningDraft] = useState<ReasoningEffort>("off");
  const [showDefault, setShowDefault] = useState(false);
  const [serverError, setServerError] = useState<string | undefined>();
  useEffect(() => {
    if (!data) return;
    setDraft(data.text);
    setModelDraft(data.model_profile_id ?? "");
    setReasoningDraft(data.reasoning_effort ?? "off");
  }, [data]);

  const savedModel = data?.model_profile_id ?? "";
  const savedReasoning = data?.reasoning_effort ?? "off";
  // The platform default uses the pods' common default profile when known; a
  // vanished profile gets the switch and the pod clamps the value.
  const controlFor = (profileId: string) =>
    reasoningControl(
      data?.model_options?.find((option) => option.profile_id === (profileId || data?.default_model_profile_id)),
    );
  const control = controlFor(modelDraft);
  const reasoningSupported = control.kind !== "unsupported";
  const reasoningShown = normalizeReasoningEffort(reasoningDraft, control);
  const modelOptions: SelectOption<string>[] = [
    { key: "default", value: "", label: t("rework.platformPrompt.creationAssistant.model.default") },
    ...(data?.model_options ?? []).map((option) => ({
      key: option.profile_id,
      value: option.profile_id,
      label: option.name,
    })),
  ];
  // A saved profile no pod advertises any more: still shown, drafts fall back to the default.
  if (savedModel && !modelOptions.some((option) => option.value === savedModel)) {
    modelOptions.push({
      key: savedModel,
      value: savedModel,
      label: t("rework.platformPrompt.creationAssistant.model.missing", { id: savedModel }),
    });
  }

  const reservedTag = findReservedPromptTag(draft);
  const draftLength = [...draft].length;
  const tooLong = draftLength > CREATION_ASSISTANT_PROMPT_MAX_CHARS;
  const clientError = reservedTag
    ? t("rework.promptEditor.reservedTag", { tag: reservedTag })
    : tooLong
      ? t("rework.platformPrompt.field.tooLong", { max: CREATION_ASSISTANT_PROMPT_MAX_CHARS })
      : !draft.trim() && !(data?.is_default && draft === data.text)
        ? t("rework.platformPrompt.creationAssistant.empty")
        : undefined;
  // Saving is still allowed: the backend accepts it and flags it the same way.
  const missingPlaceholder = draft.trim().length > 0 && !draft.includes(LANGUAGE_PLACEHOLDER);

  // An untouched built-in text is not saved as an override.
  const sendsText = data !== undefined && !(data.is_default && draft === data.text);
  const isDirty =
    data !== undefined && (draft !== data.text || modelDraft !== savedModel || reasoningDraft !== savedReasoning);
  const canSave = data !== undefined && isDirty && !clientError;

  const onDraftChange = (next: string) => {
    setDraft(next);
    setServerError(undefined);
  };

  const onSave = async () => {
    try {
      await savePrompt({
        setCreationAssistantSettingsRequest: {
          text: sendsText ? draft : null,
          model_profile_id: modelDraft || null,
          reasoning_effort: reasoningShown,
        },
      }).unwrap();
      setServerError(undefined);
      showSuccess({ summary: t("rework.platformPrompt.creationAssistant.saved") });
    } catch (error: unknown) {
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.platformPrompt.creationAssistant.saveFailed") });
    }
  };

  const onReset = () =>
    showConfirmationDialog({
      title: t("rework.platformPrompt.creationAssistant.resetConfirm.title"),
      message: t("rework.platformPrompt.creationAssistant.resetConfirm.message"),
      confirmButtonLabel: t("rework.platformPrompt.creationAssistant.reset"),
      onConfirm: async () => {
        try {
          await resetPrompt().unwrap();
          setServerError(undefined);
          showSuccess({ summary: t("rework.platformPrompt.creationAssistant.resetDone") });
        } catch (error: unknown) {
          showError({
            summary: t("rework.platformPrompt.creationAssistant.resetFailed"),
            detail: normalizeApiError(error).detail,
          });
        }
      },
    });

  const reasoningLabel = t("rework.platformPrompt.creationAssistant.reasoning.label");
  const unsupportedHint = t("rework.platformPrompt.creationAssistant.reasoning.unsupported");
  const levelLabel = (level: ReasoningEffort) => t(`rework.platformPrompt.creationAssistant.reasoning.levels.${level}`);
  const reasoningToggle = (
    <div className={styles.reasoningToggle}>
      <Switch
        size="small"
        checked={reasoningShown !== "off" && reasoningSupported}
        onChange={(event) => setReasoningDraft(event.target.checked ? REASONING_ON : "off")}
        disabled={busy || !reasoningSupported}
        aria-label={reasoningSupported ? reasoningLabel : `${reasoningLabel}. ${unsupportedHint}`}
      />
      <span aria-hidden="true">{reasoningLabel}</span>
    </div>
  );
  const reasoningLevels: ReasoningEffort[] = control.kind === "levels" ? ["off", ...control.levels] : [];
  const reasoningControlNode =
    control.kind === "levels" ? (
      <div className={styles.reasoningToggle}>
        <span aria-hidden="true">{reasoningLabel}</span>
        <ButtonGroup
          size="2xs"
          color="secondary"
          variant="radio"
          aria-label={reasoningLabel}
          items={reasoningLevels.map((level) => ({ label: levelLabel(level), disabled: busy }))}
          selectedIndex={reasoningLevels.indexOf(reasoningShown)}
          onSelectedIndexChange={(index) => setReasoningDraft(reasoningLevels[index])}
        />
      </div>
    ) : reasoningSupported ? (
      reasoningToggle
    ) : (
      <Tooltip text={unsupportedHint}>{reasoningToggle}</Tooltip>
    );

  return (
    <section className={`${styles.pane} ${styles.fill}`}>
      <div className={styles.paneHeadRow}>
        <div className={styles.paneHead}>
          <div className={styles.paneTitleRow}>
            <h2 className={styles.paneTitle}>{t("rework.platformPrompt.creationAssistant.title")}</h2>
            <span className={styles.badge}>
              {data?.is_default
                ? t("rework.platformPrompt.creationAssistant.badgeDefault")
                : t("rework.platformPrompt.creationAssistant.badgeCustom")}
            </span>
          </div>
          <p className={styles.paneSubtitle}>{t("rework.platformPrompt.creationAssistant.subtitle")}</p>
        </div>
        <div className={styles.modelSlot}>
          <Select
            size="small"
            compact
            ariaLabel={t("rework.platformPrompt.creationAssistant.model.label")}
            options={modelOptions}
            value={modelDraft}
            onChange={(value) => {
              setModelDraft(value);
              setReasoningDraft((current) => normalizeReasoningEffort(current, controlFor(value)));
              setServerError(undefined);
            }}
            disabled={busy}
          />
          {reasoningControlNode}
        </div>
      </div>

      {data?.source_unavailable && data.is_default && (
        <p className={styles.warning}>{t("rework.platformPrompt.sourceUnavailable")}</p>
      )}
      {missingPlaceholder && (
        <p className={styles.warning}>{t("rework.platformPrompt.creationAssistant.missingLanguage")}</p>
      )}
      {/* Derived server-side from dates only: saving again or restoring the default clears it. */}
      {data?.default_changed_since_override && data.default_revised_at && data.updated_at && (
        <div className={`${styles.warning} ${styles.revisionBanner}`}>
          <p className={styles.revisionText}>
            {t("rework.platformPrompt.creationAssistant.defaultRevised", {
              revised: new Date(`${data.default_revised_at}T00:00:00`).toLocaleDateString(),
              customized: new Date(data.updated_at).toLocaleDateString(),
            })}
          </p>
          <Button color="primary" variant="text" size="small" onClick={() => setShowDefault((shown) => !shown)}>
            {showDefault
              ? t("rework.platformPrompt.creationAssistant.hideDefault")
              : t("rework.platformPrompt.creationAssistant.viewDefault")}
          </Button>
        </div>
      )}
      {showDefault && data?.default_changed_since_override && (
        <pre className={`${styles.instructionsBody} ${styles.defaultPreview}`} data-testid="creation-assistant-default">
          {data.default_text ?? ""}
        </pre>
      )}

      <div className={styles.editorSlot}>
        <PromptEditor
          fillHeight
          label={t("rework.platformPrompt.field.label")}
          value={draft}
          onChange={onDraftChange}
          disabled={busy}
          error={clientError ?? serverError}
        />
      </div>
      <div className={styles.editorFooter}>
        <p className={styles.hint}>{t("rework.platformPrompt.creationAssistant.hint")}</p>
        <p className={`${styles.counter} ${tooLong ? styles.counterOver : ""}`}>
          {draftLength} / {CREATION_ASSISTANT_PROMPT_MAX_CHARS}
        </p>
      </div>

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
            variant="text"
            size="medium"
            onClick={onReset}
            disabled={data === undefined || data.is_default || busy}
          >
            {t("rework.platformPrompt.creationAssistant.reset")}
          </Button>
          <Button
            color="primary"
            variant="outlined"
            size="medium"
            onClick={() => {
              if (!data) return;
              onDraftChange(data.text);
              setModelDraft(savedModel);
              setReasoningDraft(savedReasoning);
            }}
            disabled={!isDirty || busy}
          >
            {t("rework.platformPrompt.reset")}
          </Button>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            icon={{ category: "outlined", type: "check", filled: false }}
            onClick={onSave}
            disabled={!canSave || busy}
          >
            {isSaving ? t("rework.platformPrompt.saving") : t("rework.platformPrompt.save")}
          </Button>
        </div>
      </div>
    </section>
  );
}
